"""The rating maths. This is the part players will argue about, so the
properties they'd argue from are asserted directly."""
import pytest

import elo


def P(uid, rating=1000, games=200):
    """A player. `games` drives K — 200 is comfortably out of the provisional
    period, so most tests here compare established players."""
    return {"uid": uid, "rating": rating, "games": games}


def rate(a, b, games):
    return elo.rate_match([a] if isinstance(a, dict) else a,
                          [b] if isinstance(b, dict) else b, games)


def gain(a, b, games, who=None):
    r = rate(a, b, games)
    return r["deltas"][who or (a if isinstance(a, dict) else a[0])["uid"]]


SWEEP = [(11, 2), (11, 4), (11, 3)]          # 3-0, decisive
NORMAL = [(11, 7), (11, 9), (11, 8)]         # 3-0, ordinary
TIGHT = [(12, 10), (11, 9), (13, 11)]        # 3-0, every game a deuce
CLOSE_WIN = [(11, 7), (9, 11), (11, 5)]      # 2-1


# --- expectation -----------------------------------------------------------

def test_equal_ratings_are_a_coin_flip():
    assert elo.expected(1000, 1000) == pytest.approx(0.5)


def test_four_hundred_points_is_the_classic_ten_to_one():
    assert elo.expected(1400, 1000) == pytest.approx(10 / 11, abs=1e-6)


def test_expectations_sum_to_one():
    assert elo.expected(1180, 1247) + elo.expected(1247, 1180) == pytest.approx(1.0)


# --- margin of victory -----------------------------------------------------

def test_mov_is_one_at_a_normal_game_margin():
    assert elo.mov_multiplier(elo.MOV_BASELINE) == pytest.approx(1.0)


def test_mov_rises_with_the_margin_and_stays_clamped():
    assert elo.mov_multiplier(2) < elo.mov_multiplier(4) < elo.mov_multiplier(9)
    assert elo.mov_multiplier(1) == elo.MOV_MIN
    assert elo.mov_multiplier(99) == elo.MOV_MAX


def test_mov_ignores_which_side_won():
    """It scales the size of the swing; `expected` decides the direction."""
    assert elo.mov_multiplier(-7) == elo.mov_multiplier(7)


def test_a_whitewash_moves_about_three_times_a_deuce_fest():
    """The margin knob, stated as the ratio players will actually notice."""
    sweep, tight = gain(P("a"), P("b"), SWEEP), gain(P("a"), P("b"), TIGHT)
    assert 2.5 < sweep / tight < 3.3


# --- the upset correction --------------------------------------------------

def test_the_upset_correction_is_neutral_between_equals():
    assert elo.upset_correction(0) == pytest.approx(1.0)


def test_a_favourites_big_win_counts_for_less_than_an_underdogs():
    assert elo.upset_correction(400) < 1.0 < elo.upset_correction(-400)


def test_the_correction_can_never_flip_the_sign_of_an_update():
    """Its denominator reaches zero at a gap of -2200; unclamped, anything past
    that would hand the points to the loser."""
    assert elo.upset_correction(-100000) > 0
    assert elo.upset_correction(100000) > 0


# --- every game is rated on its own ----------------------------------------

def test_more_games_move_a_rating_further():
    """The point of per-game scoring: a long session is more evidence, so it
    counts for more. Sessions are whatever length people had time for."""
    three = gain(P("a"), P("b"), [(11, 7)] * 3)
    ten = gain(P("a"), P("b"), [(11, 7)] * 10)
    assert ten > three > 0
    assert 3.0 < ten / three < 3.7          # roughly linear in games played


def test_a_session_that_splits_evenly_moves_nobody():
    r = rate(P("a"), P("b"), [(11, 7)] * 5 + [(7, 11)] * 5)
    assert r["deltas"] == {"a": 0, "b": 0}


def test_losses_inside_a_session_cancel_wins():
    ten_nil = gain(P("a"), P("b"), [(11, 7)] * 10)
    seven_three = gain(P("a"), P("b"), [(11, 7)] * 7 + [(7, 11)] * 3)
    assert ten_nil > seven_three > 0


