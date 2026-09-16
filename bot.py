"""
TT Ranker — shared bot logic, host-agnostic.

Entry points:
  socket_mode.py — Socket Mode (local dev / Docker), no public URL needed.
  api/index.py   — HTTP Events API (Vercel serverless).

One slash command, `/tt`, with subcommands. Several slash commands would each
need their own manifest entry and their own Slack re-install every time one is
added; a single verb keeps the app definition stable and the help in one place.

A logged match does not move anybody's rating on its own — it waits for someone
on the other side to press Confirm (or for the daily sweep to age it in). See
store.py for why the rating maths happens at confirmation time rather than here.
"""
import logging
import os
import ssl
from datetime import datetime

from slack_bolt import App
from slack_sdk import WebClient

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s")
log = logging.getLogger("tt-ranker")

import elo
import kv
import parsing
import store

CONFIRM_ACTION = "tt_confirm"
DISPUTE_ACTION = "tt_dispute"

# Below this many matches a rating says more about luck than about the player,
# so they sit in a "still placing" line instead of the ladder proper.
PLACEMENT_MATCHES = 5
BOARD_LIMIT = 20
MEDALS = (":first_place_medal:", ":second_place_medal:", ":third_place_medal:")

NO_KV = (":warning: No database is configured, so I can't track ratings. "
         "Set `KV_REST_API_URL` and `KV_REST_API_TOKEN` and redeploy.")


# --- formatting ------------------------------------------------------------

def fmt_side(uids):
    return " & ".join(f"<@{u}>" for u in uids)


def fmt_games(games):
    return "  ".join(f"`{a}-{b}`" for a, b in games)


def fmt_delta(d):
    return f"+{d}" if d > 0 else (str(d) if d < 0 else "±0")


def fmt_ago(iso, now=None):
    """"3h ago" — vague on purpose; nobody needs the seconds."""
    if not iso:
        return "never"
    try:
        then = datetime.fromisoformat(iso)
    except ValueError:
        return "a while ago"
    seconds = ((now or store.now_ist()) - then).total_seconds()
    for limit, div, unit in ((90, 1, "s"), (5400, 60, "m"), (172800, 3600, "h")):
        if seconds < limit:
            return f"{max(0, int(seconds // div))}{unit} ago"
    return f"{int(seconds // 86400)}d ago"


def fmt_streak(streak):
    if streak >= 3:
        return f":fire: {streak} wins"
    if streak > 0:
        return f"{streak} win{'s' if streak > 1 else ''}"
    if streak <= -3:
        return f":snowflake: {-streak} losses"
    if streak < 0:
        return f"{-streak} loss{'es' if streak < -1 else ''}"
    return "—"


def _section(text):
    return {"type": "section", "text": {"type": "mrkdwn", "text": text}}


def _context(text):
    return {"type": "context", "elements": [{"type": "mrkdwn", "text": text}]}


def scoreline(record, games_a, games_b, settled):
    """"*<@a>* beat *<@b>* — *2–1*", or the neutral form while it's a claim."""
    a, b = fmt_side(record["side_a"]), fmt_side(record["side_b"])
    if not settled:
        return f":table_tennis_paddle_and_ball: *{a}*  {games_a}–{games_b}  *{b}*"
    if games_a == games_b:
        return f":table_tennis_paddle_and_ball: *{a}* drew with *{b}* — *{games_a}–{games_b}*"
    winner, loser = (a, b) if games_a > games_b else (b, a)
    high, low = max(games_a, games_b), min(games_a, games_b)
    return f":table_tennis_paddle_and_ball: *{winner}* beat *{loser}* — *{high}–{low}*"


def pending_blocks(record):
    """The confirmation prompt: the claim, plus the buttons that settle it."""
    games_a, games_b, _, _ = elo.tally(record["games"])
    who = confirmers(record)
    ask = (f"{fmt_side(who)} — confirm to lock in the rating change."
           if who else "Waiting on confirmation.")
    mid = record["id"]
    return [
        _section(f"{scoreline(record, games_a, games_b, settled=False)}\n"
                 f"{fmt_games(record['games'])}"),
        _context(f"Logged by <@{record['logged_by']}> · {ask} "
                 f"Auto-confirms in {store.AUTO_CONFIRM_HOURS}h."),
        {"type": "actions", "block_id": f"tt_actions_{mid}", "elements": [
            {"type": "button", "action_id": CONFIRM_ACTION, "style": "primary",
             "text": {"type": "plain_text", "text": "✅  Confirm"}, "value": mid},
            {"type": "button", "action_id": DISPUTE_ACTION,
             "text": {"type": "plain_text", "text": "❌  That's wrong"}, "value": mid},
        ]},
    ]


