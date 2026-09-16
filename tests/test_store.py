"""Persistence: registration, the pending queue, applying a match, and undo."""
from datetime import timedelta

import pytest

import elo
import store
from tests.fake_kv import FakeRedis

A, B, C, D = "U0AAA1", "U0BBB1", "U0CCC1", "U0DDD1"
WIN_2_1 = [(11, 7), (9, 11), (11, 5)]


@pytest.fixture
def fake():
    redis = FakeRedis()
    with redis.patched():
        yield redis


def log(side_a, side_b, games=WIN_2_1, by=None, now=None):
    return store.create_pending(side_a, side_b, games, logged_by=by or side_a[0], now=now)


def confirm(record, by=None, **kw):
    assert store.claim_pending(record["id"])
    return store.apply_match(record, confirmed_by=by, **kw)


# --- registration ----------------------------------------------------------

def test_a_new_player_starts_at_the_opening_rating(fake):
    assert store.ensure_players([A]) == [A]
    assert store.get_player(A)["rating"] == elo.START_RATING
    assert store.get_player(A)["matches"] == 0


def test_registering_twice_changes_nothing(fake):
    store.ensure_players([A])
    store.get_player(A)  # established
    assert store.ensure_players([A, B]) == [B]


def test_an_unregistered_player_reads_as_absent(fake):
    assert store.get_player(A) is None
    assert store.get_players([A, B]) == {}


def test_load_for_match_invents_a_record_rather_than_failing(fake):
    """A crash between the SADD and the HSET would leave a uid with no hash;
    that player must rate as a newcomer, not blow up a confirmation."""
    loaded = store.load_for_match([A])
    assert loaded[A]["rating"] == elo.START_RATING


# --- the pending queue -----------------------------------------------------

def test_a_logged_match_is_parked_not_rated(fake):
    store.ensure_players([A, B])
    record = log([A], [B])
    assert store.get_pending(record["id"])["side_b"] == [B]
    assert fake.rating(A) == elo.START_RATING  # untouched until confirmed


def test_only_one_caller_can_claim_a_pending_match(fake):
    record = log([A], [B])
    assert store.claim_pending(record["id"]) is True
    assert store.claim_pending(record["id"]) is False


def test_pending_ids_are_listed_oldest_first(fake):
    first, second = log([A], [B]), log([A], [C])
    assert [r["id"] for r in store.list_pending()] == [first["id"], second["id"]]


def test_a_pending_record_whose_json_expired_leaves_the_index(fake):
    record = log([A], [B])
    del fake.data[store.pending_key(record["id"])]  # as Redis would on TTL
    assert store.list_pending() == []
    assert fake.data[store.PENDING_KEY] == set()


def test_expiry_is_measured_from_when_it_was_logged(fake):
    now = store.now_ist()
    record = log([A], [B], now=now)
    assert not store.is_expired(record, now + timedelta(hours=store.AUTO_CONFIRM_HOURS - 1))
    assert store.is_expired(record, now + timedelta(hours=store.AUTO_CONFIRM_HOURS))


def test_disputing_removes_every_trace(fake):
    record = log([A], [B])
    store.drop_pending(record["id"])
    assert store.get_pending(record["id"]) is None
    assert store.list_pending() == []


# --- applying --------------------------------------------------------------

def test_confirming_moves_both_ratings_in_opposite_directions(fake):
    blob = confirm(log([A], [B]), by=B)
    assert fake.rating(A) > elo.START_RATING > fake.rating(B)
    assert blob["deltas"][A] == -blob["deltas"][B]
    assert fake.rating(A) == blob["after"][A]


def test_confirming_registers_players_nobody_registered(fake):
    confirm(log([A], [B]), by=B)
    assert sorted(fake.data[store.PLAYERS_KEY]) == [A, B]


