"""
HTTP Events API entry point — Vercel serverless function.

vercel.json rewrites every path to /api/index/<original-path>, so this one
function serves all routes. Vercel's platform may deliver the WSGI PATH_INFO as
the original path ('/slack/events') or as the rewrite destination with the
original appended ('/api/index/slack/events'); we route on the path *suffix* so
it works either way.

Requires SLACK_BOT_TOKEN, SLACK_SIGNING_SECRET and the KV_REST_API_* pair in the
Vercel project's environment variables.
"""
import logging
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, request

log = logging.getLogger("tt-ranker")
app = Flask(__name__)

# Initialize guarded, so a misconfiguration (missing env var, import problem)
# surfaces as a readable error instead of an opaque FUNCTION_INVOCATION_FAILED.
_init_error = None
try:
    # NB: must not be named `handler` — Vercel's Python runtime treats a
    # module-level `handler` as a BaseHTTPRequestHandler class.
    from slack_bolt.adapter.flask import SlackRequestHandler

    from bot import build_app

    bolt_app = build_app(process_before_response=True, token_verification=False)
    slack_request_handler = SlackRequestHandler(bolt_app)
except Exception:
    _init_error = traceback.format_exc()


def _debug_payload(observed_path):
    """Self-checks: what's configured and what broke. Never exposes secrets."""
    import kv
    import standings
    import store

    required = ("SLACK_BOT_TOKEN", "SLACK_SIGNING_SECRET", "KV_REST_API_URL",
                "KV_REST_API_TOKEN", "CRON_SECRET", "TT_CHANNEL", "TT_ADMINS")
    payload = {
        "commit": os.environ.get("VERCEL_GIT_COMMIT_SHA", "unknown")[:7],
        # Which deployment answered, and which env's variables it was built with.
        # An env var only reaches a *new* deployment, so "I set it and it's still
        # false" is nearly always an old deployment still serving — without these
        # two fields that is indistinguishable from the variable being wrong.
        "deployment": os.environ.get("VERCEL_DEPLOYMENT_ID", "local"),
        "vercel_env": os.environ.get("VERCEL_ENV", "local"),
        "python": sys.version.split()[0],
        "observed_path": observed_path,  # what Vercel actually handed Flask
        "env": {name: bool(os.environ.get(name)) for name in required},
        "kv_configured": kv.kv_available(),
        "init_ok": _init_error is None,
        "init_error": _init_error,
    }
    if kv.kv_available() and request.args.get("ladder"):
        # Read-only snapshot: tells "the cron never ran" apart from "it ran and
        # the post failed", which look identical from outside.
        week_key, label = standings.previous_week()
        players = store.all_players()
        payload["ladder"] = {
            "players": len(players),
            "pending": len(store.list_pending()),
            "due_week": week_key,
            "label": label,
            "already_announced": week_key in set(kv.smembers(standings.POSTED_KEY) or []),
            "invocations": standings.invocation_log(),
        }
    return payload


def _authorized():
    """CRON_SECRET must match when it is set. Both cron endpoints are safe to
    call twice — the weekly post claims its week and the sweep claims each match
    — so an unauthenticated hit is at worst a no-op, never a duplicate."""
    secret = os.environ.get("CRON_SECRET")
    return not secret or request.headers.get("Authorization") == f"Bearer {secret}"


def _run_cron(fn):
    """Shared wrapper for /cron/*: record the call, check the secret, run."""
    if _init_error:
        return {"error": "app failed to initialize; see GET /"}, 500
    import standings
    authorized = _authorized()
    # Recorded before the auth check, so a scheduler call that was rejected is
    # still visible rather than looking like it never happened.
    standings.record_invocation(request.headers.get("User-Agent"), authorized)
    if not authorized:
        return {"error": "unauthorized"}, 401
    try:
        dry = request.args.get("dry") in ("1", "true", "yes")
        return fn(standings, bolt_app.client, dry)
    except Exception:
        log.exception("cron failed")
        return {"error": traceback.format_exc().splitlines()[-1]}, 500


def _render_ladder():
    """The public ladder page — the link that goes in the channel topic.

    Read-only and unauthenticated by design: it holds display names and ratings,
    nothing that isn't already visible to anyone in the Slack channel.
    """
    import kv
    if not kv.kv_available():
        return "<p>No database configured yet.</p>", 503, {"Content-Type": "text/html"}
    import bot
    import page
    import store

    try:
        # Opportunistic and best-effort: if users:read isn't granted this is a
        # no-op and the page falls back to names slash commands have revealed.
        if _init_error is None:
            bot.refresh_names(bolt_app.client, logger=log)
    except Exception:
        log.exception("name refresh failed; rendering with what we have")

    players = store.all_players()
    view = request.args.get("view", "")
    if view not in dict(page.VIEWS):
        view = ""
    week_delta, week_played = store.week_movement()
    body = page.render(
        players=store.singles_players(players) if view == "singles" else players,
        names=store.names(),
        recent=store.recent_matches(limit=8),
        week_delta=week_delta,
        week_played=week_played,
        placement_games=bot.PLACEMENT_GAMES,
        channel_hint=os.environ.get("TT_CHANNEL_NAME", ""),
        updated=store.now_ist().strftime("%H:%M IST"),
        view=view,
    )
    # Let a CDN hold it briefly so a channel-wide click doesn't become a
    # thundering herd, while staying fresh enough to feel live.
    return body, 200, {"Content-Type": "text/html; charset=utf-8",
                       "Cache-Control": "public, max-age=15, stale-while-revalidate=60"}


@app.route("/", defaults={"subpath": ""}, methods=["GET", "POST"])
@app.route("/<path:subpath>", methods=["GET", "POST"])
def route(subpath):
    tail = "/" + subpath  # e.g. "/slack/events" or "/api/index/slack/events"

    if request.method == "POST" and tail.endswith("/slack/events"):
        if _init_error:
            return {"error": "app failed to initialize; see GET /"}, 500
        # Slack retries an event when our first response misses its 3s ack
        # deadline (common on serverless cold starts). That first invocation
        # still runs to completion, so ack retried *event* deliveries without
        # reprocessing. Slash commands and button presses are not retried this
        # way, and url_verification is a setup handshake — never skip those.
        if request.headers.get("X-Slack-Retry-Num"):
            body = request.get_json(silent=True) or {}
            if body.get("type") == "event_callback":
                log.info("Skipping Slack retry #%s (reason: %s)",
                         request.headers.get("X-Slack-Retry-Num"),
                         request.headers.get("X-Slack-Retry-Reason"))
                return "", 200
        return slack_request_handler.handle(request)

    # Both cron jobs pay the stipend. It is claimed once per week, so whichever
    # fires first that week hands it out and the other is a no-op — nobody goes
    # unpaid because one scheduled job was skipped.
    if tail.endswith("/cron/standings"):
        return _run_cron(lambda s, client, dry: {
            **s.post_weekly(client, dry_run=dry),
            "stipend": s.pay_due_stipend(dry_run=dry)})

    if tail.endswith("/cron/sweep"):
        return _run_cron(lambda s, client, dry: {
            **s.sweep_pending(client, dry_run=dry),
            "fixtures": s.sweep_fixtures(client, dry_run=dry),
            "stipend": s.pay_due_stipend(dry_run=dry)})

    if tail.endswith("/ladder"):
        return _render_ladder()

    if tail.endswith("/debug"):
        return _debug_payload(tail)

    if _init_error:
        return f"<pre>init failed:\n\n{_init_error}</pre>", 500
    return "TT Ranker is running."