def applied_blocks(blob):
    """The settled match: who won, and what it cost everyone."""
    lines = [scoreline(blob, blob["games_a"], blob["games_b"], settled=True),
             fmt_games(blob["games"]), ""]
    for uid in blob["side_a"] + blob["side_b"]:
        before, after = blob["before"][uid], blob["after"][uid]
        lines.append(f"<@{uid}>  {before} → *{after}*  `{fmt_delta(blob['deltas'][uid])}`")

    how = ("auto-confirmed — nobody objected"
           if blob.get("auto_confirmed")
           else (f"confirmed by <@{blob['confirmed_by']}>" if blob.get("confirmed_by")
                 else "confirmed"))
    tail = f"Match `#{blob['id']}` · {how}"
    if blob.get("doubles"):
        tail += " · doubles"
    return [_section("\n".join(lines)), _context(tail)]


# --- who may confirm -------------------------------------------------------

def confirmers(record):
    """Who can confirm: the side the reporter is *not* on.

    Confirmation is only worth anything if it comes from someone the result
    costs. A bystander logging someone else's match has no side, so then anyone
    who actually played can settle it.
    """
    a, b, logged_by = record["side_a"], record["side_b"], record["logged_by"]
    if logged_by in a:
        return list(b)
    if logged_by in b:
        return list(a)
    return list(a) + list(b)


def disputers(record):
    """Anyone involved can say it's wrong — including the reporter, for whom the
    button is really a cancel."""
    return list(dict.fromkeys(record["side_a"] + record["side_b"] + [record["logged_by"]]))


# --- /tt log ---------------------------------------------------------------

def handle_log(command, respond, client, bot_id, logger=None):
    caller = command.get("user_id")
    _, rest = parsing.split_subcommand(command.get("text", ""))
    try:
        parsed = parsing.parse_match(rest, caller=caller, bot_id=bot_id)
    except parsing.ParseError as e:
        respond(f":warning: {e}")
        return

    record = store.create_pending(parsed["side_a"], parsed["side_b"], parsed["games"],
                                  logged_by=caller, channel=command.get("channel_id"))
    try:
        # Posted rather than `respond`ed so a confirmation hours later can still
        # edit it: a slash command's response_url expires after 30 minutes.
        resp = client.chat_postMessage(
            channel=command["channel_id"], blocks=pending_blocks(record),
            text=f"Match logged by <@{caller}> — needs confirming.")
    except Exception as e:
        # Almost always not_in_channel. Drop the pending rather than leave one
        # nobody can see, let alone confirm.
        store.drop_pending(record["id"])
        (logger or log).warning("could not post pending match: %s", e)
        respond(f":warning: I couldn't post in this channel — invite me first with "
                f"`/invite <@{bot_id}>` and log it again." if bot_id else
                ":warning: I couldn't post in this channel — invite me here and try again.")
        return
    store.set_pending_message(record["id"], resp["channel"], resp["ts"])


def handle_confirm(body, client, respond, logger=None):
    mid = _action_value(body)
    user = body["user"]["id"]
    record = store.get_pending(mid)
    if not record:
        respond(response_type="ephemeral",
                text=":information_source: That match has already been settled.")
        return
    allowed = confirmers(record)
    if allowed and user not in allowed:
        respond(response_type="ephemeral",
                text=f":lock: Only {fmt_side(allowed)} can confirm this one.")
        return
    if not store.claim_pending(mid):
        respond(response_type="ephemeral",
                text=":information_source: Someone just confirmed that one.")
        return
    try:
        blob = store.apply_match(record, confirmed_by=user)
    except Exception:
        store.release_pending(mid)  # leave it confirmable rather than stuck
        (logger or log).exception("applying match %s failed", mid)
        respond(response_type="ephemeral",
                text=":x: Something went wrong rating that match — try again in a moment.")
        return
    _replace(body, client, respond, applied_blocks(blob),
             fallback="Match confirmed.", logger=logger)


