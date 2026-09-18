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


def cards(html):
    """Just the match cards — the standings name every player whatever the
    filter, so an unscoped `in html` would pass on the wrong thing."""
    return html[html.index('class="matches"'):]


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
        assert "Matches &middot; today" in html and "1 match." in html
        # Only the match list is filtered — the standings still name everyone —
        # so the check looks inside the cards.
        assert 'side-name">Cal<' in cards(html)
        assert 'side-name">Bob<' not in cards(html)
        html = app.get("/ladder?player=U0BBB1").data.decode()
        assert "Matches &middot; Bob" in html
        assert 'side-name">Bob<' in cards(html)
        assert 'side-name">Cal<' not in cards(html)


def test_bad_filter_values_fall_back_to_the_plain_list(app, fake):
    """A stale or hand-edited link must never echo its junk or 500."""
    with patch("bot.refresh_names"):
        html = app.get("/ladder?player=%3Cscript%3E&day=someday").data.decode()
    assert "The Ladder" in html and "Matches &middot;" not in html
    assert "someday" not in html and "&lt;script&gt;" not in html


# --- the pages beyond the ladder -------------------------------------------

PAGE_PATHS = ["/matches", "/players", "/stats", "/log"]


@pytest.mark.parametrize("path", PAGE_PATHS)
@pytest.mark.parametrize("prefix", ["", "/api/index"])
def test_a_page_answers_on_either_path_vercel_may_deliver(app, fake, path, prefix):
    """Vercel hands Flask the original path or the rewrite destination, so
    every page is matched on the tail — the same rule /ladder lives by."""
    with patch("bot.refresh_names"):
        assert app.get(prefix + path).status_code == 200


def test_a_player_page_is_found_by_id(app, fake):
    import store
    store.ensure_players(["U0AAA1"])
    store.set_name("U0AAA1", "Ann")
    with patch("bot.refresh_names"):
        for path in ("/player/U0AAA1", "/api/index/player/U0AAA1"):
            page = app.get(path)
            assert page.status_code == 200 and b"Ann" in page.data


def test_an_unknown_player_is_a_404_not_an_empty_card(app, fake):
    with patch("bot.refresh_names"):
        gone = app.get("/player/U0NOPE")
    assert gone.status_code == 404 and b"Nothing here" in gone.data


def test_an_unknown_path_is_a_404_with_a_way_back(app, fake):
    gone = app.get("/nonsense")
    assert gone.status_code == 404 and b"Back to the ladder" in gone.data


def test_the_root_is_still_the_health_check(app, fake):
    assert b"TT Ranker is running" in app.get("/").data


def test_a_page_says_so_when_there_is_no_database(app, monkeypatch):
    """Without the KV pair there is nowhere for a rating to live; each page
    says which variables are missing rather than rendering an empty shell."""
    monkeypatch.delenv("KV_REST_API_URL", raising=False)
    monkeypatch.delenv("UPSTASH_REDIS_REST_URL", raising=False)
    with patch("bot.refresh_names"):
        answer = app.get("/players")
    assert answer.status_code == 503 and b"KV_REST_API_URL" in answer.data


def test_the_log_page_needs_no_database_at_all(app, monkeypatch):
    monkeypatch.delenv("KV_REST_API_URL", raising=False)
    monkeypatch.delenv("UPSTASH_REDIS_REST_URL", raising=False)
    assert app.get("/log").status_code == 200


def test_a_junk_filter_on_the_matches_page_degrades_to_the_plain_list(app, fake):
    """A stale or hand-edited link must never echo its junk or 500."""
    with patch("bot.refresh_names"):
        html = app.get("/matches?player=%3Cscript%3E&day=someday"
                       "&format=%3Cimg%3E").data.decode()
    # Dropped, not echoed: neither raw nor escaped does the junk appear. (The
    # document has a <script> of its own, so the check is for the echo.)
    assert "&lt;script&gt;" not in html and "&lt;img&gt;" not in html
    assert "<img>" not in html and "MATCHES" in html.upper()


def test_a_junk_opponent_on_a_profile_falls_back(app, fake):
    import store
    store.ensure_players(["U0AAA1"])
    with patch("bot.refresh_names"):
        page = app.get("/player/U0AAA1?vs=%3Cscript%3E")
    assert page.status_code == 200 and b"<script>alert" not in page.data


def test_a_page_that_throws_still_answers_in_words(app, fake, monkeypatch):
    """A broken page is a page, not a stack trace — and the trace only appears
    when the deployment has asked for it."""
    from web.pages import players as page_players
    monkeypatch.setattr(page_players, "render",
                        MagicMock(side_effect=RuntimeError("boom")))
    with patch("bot.refresh_names"):
        broken = app.get("/players")
    assert broken.status_code == 500
    assert b"That didn" in broken.data and b"boom" not in broken.data

    monkeypatch.setenv("TT_SHOW_ERRORS", "1")
    with patch("bot.refresh_names"):
        assert b"boom" in app.get("/players").data


# --- search, compare and the spins board -----------------------------------