def test_a_swingy_session_is_read_as_the_close_thing_it_was():
    """11-1 / 1-11 / 11-1 is a close session, not three blowouts — the lost game
    cancels most of what the won ones earned."""
    swingy = gain(P("a"), P("b"), [(11, 1), (1, 11), (11, 1)])
    consistent = gain(P("a"), P("b"), SWEEP)
    assert 0 < swingy < consistent


def test_a_single_game_is_a_valid_session():
    r = rate(P("a"), P("b"), [(11, 6)])
    assert (r["games_a"], r["games_b"]) == (1, 0)
    assert r["deltas"]["a"] > 0


# --- singles ---------------------------------------------------------------

def test_winner_gains_exactly_what_the_loser_drops():
    r = rate(P("a"), P("b"), CLOSE_WIN)
    assert r["deltas"]["a"] == -r["deltas"]["b"] > 0


@pytest.mark.parametrize("games", [SWEEP, NORMAL, TIGHT, CLOSE_WIN, [(11, 7)] * 12])
@pytest.mark.parametrize("ra,rb", [(1000, 1400), (1000, 1000), (1300, 900), (700, 1500)])
def test_the_pool_is_conserved_whatever_the_result(games, ra, rb):
    assert sum(rate(P("a", ra), P("b", rb), games)["deltas"].values()) == 0


def test_a_whitewash_beats_a_squeaker():
    assert gain(P("a"), P("b"), SWEEP) > gain(P("a"), P("b"), TIGHT) > 0


def test_winning_three_nil_beats_winning_two_one_at_the_same_margins():
    """Like for like. A 3-0 of three deuces is a genuinely closer session than a
    2-1 of comfortable wins, and the model is allowed to say so."""
    assert gain(P("a"), P("b"), NORMAL) > gain(P("a"), P("b"), CLOSE_WIN) > 0


def test_beating_someone_stronger_is_worth_more():
    assert gain(P("a", 900), P("b", 1300), SWEEP) > gain(P("a", 1300), P("b", 900), SWEEP) > 0


def test_losing_to_someone_stronger_costs_less():
    to_better = gain(P("a", 900), P("b", 1300), [(2, 11), (4, 11)])
    to_worse = gain(P("a", 1300), P("b", 900), [(2, 11), (4, 11)])
    assert to_worse < to_better < 0


def test_scraping_past_someone_far_below_you_can_cost_rating():
    """Not a bug: you were expected to take about 9 games in 10, and 2-1 is
    well short of that. The README says so in as many words."""
    assert gain(P("a", 1400), P("b", 1000), CLOSE_WIN) < 0


def test_provisional_players_move_faster():
    new = gain(P("a", games=0), P("b", games=0), NORMAL)
    old = gain(P("a", games=500), P("b", games=500), NORMAL)
    assert new > old > 0
    assert elo.k_factor(0) == elo.K_PROVISIONAL
    assert elo.k_factor(elo.PROVISIONAL_GAMES) == elo.K_ESTABLISHED


def test_the_provisional_period_is_counted_in_games():
    assert elo.games_played({"games_won": 12, "games_lost": 9}) == 21
    assert elo.games_played({}) == 0


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
    doubles = gain([P("a1"), P("a2")], [P("b1"), P("b2")], SWEEP, who="a1")
    singles = gain(P("a1"), P("b1"), SWEEP)
    assert 0 < doubles < singles


def test_carrying_a_weaker_partner_is_worth_little():
    """1200+900 beating two 1050s is par, so it barely moves; the same pair
    beating two 1200s is an upset and moves plenty."""
    par = gain([P("a1", 1200), P("a2", 900)], [P("b1", 1050), P("b2", 1050)], SWEEP, "a1")
    upset = gain([P("a1", 1200), P("a2", 900)], [P("b1", 1200), P("b2", 1200)], SWEEP, "a1")
    assert upset > par > 0


# --- tallying --------------------------------------------------------------

def test_tally_counts_games_and_points():
    assert elo.tally(CLOSE_WIN) == (2, 1, 31, 23)


def test_score_is_the_share_of_games_won():
    assert rate(P("a"), P("b"), CLOSE_WIN)["score_a"] == pytest.approx(2 / 3, abs=1e-3)


# --- deuce and game length ------------------------------------------------