def handle_dispute(body, client, respond, logger=None):
    mid = _action_value(body)
    user = body["user"]["id"]
    record = store.get_pending(mid)
    if not record:
        respond(response_type="ephemeral",
                text=":information_source: That match has already been settled.")
        return
    if user not in disputers(record):
        respond(response_type="ephemeral",
                text=":lock: Only the players in this match can dispute it.")
        return
    store.drop_pending(mid)
    games_a, games_b, _, _ = elo.tally(record["games"])
    blocks = [
        _section(f":no_entry_sign: ~{scoreline(record, games_a, games_b, settled=False)}~\n"
                 f"~{fmt_games(record['games'])}~"),
        _context(f"Thrown out by <@{user}> — no ratings changed. "
                 "Log it again with the right scores."),
    ]
    _replace(body, client, respond, blocks, fallback="Match discarded.", logger=logger)


def _action_value(body):
    return (body.get("actions") or [{}])[0].get("value", "")


def _replace(body, client, respond, blocks, fallback, logger=None):
    """Swap the prompt for the outcome, so no message is left showing live
    buttons for a match that is already settled.

    chat_update first because it keeps working indefinitely; response_url is the
    fallback for the case where the bot has since lost access to the channel.
    """
    container = body.get("container") or {}
    channel, ts = container.get("channel_id"), container.get("message_ts")
    if client is not None and channel and ts:
        try:
            client.chat_update(channel=channel, ts=ts, blocks=blocks, text=fallback)
            return
        except Exception as e:
            (logger or log).warning("chat_update failed, falling back to respond: %s", e)
    respond(replace_original=True, blocks=blocks, text=fallback)


# --- read-only subcommands -------------------------------------------------

def handle_register(command, respond):
    uid = command["user_id"]
    fresh = store.ensure_players([uid])
    if fresh:
        respond(f":table_tennis_paddle_and_ball: You're on the ladder at *{elo.START_RATING}*, "
                f"<@{uid}>. Log a match with `/tt log @opponent 11-7 9-11 11-5`.")
        return
    player = store.get_player(uid) or store.new_player()
    respond(f":information_source: You're already on the ladder at *{player['rating']}*. "
            "`/tt me` for the full card.")


def handle_me(command, respond, bot_id=None):
    _, rest = parsing.split_subcommand(command.get("text", ""))
    mentioned = parsing.mentions_in(rest, exclude=bot_id)
    uid = mentioned[0] if mentioned else command["user_id"]
    player = store.get_player(uid)
    if not player:
        respond(f":grey_question: <@{uid}> isn't on the ladder yet — "
                "`/tt register`, or just play a match and I'll add them.")
        return

    played = player["matches"]
    decided = player["wins"] + player["losses"]
    rate = f" ({round(100 * player['wins'] / decided)}%)" if decided else ""
    rank, total = _rank_of(uid)
    lines = [
        f":table_tennis_paddle_and_ball: *<@{uid}>* — *{player['rating']}*"
        + (f"   ·   #{rank} of {total}" if rank else "   ·   _still placing_"),
        f"*Record*  {player['wins']}-{player['losses']}"
        + (f"-{player['draws']}" if player["draws"] else "") + rate
        + f"   ·   *Games*  {player['games_won']}-{player['games_lost']}"
        + f"   ·   *Points*  {player['points_won']}-{player['points_lost']}",
        f"*Peak*  {player['peak']}   ·   *Streak*  {fmt_streak(player['streak'])}"
        + (f"   ·   *Best*  {player['best_streak']}" if player["best_streak"] > 1 else ""),
    ]
    if played < PLACEMENT_MATCHES:
        lines.append(f"_{PLACEMENT_MATCHES - played} more match"
                     f"{'es' if PLACEMENT_MATCHES - played > 1 else ''} to join the ladder._")
    else:
        lines.append(f"_{played} matches · last played {fmt_ago(player['last_played'])}._")
    respond("\n".join(lines))


def _rank_of(uid):
    """(rank, ladder size) for a placed player, else (None, size)."""
    ranked = ranked_players(store.all_players())
    for i, (u, _) in enumerate(ranked, start=1):
        if u == uid:
            return i, len(ranked)
    return None, len(ranked)


def ranked_players(players):
    """[(uid, record)] for everyone past placement, strongest first. Ties break
    on matches played, so the person who has actually shown up ranks higher."""
    placed = [(u, p) for u, p in players.items() if p["matches"] >= PLACEMENT_MATCHES]
    return sorted(placed, key=lambda item: (-item[1]["rating"], -item[1]["matches"], item[0]))