def test_the_counters_behind_the_player_card(fake):
    confirm(log([A], [B]), by=B)
    a, b = fake.player(A), fake.player(B)
    assert (a["matches"], a["wins"], a["losses"]) == (1, 1, 0)
    assert (a["games_won"], a["games_lost"]) == (2, 1)
    assert (a["points_won"], a["points_lost"]) == (31, 23)
    assert (b["wins"], b["losses"], b["games_won"]) == (0, 1, 1)
    assert a["peak"] == a["rating"]


def test_a_winning_streak_builds_and_a_loss_resets_it(fake):
    for _ in range(3):
        confirm(log([A], [B]), by=B)
    assert fake.player(A)["streak"] == 3
    confirm(log([A], [B], games=[(5, 11), (7, 11)]), by=B)
    assert fake.player(A)["streak"] == -1
    assert fake.player(A)["best_streak"] == 3


def test_an_even_split_is_a_draw_and_breaks_the_streak(fake):
    confirm(log([A], [B]), by=B)
    confirm(log([A], [B], games=[(11, 7), (7, 11)]), by=B)
    assert fake.player(A)["draws"] == 1
    assert fake.player(A)["streak"] == 0


def test_a_match_is_rated_when_confirmed_not_when_logged(fake):
    """Two matches logged back to back, confirmed in the other order: the second
    confirmation must see the rating the first one produced."""
    first, second = log([A], [B]), log([A], [B])
    later = confirm(second, by=B)
    earlier = confirm(first, by=B)
    assert earlier["before"][A] == later["after"][A]
    assert fake.rating(A) == earlier["after"][A]


def test_a_doubles_match_moves_four_players(fake):
    blob = confirm(log([A, B], [C, D]), by=C)
    assert blob["doubles"] is True
    assert set(blob["deltas"]) == {A, B, C, D}
    assert all(fake.player(u)["matches"] == 1 for u in (A, B, C, D))


def test_history_records_the_match_for_everyone_in_it(fake):
    blob = confirm(log([A], [B]), by=B)
    assert [m["id"] for m in store.recent_matches()] == [blob["id"]]
    assert [m["id"] for m in store.recent_matches(uid=B)] == [blob["id"]]
    assert store.recent_matches(uid=C) == []


def test_history_is_newest_first(fake):
    ids = [confirm(log([A], [B]), by=B)["id"] for _ in range(3)]
    assert [m["id"] for m in store.recent_matches()] == list(reversed(ids))


def test_the_week_counters_follow_the_confirmations(fake):
    blob = confirm(log([A], [B]), by=B)
    delta, played = store.week_movement(blob["week"])
    assert delta[A] == blob["deltas"][A]
    assert played == {A: 1, B: 1}


# --- undo ------------------------------------------------------------------

def test_undo_puts_everything_back_exactly(fake):
    confirm(log([A], [B]), by=B)          # a first match to restore *to*
    before = {u: fake.player(u) for u in (A, B)}
    blob = confirm(log([A], [B]), by=B)
    store.undo_match(blob)
    assert {u: fake.player(u) for u in (A, B)} == before
    assert store.get_match(blob["id"]) is None
    assert store.recent_matches() and store.recent_matches()[0]["id"] != blob["id"]


def test_undo_rewinds_the_week_counters_too(fake):
    blob = confirm(log([A], [B]), by=B)
    store.undo_match(blob)
    delta, played = store.week_movement(blob["week"])
    assert delta == {A: 0, B: 0} and played == {A: 0, B: 0}


def test_undo_is_refused_once_someone_has_played_again(fake):
    blob = confirm(log([A], [B]), by=B)
    confirm(log([A], [C]), by=C)
    ok, reason = store.can_undo(blob)
    assert not ok and f"<@{A}>" in reason


def test_undo_is_allowed_while_the_match_is_still_everyone_s_last(fake):
    blob = confirm(log([A], [B]), by=B)
    assert store.can_undo(blob) == (True, "")


def test_you_can_only_undo_a_match_you_logged(fake):
    mine = confirm(log([A], [B], by=A), by=B)
    confirm(log([C], [D], by=C), by=D)
    assert store.last_match_by(A)["id"] == mine["id"]
    assert store.last_match_by(B) is None