def test_the_players_page_filters_by_name(app, fake):
    import store
    store.ensure_players(["U0AAA1", "U0BBB1"])
    store.set_name("U0AAA1", "Ann"); store.set_name("U0BBB1", "Bob")
    with patch("bot.refresh_names"):
        html = app.get("/players?q=ann").data.decode()
    grid = html[html.index('class="pc-grid"'):]
    assert "Ann" in grid and "Bob" not in grid


def test_the_matches_page_filters_by_name(app, fake):
    import store
    store.set_name("U0AAA1", "Ann"); store.set_name("U0BBB1", "Bob")
    store.set_name("U0CCC1", "Cal")
    _rated("U0AAA1", "U0BBB1", store.now_ist())
    _rated("U0CCC1", "U0BBB1", store.now_ist())
    with patch("bot.refresh_names"):
        html = app.get("/matches?q=ann").data.decode()
    assert html.count('<article class="match"') == 1
    assert 'side-name">Ann<' in cards(html)


def test_a_search_term_is_never_echoed_raw(app, fake):
    with patch("bot.refresh_names"):
        html = app.get("/matches?q=%3Cscript%3Ealert(1)%3C/script%3E").data.decode()
    assert "<script>alert(1)" not in html


def test_compare_needs_two_known_players(app, fake):
    import store
    store.ensure_players(["U0AAA1", "U0BBB1"])
    store.set_name("U0AAA1", "Ann"); store.set_name("U0BBB1", "Bob")
    with patch("bot.refresh_names"):
        assert b"Pick two players" in app.get("/compare").data
        assert b"Pick two players" in app.get("/compare?p=U0AAA1").data
        # An unknown id is not guessed at.
        assert b"Pick two players" in app.get("/compare?p=U0AAA1&p=U0NOPE").data
        both = app.get("/compare?p=U0AAA1&p=U0BBB1").data
        assert b"Side by side" in both and b"Ann" in both and b"Bob" in both
        # The pair of links already pasted in the channel still work.
        assert b"Side by side" in app.get("/compare?a=U0AAA1&b=U0BBB1").data


def test_nobody_is_compared_with_themselves(app, fake):
    import store
    store.ensure_players(["U0AAA1"])
    with patch("bot.refresh_names"):
        assert b"Pick two players" in app.get("/compare?p=U0AAA1&p=U0AAA1").data


def test_the_popup_asks_for_the_comparison_without_the_page(app, fake):
    """`?bare=1` is what the dialog fetches — the same render, no shell."""
    import store
    store.ensure_players(["U0AAA1", "U0BBB1"])
    with patch("bot.refresh_names"):
        bare = app.get("/compare?bare=1&p=U0AAA1&p=U0BBB1").data
    assert b"<!doctype html>" not in bare and b"Side by side" in bare


def test_the_players_page_carries_the_compare_mode(app, fake):
    import store
    store.ensure_players(["U0AAA1", "U0BBB1"])
    with patch("bot.refresh_names"):
        plain = app.get("/players").data
        picking = app.get("/players?compare=1&p=U0AAA1").data
    # The script names the class too, so the check is for the markup.
    assert b'class="pc pc-pick' not in plain
    assert b'class="pc pc-pick' in picking and b"is-picked" in picking


def test_the_ladder_switches_to_the_spins_board(app, fake):
    import betting
    import store
    now = store.now_ist()
    for _ in range(4):        # enough games to reach the singles board
        _rated("U0AAA1", "U0BBB1", now)
    betting.ensure_wallets(["U0AAA1", "U0BBB1"])
    betting.adjust("U0AAA1", 1000, "won a bet")
    with patch("bot.refresh_names"):
        ratings = app.get("/ladder").data.decode()
        spins = app.get("/ladder?board=spins").data.decode()
    assert "<h2>Standings</h2>" in ratings and "<h2>Spins</h2>" not in ratings
    assert "<h2>Spins</h2>" in spins and "<h2>Standings</h2>" not in spins


def test_a_junk_board_falls_back_to_the_ratings(app, fake):
    with patch("bot.refresh_names"):
        html = app.get("/ladder?board=%3Cscript%3E").data.decode()
    assert "<h2>Spins</h2>" not in html


# --- titles ----------------------------------------------------------------

def test_the_titles_page_is_served(app, fake):
    import store
    store.ensure_players(["U0AAA1", "U0BBB1"])
    with patch("bot.refresh_names"):
        html = app.get("/titles").data.decode()
    assert "Titles" in html and "Going spare" in html


def test_titles_are_in_the_bar_on_every_page(app, fake):
    import store
    store.ensure_players(["U0AAA1"])
    with patch("bot.refresh_names"):
        for path in ("/ladder", "/players", "/matches", "/stats", "/titles"):
            assert 'href="/titles"' in app.get(path).data.decode()


def test_a_page_renders_even_when_the_titles_lookup_fails(app, fake):
    """The chips are a cache read on a page that has a job to do without them."""
    with patch("bot.refresh_names"), \
         patch("awards.current", side_effect=RuntimeError("kv is down")):
        response = app.get("/ladder")
    assert response.status_code == 200
    assert b"Table Tennis League" in response.data
