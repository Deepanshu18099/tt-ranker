"""The Vercel entry point: routing on the path suffix, cron auth, diagnostics."""
from unittest.mock import MagicMock, patch

import pytest

import standings
from api import index
from tests.fake_kv import FakeRedis


@pytest.fixture
def app():
    index.app.config["TESTING"] = True
    return index.app.test_client()


@pytest.fixture
def fake():
    redis = FakeRedis()
    with redis.patched():
        yield redis


def test_the_app_starts_up_clean():
    assert index._init_error is None


def test_the_root_is_a_health_check(app):
    assert b"TT Ranker is running" in app.get("/").data


@pytest.mark.parametrize("path", ["/debug", "/api/index/debug"])
def test_debug_works_whichever_path_vercel_hands_us(app, path):
    """Vercel may deliver the original path or the rewrite destination."""
    payload = app.get(path).get_json()
    assert payload["init_ok"] is True
    assert payload["observed_path"] == path
    assert payload["env"]["SLACK_BOT_TOKEN"] is True


def test_debug_identifies_which_deployment_answered(app, monkeypatch):
    """Without this, "I set the variable and it's still false" can't be told
    apart from an older deployment still serving traffic."""
    monkeypatch.setenv("VERCEL_DEPLOYMENT_ID", "dpl_abc123")
    monkeypatch.setenv("VERCEL_ENV", "production")
    payload = app.get("/debug").get_json()
    assert payload["deployment"] == "dpl_abc123"
    assert payload["vercel_env"] == "production"


def test_debug_reports_the_ladder_on_request(app, fake):
    payload = app.get("/debug?ladder=1").get_json()
    assert payload["ladder"]["players"] == 0
    assert payload["ladder"]["pending"] == 0
    assert payload["ladder"]["already_announced"] is False


def test_debug_never_leaks_a_secret(app):
    body = app.get("/debug").data.decode()
    assert "test-signing-secret" not in body and "xoxb-test-token" not in body


# --- cron ------------------------------------------------------------------

@pytest.mark.parametrize("path", ["/cron/standings", "/cron/sweep"])
def test_a_cron_endpoint_runs_when_no_secret_is_set(app, fake, monkeypatch, path):
    monkeypatch.delenv("CRON_SECRET", raising=False)
    assert app.get(f"{path}?dry=1").status_code == 200


@pytest.mark.parametrize("path", ["/cron/standings", "/cron/sweep"])
def test_a_cron_endpoint_refuses_the_wrong_secret(app, fake, monkeypatch, path):
    monkeypatch.setenv("CRON_SECRET", "s3cret")
    assert app.get(path).status_code == 401
    ok = app.get(path, headers={"Authorization": "Bearer s3cret"})
    assert ok.status_code == 200


def test_a_rejected_call_is_still_recorded(app, fake, monkeypatch):
    """Otherwise a scheduler call that was turned away looks like one that never
    happened at all."""
    monkeypatch.setenv("CRON_SECRET", "s3cret")
    app.get("/cron/standings", headers={"User-Agent": "vercel-cron/1.0"})
    assert "last_denied_at" in standings.invocation_log()


def test_a_dry_standings_run_reports_without_consuming_the_week(app, fake, monkeypatch):
    """The endpoint has to be safe to poke at: ?dry=1 must leave the week
    unclaimed so the real Monday run still posts it."""
    monkeypatch.delenv("CRON_SECRET", raising=False)
    payload = app.get("/cron/standings?dry=1").get_json()
    assert payload["status"] == "dry_run"
    assert standings.kv.smembers(standings.POSTED_KEY) == []


def test_a_cron_failure_answers_with_an_error_not_a_crash(app, fake, monkeypatch):
    monkeypatch.delenv("CRON_SECRET", raising=False)
    monkeypatch.setattr(standings, "sweep_pending",
                        MagicMock(side_effect=RuntimeError("boom")))
    resp = app.get("/cron/sweep")
    assert resp.status_code == 500 and "boom" in resp.get_json()["error"]


# --- Slack events ----------------------------------------------------------

def test_a_slack_event_retry_is_acked_without_reprocessing(app):
    """The first invocation still runs to completion on a slow cold start, so
    re-handling the retry would double-post."""
    with patch.object(index, "slack_request_handler") as handler:
        resp = app.post("/slack/events", json={"type": "event_callback"},
                        headers={"X-Slack-Retry-Num": "1"})
    assert resp.status_code == 200
    assert handler.handle.call_count == 0


def test_a_command_retry_is_still_handled(app):
    """Only event deliveries are skipped — a slash command or button press that
    Slack re-sends is a fresh interaction."""
    with patch.object(index, "slack_request_handler") as handler:
        handler.handle.return_value = ""
        app.post("/slack/events", data={"command": "/tt"},
                 headers={"X-Slack-Retry-Num": "1"})
    assert handler.handle.call_count == 1


def test_the_setup_handshake_is_never_skipped(app):
    with patch.object(index, "slack_request_handler") as handler:
        handler.handle.return_value = ""
        app.post("/slack/events", json={"type": "url_verification", "challenge": "x"},
                 headers={"X-Slack-Retry-Num": "1"})
    assert handler.handle.call_count == 1


# --- the ladder's filters --------------------------------------------------

def _rated(a, b, when):
    import store
    rec = store.create_pending([a], [b], [(11, 7)], logged_by=a, now=when)
    assert store.claim_pending(rec["id"])
    return store.apply_match(rec, confirmed_by=b, now=when)


def test_the_ladder_filters_by_day_and_player(app, fake):
    import store
    from datetime import timedelta
    now = store.now_ist()
    store.set_name("U0AAA1", "Ann"); store.set_name("U0BBB1", "Bob")
    store.set_name("U0CCC1", "Cal")
    _rated("U0AAA1", "U0BBB1", now - timedelta(days=1))
    _rated("U0AAA1", "U0CCC1", now)
    with patch("bot.refresh_names"):
        html = app.get("/ladder?day=today").data.decode()
        assert "Sessions · today" in html and "1 session." in html
        assert "beat</span><span>Cal" in html and "beat</span><span>Bob" not in html
        html = app.get("/ladder?player=U0BBB1").data.decode()
        assert "Sessions · Bob" in html and "beat</span><span>Bob" in html
        assert "beat</span><span>Cal" not in html


def test_bad_filter_values_fall_back_to_the_plain_list(app, fake):
    """A stale or hand-edited link must never echo its junk or 500."""
    with patch("bot.refresh_names"):
        html = app.get("/ladder?player=%3Cscript%3E&day=someday").data.decode()
    assert "Table tennis ladder" in html and "Sessions ·" not in html
    assert "someday" not in html and "&lt;script&gt;" not in html