def test_every_deuce_game_lands_near_the_floor():
    """Won by the minimum two, whatever the format and however long it ran."""
    for hi, lo in ((11, 9), (13, 11), (18, 16), (21, 19), (25, 23), (31, 29)):
        assert elo.mov_multiplier(hi - lo, hi) <= elo.mov_multiplier(2, elo.REFERENCE_GAME)


def test_the_same_margin_is_closer_in_a_longer_game():
    """Two points is 18% of a game to 11 but under 10% of a game to 21, so
    21-19 is the tighter result and has to count as one."""
    assert elo.mov_multiplier(2, 21) < elo.mov_multiplier(2, 11)
    assert elo.mov_multiplier(4, 21) < elo.mov_multiplier(4, 11)


def test_proportionally_equal_games_score_alike():
    """A game to 21 is rated on the same curve as a game to 11 once its margin
    is read relative to the game being played — no second set of constants."""
    for (a1, b1), (a2, b2) in (((11, 7), (21, 13)), ((11, 9), (21, 17)),
                               ((11, 2), (21, 4))):
        assert abs(elo.mov_multiplier(a1 - b1, a1)
                   - elo.mov_multiplier(a2 - b2, a2)) < 0.06


def test_the_eleven_point_calibration_is_untouched():
    """Rescaling must not have quietly moved the numbers everything else was
    tuned against."""
    assert elo.mov_multiplier(elo.MOV_BASELINE, 11) == pytest.approx(1.0)
    assert elo.mov_multiplier(4) == elo.mov_multiplier(4, 11)


def test_a_freak_short_score_cannot_read_as_a_whitewash():
    """Without a floor on the divisor, a 2-0 would rescale to an 11-0."""
    assert elo.mov_multiplier(2, 2) < elo.MOV_MAX
    assert elo.mov_multiplier(2, 2) == elo.mov_multiplier(2, elo.MIN_GAME)


def test_a_session_of_deuce_battles_barely_moves_anyone():
    deuces = gain(P("a"), P("b"), [(12, 10), (15, 13), (18, 16)])
    routine = gain(P("a"), P("b"), NORMAL)
    assert 0 < deuces < routine


def test_points_totals_are_recorded_but_do_not_drive_the_rating():
    """The maths reads per-game margins; the totals are for the player card."""
    r = rate(P("a"), P("b"), [(21, 19)])
    assert r["points_a"] == 21 and r["points_b"] == 19
    assert r["deltas"]["a"] > 0


def test_twenty_one_point_games_are_rated_sensibly_end_to_end():
    """The format actually being played: a 2-1 nets to about one clean win, and
    a 3-0 to roughly three."""
    two_one = gain(P("a"), P("b"), [(21, 19), (21, 14), (16, 21)])
    three_nil = gain(P("a"), P("b"), [(21, 19), (21, 14), (21, 16)])
    one_nil = gain(P("a"), P("b"), [(21, 17)])
    assert 0 < two_one < three_nil
    assert three_nil > 2 * one_nil


# --- the skunk rule (11-0 ends the game) ----------------------------------

def test_a_skunk_is_the_most_decisive_result_there_is():
    """House rule: reach 11-0 and the game is over. Its winning score is 11, so
    it reads as a complete game-to-11 whitewash rather than a half-played game
    to 21 — which is what it is."""
    assert elo.mov_multiplier(11, 11) == elo.MOV_MAX
    assert elo.mov_multiplier(11, 11) >= elo.mov_multiplier(19, 21)   # vs 21-2


def test_a_skunk_beats_a_normal_win_by_about_double():
    assert gain(P("a"), P("b"), [(11, 0)]) > gain(P("a"), P("b"), [(21, 13)]) > 0


def test_a_skunk_mixes_into_a_longer_session(fake=None):
    """One game ending early doesn't disturb the others in the same session."""
    with_skunk = gain(P("a"), P("b"), [(21, 14), (11, 0), (21, 16)])
    without = gain(P("a"), P("b"), [(21, 14), (21, 13), (21, 16)])
    assert with_skunk > without > 0


def test_losing_a_skunk_costs_the_most():
    assert gain(P("a"), P("b"), [(0, 11)]) < gain(P("a"), P("b"), [(13, 21)]) < 0


def test_a_skunk_still_conserves_the_pool():
    r = rate(P("a", 1200), P("b", 900), [(11, 0)])
    assert sum(r["deltas"].values()) == 0
