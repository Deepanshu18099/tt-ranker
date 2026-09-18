"""Titles: who holds what, and why it is never stored."""
import json

import pytest

import awards
import betting
import kv
import store
from tests.fake_kv import FakeRedis

A, B, C, D = "U0AAA1", "U0BBB1", "U0CCC1", "U0DDD1"


@pytest.fixture
def fake():
    redis = FakeRedis()
    with redis.patched():
        yield redis


def player(**kw):
    base = {"rating": 1000, "wins": 0, "losses": 0, "draws": 0, "games_won": 0,
            "games_lost": 0, "peak": 1000, "streak": 0, "best_streak": 0,
            "matches": 0, "points_won": 0, "points_lost": 0}
    base.update(kw)
    return base


def match(side_a, side_b, games_a=2, games_b=0):
    return {"side_a": list(side_a), "side_b": list(side_b),
            "games_a": games_a, "games_b": games_b}


def week(*results):
    return list(results)


def play(a, b, games=((11, 5), (11, 6)), now=None):
    record = store.create_pending([a], [b], list(games), logged_by=a, now=now)
    assert store.claim_pending(record["id"])
    return store.apply_match(record, confirmed_by=b, now=now)


# --- the table -------------------------------------------------------------

def test_the_hottest_and_coldest_weeks_are_opposite_ends_of_the_same_list():
    players = {A: player(), B: player(), C: player()}
    table = awards.compute(players, week(
        match([A], [B]), match([A], [B]), match([A], [C]),
        match([C], [B]), match([C], [B]), match([B], [C], 2, 0)))
    assert table["hot"] == A          # 3 from 3
    assert table["cold"] == B         # 1 from 4


def test_a_week_too_thin_to_judge_awards_nothing():
    """One match is not a week. The floor is the whole point of the title."""
    players = {A: player(), B: player()}
    table = awards.compute(players, week(match([A], [B])))
    assert "hot" not in table and "cold" not in table


def test_turning_up_is_its_own_title():
    players = {A: player(), B: player(), C: player()}
    table = awards.compute(players, week(
        match([A], [B]), match([A], [C]), match([A], [B]), match([A], [C]),
        match([B], [C])))
    assert table["machine"] == A      # 4 to B's 3 and C's 3


def test_the_all_time_title_is_a_rate_not_a_pile():
    """Otherwise it is only ever held by whoever has played most."""
    players = {A: player(games_won=9, games_lost=1),        # 90%, 10 games
               B: player(games_won=40, games_lost=40)}      # 50%, 80 games
    assert awards.compute(players, [])["untouchable"] == A


def test_too_few_games_is_not_a_record():
    players = {A: player(games_won=2, games_lost=0),
               B: player(games_won=5, games_lost=1)}
    assert awards.compute(players, [])["untouchable"] == B


def test_the_richest_wallet_takes_a_title_once_one_has_moved():
    players = {A: player(), B: player()}
    start = betting.START_SPINS
    assert "moneybags" not in awards.compute(players, [], {A: start, B: start})
    assert awards.compute(players, [], {A: start + 900, B: start})["moneybags"] == A


def test_a_dead_heat_leaves_the_title_unheld():
    """Joint On Fire is not a thing anyone says, and a badge nobody can claim
    uniquely is worse than no badge."""
    players = {A: player(), B: player(), C: player(), D: player()}
    table = awards.compute(players, week(
        match([A], [C]), match([A], [C]), match([A], [C]),
        match([B], [D]), match([B], [D]), match([B], [D])))
    assert "hot" not in table         # A and B both 3 from 3, both on 3 matches


def test_a_thinner_week_loses_the_tie():
    players = {A: player(), B: player(), C: player(), D: player()}
    table = awards.compute(players, week(
        match([A], [C]), match([A], [C]), match([A], [C]), match([A], [C]),
        match([B], [D]), match([B], [D]), match([B], [D])))
    assert table["hot"] == A          # both perfect, A played more


def test_somebody_not_on_the_ladder_cannot_hold_a_title():
    """A match blob outlives a player record; a title should not."""
    table = awards.compute({A: player()}, week(
        match([A], [B]), match([A], [B]), match([B], [A], 2, 0)))
    assert table.get("cold") != B


def test_a_player_can_wear_more_than_one():
    players = {A: player(games_won=9, games_lost=1), B: player(), C: player()}
    table = awards.compute(players, week(
        match([A], [B]), match([A], [B]), match([A], [C])))
    assert awards.by_player(table)[A] == ["hot", "machine", "untouchable"]


def test_nobody_is_both_on_fire_and_ice_cold():
    """With one qualifying player they are the best *and* the worst week of the
    seven days, and wearing both badges at once makes a joke of each."""
    players = {A: player(), B: player(), C: player()}
    table = awards.compute(players, week(
        match([A], [B]), match([A], [B]), match([A], [C])))
    assert table["hot"] == A and "cold" not in table


def test_every_title_is_listed_even_when_nobody_holds_it():
    rows = awards.holder_rows({"hot": A})
    assert len(rows) == len(awards.TITLES)
    assert dict((t.key, uid) for t, uid in rows)["moneybags"] == ""


# --- the cache -------------------------------------------------------------

def test_the_table_is_cached_and_the_cache_is_used(fake):
    store.ensure_players([A, B])
    for _ in range(3):
        play(A, B)
    first = awards.current()
    assert first["hot"] == A
    # Rewritten by hand: if the next read comes back with this, it was cached.
    kv.set_(store.TITLES_KEY, json.dumps({"hot": B}))
    assert awards.current()["hot"] == B
    assert awards.current(fresh=True)["hot"] == A


def test_applying_a_match_drops_the_cache(fake):
    """A title has to be able to change hands on the result that changes it."""
    store.ensure_players([A, B, C])
    for _ in range(3):
        play(A, B)
    assert awards.current()["hot"] == A
    assert kv.get(store.TITLES_KEY)
    for _ in range(4):
        play(C, A)
    assert kv.get(store.TITLES_KEY) is None
    assert awards.current()["hot"] == C


def test_undoing_a_match_drops_it_too(fake):
    store.ensure_players([A, B])
    for _ in range(3):
        play(A, B)
    blob = play(A, B)
    awards.current()
    store.undo_match(blob)
    assert kv.get(store.TITLES_KEY) is None


def test_a_corrupt_cache_is_recomputed_rather_than_raised(fake):
    store.ensure_players([A, B])
    for _ in range(3):
        play(A, B)
    kv.set_(store.TITLES_KEY, "{not json")
    assert awards.current()["hot"] == A


def test_the_week_is_the_rolling_seven_days(fake):
    """The same week /tt history week means. A title that only changed hands at
    midnight on Sunday would be a dead thing by Wednesday."""
    from datetime import timedelta
    now = store.now_ist()
    store.ensure_players([A, B, C])
    for _ in range(3):
        play(A, B, now=now - timedelta(days=30))     # long out of the window
    for _ in range(3):
        play(C, B, now=now)
    start, end = awards.week_window(now)
    table = awards.compute(store.all_players(), store.matches_in(start, end))
    assert table["hot"] == C
