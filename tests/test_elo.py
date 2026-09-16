"""The rating maths. This is the part players will argue about, so the
properties they'd argue from are asserted directly."""
import pytest

import elo


def P(uid, rating=1000, matches=50):
    return {"uid": uid, "rating": rating, "matches": matches}


def rate(a, b, games):
    return elo.rate_match([a] if isinstance(a, dict) else a,
                          [b] if isinstance(b, dict) else b, games)


SWEEP = [(11, 2), (11, 4), (11, 3)]
TIGHT_SWEEP = [(12, 10), (11, 9), (13, 11)]
CLOSE_WIN = [(11, 7), (9, 11), (11, 5)]


# --- expectation -----------------------------------------------------------

def test_equal_ratings_are_a_coin_flip():
    assert elo.expected(1000, 1000) == pytest.approx(0.5)


def test_four_hundred_points_is_the_classic_ten_to_one():
    assert elo.expected(1400, 1000) == pytest.approx(10 / 11, abs=1e-6)


def test_expectations_sum_to_one():
    assert elo.expected(1180, 1247) + elo.expected(1247, 1180) == pytest.approx(1.0)


# --- margin of victory -----------------------------------------------------

def test_mov_is_one_at_a_normal_margin():
    """Par is 4 points a game across the match — roughly a 3-0 of 11-7s. A real
    3-0 (11-7 11-9 11-8) sits just under; a whitewash well over."""
    assert elo.mov_multiplier(33, 21, 3) == pytest.approx(1.0)
    assert elo.mov_multiplier(33, 24, 3) < 1.0 < elo.mov_multiplier(33, 9, 3)


def test_mov_rises_with_the_margin_and_stays_clamped():
    squeaker = elo.mov_multiplier(36, 30, 3)
    blowout = elo.mov_multiplier(33, 9, 3)
    assert elo.MOV_MIN <= squeaker < 1.0 < blowout <= elo.MOV_MAX
    assert elo.mov_multiplier(99, 0, 1) == elo.MOV_MAX
    assert elo.mov_multiplier(11, 10, 1) == elo.MOV_MIN


def test_mov_reads_the_match_not_the_loudest_game():
    """11-1 / 1-11 / 11-1 was a close match, not three blowouts — measuring on
    the match total lets the swings cancel the way they actually did."""
    swingy = elo.mov_multiplier(23, 13, 3)
    consistent = elo.mov_multiplier(33, 9, 3)
    assert swingy < consistent


# --- singles ---------------------------------------------------------------

def test_winner_gains_exactly_what_the_loser_drops():
    r = rate(P("a"), P("b"), CLOSE_WIN)
    assert r["deltas"]["a"] == -r["deltas"]["b"]
    assert r["deltas"]["a"] > 0


def test_a_whitewash_beats_a_squeaker():
    sweep = rate(P("a"), P("b"), SWEEP)["deltas"]["a"]
    tight = rate(P("a"), P("b"), TIGHT_SWEEP)["deltas"]["a"]
    assert sweep > tight > 0


def test_winning_three_nil_beats_winning_two_one():
    three_nil = rate(P("a"), P("b"), TIGHT_SWEEP)["deltas"]["a"]
    two_one = rate(P("a"), P("b"), CLOSE_WIN)["deltas"]["a"]
    assert three_nil > two_one > 0


def test_beating_someone_stronger_is_worth_more():
    upset = rate(P("a", 900), P("b", 1300), SWEEP)["deltas"]["a"]
    expected_win = rate(P("a", 1300), P("b", 900), SWEEP)["deltas"]["a"]
    assert upset > expected_win > 0


def test_losing_to_someone_stronger_costs_less():
    to_better = rate(P("a", 900), P("b", 1300), [(2, 11), (4, 11)])["deltas"]["a"]
    to_worse = rate(P("a", 1300), P("b", 900), [(2, 11), (4, 11)])["deltas"]["a"]
    assert to_worse < to_better < 0


def test_an_even_split_between_equals_moves_nobody():
    r = rate(P("a"), P("b"), [(11, 7), (7, 11)])
    assert r["deltas"] == {"a": 0, "b": 0}
    assert r["score_a"] == 0.5


def test_provisional_players_move_faster():
    new = rate(P("a", matches=0), P("b", matches=0), SWEEP)["deltas"]["a"]
    old = rate(P("a", matches=99), P("b", matches=99), SWEEP)["deltas"]["a"]
    assert new > old > 0
    assert elo.k_factor(0) == elo.K_PROVISIONAL
    assert elo.k_factor(elo.PROVISIONAL_MATCHES) == elo.K_ESTABLISHED


def test_a_single_game_is_a_valid_match():
    r = rate(P("a"), P("b"), [(11, 6)])
    assert r["games_a"] == 1 and r["games_b"] == 0
    assert r["deltas"]["a"] > 0


def test_rating_never_falls_through_the_floor():
    r = rate(P("a", elo.RATING_FLOOR), P("b", 2000), [(0, 11), (0, 11)])
    assert r["after"]["a"] == elo.RATING_FLOOR
    # the reported drop is the drop that happened, not the one we wanted
    assert r["deltas"]["a"] == 0


# --- doubles ---------------------------------------------------------------

def test_doubles_rates_the_pair_at_their_average():
    assert elo.team_rating([P("a", 1200), P("b", 900)]) == 1050


def test_a_doubles_result_moves_all_four_players():
    r = rate([P("a1", 1200), P("a2", 900)], [P("b1", 1030), P("b2", 1010)], SWEEP)
    assert set(r["deltas"]) == {"a1", "a2", "b1", "b2"}
    assert r["deltas"]["a1"] == r["deltas"]["a2"] > 0
    assert r["deltas"]["b1"] == r["deltas"]["b2"] < 0
    assert r["doubles"] is True


def test_doubles_conserves_the_rating_pool():
    r = rate([P("a1", 1200), P("a2", 900)], [P("b1", 1030), P("b2", 1010)], CLOSE_WIN)
    assert sum(r["deltas"].values()) == 0


def test_doubles_counts_for_less_than_singles():
    doubles = rate([P("a1"), P("a2")], [P("b1"), P("b2")], SWEEP)["deltas"]["a1"]
    singles = rate(P("a1"), P("b1"), SWEEP)["deltas"]["a1"]
    assert 0 < doubles < singles


def test_carrying_a_weaker_partner_is_worth_little():
    """1200+900 beating two 1050s is par, so it barely moves; the same pair
    beating two 1200s is an upset and moves plenty."""
    par = rate([P("a1", 1200), P("a2", 900)], [P("b1", 1050), P("b2", 1050)], SWEEP)
    upset = rate([P("a1", 1200), P("a2", 900)], [P("b1", 1200), P("b2", 1200)], SWEEP)
    assert upset["deltas"]["a1"] > par["deltas"]["a1"] > 0


# --- tallying --------------------------------------------------------------

def test_tally_counts_games_and_points():
    assert elo.tally(CLOSE_WIN) == (2, 1, 31, 23)


def test_score_is_the_share_of_games_won():
    assert rate(P("a"), P("b"), CLOSE_WIN)["score_a"] == pytest.approx(2 / 3, abs=1e-3)