def board_text(players, limit=BOARD_LIMIT, title="Table tennis ladder"):
    """The leaderboard, shared by `/tt board` and the weekly post."""
    if not players:
        return (f":table_tennis_paddle_and_ball: *{title}*\n"
                "_Nobody has registered yet — `/tt register` to start it off._")
    ranked = ranked_players(players)
    lines = [f":table_tennis_paddle_and_ball: *{title}*"]
    for i, (uid, p) in enumerate(ranked[:limit]):
        badge = MEDALS[i] if i < 3 else f"`{i + 1:>2}.`"
        row = f"{badge}  <@{uid}> — *{p['rating']}*  ·  {p['wins']}-{p['losses']}"
        if abs(p["streak"]) >= 3:
            row += f"  ·  {fmt_streak(p['streak'])}"
        lines.append(row)
    if not ranked:
        lines.append(f"_No one has played {PLACEMENT_MATCHES} matches yet._")
    if len(ranked) > limit:
        lines.append(f"_…and {len(ranked) - limit} more._")

    placing = sorted(((u, p) for u, p in players.items() if p["matches"] < PLACEMENT_MATCHES),
                     key=lambda item: (-item[1]["matches"], item[0]))
    if placing:
        who = ", ".join(f"<@{u}> ({p['matches']})" for u, p in placing[:10])
        lines.append(f"\n_Still placing ({PLACEMENT_MATCHES} matches to qualify): {who}_")
    return "\n".join(lines)


def handle_board(respond):
    respond(board_text(store.all_players()))


def handle_history(command, respond, bot_id=None):
    _, rest = parsing.split_subcommand(command.get("text", ""))
    mentioned = parsing.mentions_in(rest, exclude=bot_id)
    uid = mentioned[0] if mentioned else None
    matches = store.recent_matches(limit=10, uid=uid)
    if not matches:
        respond(f":grey_question: No matches recorded for <@{uid}> yet." if uid
                else ":grey_question: No matches recorded yet.")
        return
    who = f" for <@{uid}>" if uid else ""
    lines = [f":scroll: *Recent matches{who}*"]
    for blob in matches:
        deltas = "  ".join(f"<@{u}> `{fmt_delta(blob['deltas'][u])}`"
                           for u in blob["side_a"] + blob["side_b"])
        lines.append(f"`#{blob['id']}`  {fmt_side(blob['side_a'])} "
                     f"*{blob['games_a']}–{blob['games_b']}* {fmt_side(blob['side_b'])}"
                     f"   {deltas}   ·  _{fmt_ago(blob.get('applied_at'))}_")
    respond("\n".join(lines))


def handle_pending(respond):
    records = store.list_pending()
    if not records:
        respond(":white_check_mark: Nothing waiting — every match is confirmed.")
        return
    lines = [":hourglass_flowing_sand: *Waiting on confirmation*"]
    for record in records:
        games_a, games_b, _, _ = elo.tally(record["games"])
        who = confirmers(record)
        lines.append(f"`#{record['id']}`  {fmt_side(record['side_a'])} *{games_a}–{games_b}* "
                     f"{fmt_side(record['side_b'])}  ·  logged by <@{record['logged_by']}> "
                     f"{fmt_ago(record['logged_at'])}  ·  needs {fmt_side(who) or 'anyone'}")
    lines.append("\n_Scroll back to the match message to confirm, or leave it — "
                 f"unconfirmed matches apply themselves after {store.AUTO_CONFIRM_HOURS}h._")
    respond("\n".join(lines))


def handle_undo(command, respond):
    uid = command["user_id"]
    blob = store.last_match_by(uid)
    if not blob:
        respond(":grey_question: You haven't logged any confirmed matches to undo. "
                "(A match still waiting on confirmation can be thrown out with the "
                "*That's wrong* button on its message.)")
        return
    ok, reason = store.can_undo(blob)
    if not ok:
        respond(f":warning: {reason}")
        return
    store.undo_match(blob)
    restored = "  ".join(f"<@{u}> back to *{blob['before'][u]}*"
                         for u in blob["side_a"] + blob["side_b"])
    respond(f":leftwards_arrow_with_hook: Undid match `#{blob['id']}` "
            f"({fmt_side(blob['side_a'])} {blob['games_a']}–{blob['games_b']} "
            f"{fmt_side(blob['side_b'])}).\n{restored}")


def handle_odds(command, respond, bot_id=None):
    _, rest = parsing.split_subcommand(command.get("text", ""))
    try:
        side_a, side_b = parsing.parse_odds(rest, caller=command.get("user_id"), bot_id=bot_id)
    except parsing.ParseError as e:
        respond(f":warning: {e}")
        return
    players = store.load_for_match(side_a + side_b)
    entries = lambda side: [{"uid": u, "rating": players[u]["rating"],
                             "matches": players[u]["matches"]} for u in side]
    chance = elo.win_probability(entries(side_a), entries(side_b))
    ra, rb = elo.team_rating(entries(side_a)), elo.team_rating(entries(side_b))
    respond(f":crystal_ball: {fmt_side(side_a)} *{round(100 * chance)}%*  ·  "
            f"*{round(100 * (1 - chance))}%* {fmt_side(side_b)}"
            f"\n_{round(ra)} vs {round(rb)} — per game, on current ratings._")


