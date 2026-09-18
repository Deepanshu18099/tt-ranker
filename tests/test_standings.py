"""The weekly standings post."""
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

import standings
import store
from tests.fake_kv import FakeRedis

A, B, C = "U0AAA1", "U0BBB1", "U0CCC1"


@pytest.fixture
def fake():
    redis = FakeRedis()
    with redis.patched():
        yield redis


@pytest.fixture
def client():
    c = MagicMock()
    c.chat_postMessage.return_value = {"channel": "C9", "ts": "1.1"}
    return c


def at(y, m, d, h=9):
    return datetime(y, m, d, h, tzinfo=store.IST)


def play(side_a, side_b, games=((11, 7), (11, 9)), now=None):
    record = store.create_pending(side_a, side_b, list(games), logged_by=side_a[0], now=now)
    assert store.claim_pending(record["id"])
    return store.apply_match(record, confirmed_by=side_b[0], now=now)


# --- which week ------------------------------------------------------------

def test_a_monday_run_reports_the_week_that_just_ended():
    now = at(2026, 9, 14)
    key, label = standings.previous_week(now)
    assert key == store.week_key(now - timedelta(days=7))
    assert "Sep" in label


def test_the_label_spans_two_months_when_the_week_does():
    _, label = standings.previous_week(at(2026, 10, 5))
    assert "–" in label or "-" in label


def test_weeks_are_bucketed_in_ist():
    # 23:00 IST Sunday is still that week, though it is already Monday in UTC+0
    late_sunday = datetime(2026, 9, 13, 23, 0, tzinfo=store.IST)
    assert store.week_key(late_sunday) == store.week_key(at(2026, 9, 9))


# --- the message -----------------------------------------------------------

def test_a_quiet_week_produces_nothing(fake):
    assert standings.build_message(store.week_key(), "1–7 Sep") is None


def test_the_post_carries_the_ladder_and_the_movers(fake):
    now = at(2026, 9, 9)
    blob = play([A], [B], now=now)
    text = standings.build_message(blob["week"], "7–13 Sep")
    assert "Table tennis ladder" in text
    assert "player-matches" in text
    assert f"<@{A}>" in text and "Climbers" in text
    assert "Toughest week" in text and f"<@{B}>" in text


def test_a_week_with_only_wins_needs_no_wooden_spoon(fake, monkeypatch):
    """Nobody should be singled out for a loss that didn't happen."""
    now = at(2026, 9, 9)
    play([A], [B], games=[(11, 7), (7, 11)], now=now)   # a draw: no deltas
    text = standings.build_message(store.week_key(now), "7–13 Sep")
    assert "Toughest week" not in text and "Climbers" not in text
    assert "player-matches" in text


# --- posting ---------------------------------------------------------------

def test_posting_is_idempotent(fake, client, monkeypatch):
    monkeypatch.setattr(standings, "CHANNEL", "C9")
    now = at(2026, 9, 14)
    play([A], [B], now=now - timedelta(days=3))

    assert standings.post_weekly(client, now=now)["status"] == "posted"
    assert standings.post_weekly(client, now=now)["status"] == "already_posted"
    assert client.chat_postMessage.call_count == 1


def test_a_quiet_week_is_not_consumed(fake, client, monkeypatch):
    """A week with no matches must stay claimable, or a late confirmation could
    never be announced."""
    monkeypatch.setattr(standings, "CHANNEL", "C9")
    now = at(2026, 9, 14)
    assert standings.post_weekly(client, now=now)["status"] == "no_activity"
    play([A], [B], now=now - timedelta(days=3))
    assert standings.post_weekly(client, now=now)["status"] == "posted"


def test_a_dry_run_neither_posts_nor_consumes_the_week(fake, client, monkeypatch):
    monkeypatch.setattr(standings, "CHANNEL", "C9")
    now = at(2026, 9, 14)
    play([A], [B], now=now - timedelta(days=3))

    dry = standings.post_weekly(client, now=now, dry_run=True)
    assert dry["status"] == "dry_run" and dry["would_post"] and "ladder" in dry["preview"]
    assert client.chat_postMessage.call_count == 0
    assert standings.post_weekly(client, now=now)["status"] == "posted"


