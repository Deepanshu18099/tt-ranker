"""
Elo maths for table tennis — pure functions, no I/O and no Slack.

A *match* here is the whole encounter: several games (11-7, 9-11, 11-5) rated as
ONE update, not one update per game. Rating game-by-game would make a best-of-5
swing ratings far harder than a best-of-3 for the same result, which is not what
a ladder should say.

Three inputs shape the swing:

  S    fraction of games won (2-1 → 0.667). Elo's actual score generalises to any
       value in [0, 1], so a 3-0 sweep moves more than a 3-2 grind.
  E    expected score from the rating gap — the standard logistic curve.
  mov  margin-of-victory multiplier from the point scores, so 11-2 and 11-9 are
       not treated as the same evidence. Log-damped and clamped, because raw
       point margin is noisy and one 11-0 must not rewrite the ladder.

      delta = K · mov · (S − E)

Doubles rates a team at its members' mean rating and moves every member by the
same delta at a reduced K — you only control half of a doubles match, so a
doubles night should not move the ladder as hard as singles.
"""
import math

START_RATING = 1000
RATING_FLOOR = 100  # ratings can sink, but not to something that reads as a bug

# Provisional players move fast so a newcomer reaches their true level in a few
# nights instead of a season; it settles down once we know roughly where they are.
K_PROVISIONAL = 48
K_ESTABLISHED = 32
PROVISIONAL_MATCHES = 20

# You control about half of a doubles match, so it carries about half the
# evidence about *you*. 0.75 rather than 0.5: partners are picked ad hoc here, so
# over many matches a doubles record still says a lot about a player.
DOUBLES_K_FACTOR = 0.75

# mov == 1.0 at this average point margin. Measured on the match total, real
# results cluster at 2–4 points a game (a 3-0 of 11-7 11-9 11-8 is 3.0, a 2-1 is
# lower still because the lost game cancels), so par belongs here. Set it at a
# single game's comfortable margin instead and almost every real match comes out
# damped, which quietly shrinks the whole ladder.
MOV_BASELINE = 4
MOV_MIN, MOV_MAX = 0.6, 1.4

MAX_POINTS = 99  # a game score above this is a typo, not a marathon
MAX_GAMES = 15


def expected(rating_a, rating_b):
    """Probability-ish score side A is expected to take, in [0, 1]. A 400-point
    edge is the classic 10:1 favourite."""
    return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400.0))


def k_factor(matches_played, doubles=False):
    """How hard one match may move a rating.

    Each player brings their own K — a newcomer's rating moves further than the
    veteran's in the very same match. That deliberately breaks strict zero-sum
    (the pool gains a little when a provisional player wins); converging
    newcomers quickly is worth more here than conserving points exactly.
    """
    k = K_PROVISIONAL if matches_played < PROVISIONAL_MATCHES else K_ESTABLISHED
    return k * DOUBLES_K_FACTOR if doubles else float(k)


def mov_multiplier(points_a, points_b, game_count):
    """Scale the swing by how decisive the match was on points.

    Measured on the match total rather than per game, so a 11-1 / 1-11 / 11-1
    thriller is read as the close match it was instead of three blowouts. log
    damps it and the clamp bounds it, so the multiplier stays in a range a player
    can reason about (0.6 for a deuce-fest, 1.4 for a whitewash).
    """
    if game_count <= 0:
        return 1.0
    avg_margin = abs(points_a - points_b) / float(game_count)
    raw = math.log(1.0 + avg_margin) / math.log(1.0 + MOV_BASELINE)
    return min(MOV_MAX, max(MOV_MIN, raw))


def tally(games):
    """(games_a, games_b, points_a, points_b) for a list of (a, b) game scores."""
    games_a = sum(1 for a, b in games if a > b)
    games_b = sum(1 for a, b in games if b > a)
    return games_a, games_b, sum(a for a, _ in games), sum(b for _, b in games)


def _round_half_away(x):
    """Round to int, halves away from zero. Python's round() is banker's
    rounding, which turns a +0.5 swing into 0 and looks like nothing happened."""
    return int(x + 0.5) if x >= 0 else int(x - 0.5)


def team_rating(side):
    """A team is worth its members' mean rating. A 1200 carrying a 900 plays like
    a 1050 pair — beating two 1050s is then par, not an upset."""
    return sum(p["rating"] for p in side) / float(len(side))


def rate_match(side_a, side_b, games):
    """Rate one match and return everything needed to store and narrate it.

    side_a / side_b: [{"uid": str, "rating": int, "matches": int}, …] — one entry
    for singles, two for doubles. `games`: [(a_points, b_points), …].

    Ratings are read from the arguments, so the caller must pass *current*
    ratings: a match is always rated at the moment it is confirmed, never at the
    moment it was typed, or two pending matches confirmed out of order would
    apply stale numbers.
    """
    doubles = len(side_a) > 1
    games_a, games_b, points_a, points_b = tally(games)
    decided = games_a + games_b  # a freak dead-even game counts for neither side

    score_a = 0.5 if decided == 0 else games_a / float(decided)
    exp_a = expected(team_rating(side_a), team_rating(side_b))
    mov = mov_multiplier(points_a, points_b, len(games))

    deltas, before, after = {}, {}, {}
    for side, score, exp in ((side_a, score_a, exp_a),
                             (side_b, 1.0 - score_a, 1.0 - exp_a)):
        for p in side:
            k = k_factor(p["matches"], doubles=doubles)
            rating = int(p["rating"])
            new = max(RATING_FLOOR, rating + _round_half_away(k * mov * (score - exp)))
            before[p["uid"]] = rating
            after[p["uid"]] = new
            # Read the delta back off the floor-clamped result, so the number we
            # report is always the change that actually happened.
            deltas[p["uid"]] = new - rating

    return {
        "doubles": doubles,
        "games_a": games_a, "games_b": games_b,
        "points_a": points_a, "points_b": points_b,
        "score_a": round(score_a, 4),
        "expected_a": round(exp_a, 4),
        "mov": round(mov, 4),
        "deltas": deltas, "before": before, "after": after,
    }


def win_probability(side_a, side_b):
    """Chance side A takes the next game — what `/tt odds` reports."""
    return expected(team_rating(side_a), team_rating(side_b))