HELP = f""":table_tennis_paddle_and_ball: *TT Ranker* — the office table tennis ladder.

*Log a match* (scores are the points in each game)
• `/tt log @bob 11-7 9-11 11-5` — singles, you vs Bob
• `/tt log @partner vs @dan @eve 11-7 11-9` — doubles
• `/tt log @ann @bob vs @cal @dee 11-7 11-9` — record someone else's match

The other side confirms it, then ratings move. Unconfirmed matches apply on \
their own after {store.AUTO_CONFIRM_HOURS}h.

*Everything else*
• `/tt board` — the ladder      • `/tt me [@player]` — one player's card
• `/tt history [@player]` — recent results    • `/tt pending` — awaiting confirmation
• `/tt odds @bob` — who's favoured    • `/tt undo` — revert the last match you logged
• `/tt register` — join early (playing a match registers you anyway)

*How the rating works*
Everyone starts at *{elo.START_RATING}*. A match moves you by \
`K × margin × (games won − games expected)`, so beating someone above you is \
worth more, a whitewash beats a squeaker, and doubles counts \
{int(elo.DOUBLES_K_FACTOR * 100)}% as hard as singles. You're provisional \
(bigger swings) for your first {elo.PROVISIONAL_MATCHES} matches and join the \
ladder proper after {PLACEMENT_MATCHES}."""


# --- routing ---------------------------------------------------------------

def handle_tt_command(ack, command, respond, client=None, context=None, logger=None):
    ack()
    sub, _ = parsing.split_subcommand(command.get("text", ""))
    bot_id = (context or {}).get("bot_user_id")

    if sub == "help":
        respond(HELP)
        return
    if not kv.kv_available():
        respond(NO_KV)
        return

    try:
        if sub == "log":
            handle_log(command, respond, client, bot_id, logger=logger)
        elif sub == "register":
            handle_register(command, respond)
        elif sub == "me":
            handle_me(command, respond, bot_id)
        elif sub == "board":
            handle_board(respond)
        elif sub == "history":
            handle_history(command, respond, bot_id)
        elif sub == "pending":
            handle_pending(respond)
        elif sub == "undo":
            handle_undo(command, respond)
        elif sub == "odds":
            handle_odds(command, respond, bot_id)
        else:
            respond(HELP)
    except Exception:
        (logger or log).exception("/tt %s failed", sub)
        respond(":x: Something went wrong on my side — try again in a moment.")


def build_app(process_before_response=False, token_verification=True):
    """Build a Bolt App wired with the `/tt` command and the match buttons.

    process_before_response=True is required on serverless hosts (Vercel):
    listeners must finish before the HTTP response is returned, because the
    process is frozen the moment it responds.
    """
    # The corporate TLS proxy (VMock CA) re-signs certificates without the
    # Authority Key Identifier extension, which Python 3.13+'s strict
    # verification rejects. Keep full verification but drop the strict flag.
    ssl_context = ssl.create_default_context()
    ssl_context.verify_flags &= ~ssl.VERIFY_X509_STRICT

    app = App(
        client=WebClient(token=os.environ["SLACK_BOT_TOKEN"], ssl=ssl_context),
        signing_secret=os.environ.get("SLACK_SIGNING_SECRET"),
        process_before_response=process_before_response,
        token_verification_enabled=token_verification,
    )
    app.command("/tt")(handle_tt_command)
    app.action(CONFIRM_ACTION)(_wrap_action(handle_confirm))
    app.action(DISPUTE_ACTION)(_wrap_action(handle_dispute))
    return app


def _wrap_action(fn):
    """Ack the button press first — Slack greys it out after 3s regardless of how
    the rating maths is going."""
    def listener(ack, body, respond, client=None, logger=None):
        ack()
        if not kv.kv_available():
            respond(response_type="ephemeral", text=NO_KV)
            return
        try:
            fn(body, client, respond, logger=logger)
        except Exception:
            (logger or log).exception("action %s failed", fn.__name__)
            respond(response_type="ephemeral",
                    text=":x: Something went wrong — try again in a moment.")
    return listener