def test_without_a_channel_it_says_which_var_is_missing(fake, client, monkeypatch):
    monkeypatch.setattr(standings, "CHANNEL", "")
    result = standings.post_weekly(client, now=at(2026, 9, 14))
    assert result["status"] == "no_channel" and "TT_CHANNEL" in result["detail"]


# --- diagnostics -----------------------------------------------------------

def test_cron_calls_are_told_apart_from_manual_ones(fake):
    standings.record_invocation("vercel-cron/1.0")
    standings.record_invocation("curl/8.0")
    standings.record_invocation("vercel-cron/1.0", authorized=False)
    log = standings.invocation_log()
    assert log["cron_count"] == "2" and log["other_count"] == "1"
    assert "last_denied_at" in log


def test_diagnostics_never_break_the_run_they_measure(fake, monkeypatch):
    monkeypatch.setattr(standings.kv, "hset_many",
                        MagicMock(side_effect=RuntimeError("kv down")))
    standings.record_invocation("vercel-cron/1.0")  # must not raise


# --- payday ----------------------------------------------------------------

def test_a_quiet_week_still_pays_the_stipend(fake, monkeypatch):
    """The bug this file gained a section for: payday used to sit after the
    weekly post's early returns, so a week with no matches paid nobody — the
    exact week people need spins to start playing again."""
    import betting
    # Pinned, not inherited: without this the test reads TT_CHANNEL from
    # whatever .env the machine happens to have, and fails on one that has none.
    monkeypatch.setattr(standings, "CHANNEL", "C9")
    monkeypatch.setattr(betting, "WEEKLY_STIPEND", 1000)
    store.ensure_players([A, B])
    now = at(2026, 9, 14)
    assert standings.post_weekly(MagicMock(), now=now)["status"] == "no_activity"
    assert standings.pay_due_stipend(now=now)["status"] == "paid"
    assert betting.balance(A) == betting.START_SPINS + betting.WEEKLY_STIPEND


def test_payday_does_not_need_a_channel(fake, monkeypatch):
    import betting
    monkeypatch.setattr(betting, "WEEKLY_STIPEND", 1000)
    store.ensure_players([A])
    standings.CHANNEL = ""
    assert standings.pay_due_stipend()["status"] == "paid"
    assert betting.balance(A) == betting.START_SPINS + betting.WEEKLY_STIPEND


def test_whichever_cron_fires_first_pays_and_the_rest_are_no_ops(fake, monkeypatch):
    """Vercel has skipped scheduled invocations before, so both jobs try."""
    import betting
    monkeypatch.setattr(betting, "WEEKLY_STIPEND", 1000)
    store.ensure_players([A])
    now = at(2026, 9, 14)
    assert standings.pay_due_stipend(now=now)["status"] == "paid"
    assert standings.pay_due_stipend(now=now)["status"] == "already_paid"
    assert betting.balance(A) == betting.START_SPINS + betting.WEEKLY_STIPEND


def test_a_dry_run_says_what_it_would_do_without_paying(fake, monkeypatch):
    import betting
    monkeypatch.setattr(betting, "WEEKLY_STIPEND", 1000)
    store.ensure_players([A])
    assert standings.pay_due_stipend(dry_run=True)["status"] == "would_pay"
    assert betting.balance(A) == betting.START_SPINS
    standings.pay_due_stipend()
    assert standings.pay_due_stipend(dry_run=True)["status"] == "already_paid"


def test_each_week_is_paid_once(fake, monkeypatch):
    import betting
    monkeypatch.setattr(betting, "WEEKLY_STIPEND", 1000)
    store.ensure_players([A])
    standings.pay_due_stipend(now=at(2026, 9, 14))
    standings.pay_due_stipend(now=at(2026, 9, 21))     # the next week
    assert betting.balance(A) == betting.START_SPINS + 2 * betting.WEEKLY_STIPEND
