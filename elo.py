"""
Elo maths for table tennis — pure functions, no I/O and no Slack.

**Every game is rated on its own, and they add up.** A session runs as long as
people have time for, so its length is information, not noise: winning 8 of 10
is a far stronger claim than winning 2 of 3, and rating the encounter as one
unit would throw that away. Ten games move a rating about three times as far as
three games, and a session that splits evenly moves nobody.

Each game contributes:

    K · mov · upset · (won ? 1 : 0  −  E)

  E      expected score from the rating gap — the standard logistic curve,
         fixed for the whole session so the result can't depend on the order
         the games happened to be typed in.
  mov    margin of victory for *that game*, log-damped and clamped, so 11-2
         and 11-9 are not the same evidence.
  upset  the correction below: a favourite is *expected* to win big, so their
         blowout says less than an underdog's.

Losses in a session cancel wins, so the whole thing reduces to "how much better
did you do than expected". Winning narrowly against someone far below you can
still cost rating — you were expected to win by more, and that is the model
working rather than a bug.

Doubles rates a team at its members' mean rating and moves every member by the
same amount at a reduced K — you only control half of a doubles match.
"""
import math

START_RATING = 1000
RATING_FLOOR = 100  # ratings can sink, but not to something that reads as a bug

# Per *game*, not per session. Calibrated so a typical three-game session lands
# where the old session-based numbers did, while longer sessions scale up.
K_PROVISIONAL = 16
K_ESTABLISHED = 11
# Counted in games rather than sessions, because a session is any length.
PROVISIONAL_GAMES = 50

# You control about half of a doubles match, so it carries about half the
# evidence about *you*: your partner's play is in every result, and none of it
# is yours.
DOUBLES_K_FACTOR = 0.5

# The margin curve is calibrated on a game to 11: mov == 1.0 at a 4-point margin,
# which is a normal, clearly-won 11-7.
MOV_BASELINE = 4
REFERENCE_GAME = 11
# Longer games spread scores out — winning a game to 21 by 4 is close, while the
# same 4 points in a game to 11 is comfortable. Margins are rescaled to their
# game-to-11 equivalent before the curve sees them, so the same curve serves
# 11s, 21s and first-to-7 without three sets of constants.
MIN_GAME = 7  # floor on the divisor, so a freak 2-0 can't read as a whitewash
# Above 1, the curve spreads out: a whitewash moves ~2.9x a deuce-fest instead of
# ~2x. This is the knob for "how much should the scoreline matter".
MOV_GAIN = 1.5
MOV_MIN, MOV_MAX = 0.45, 1.75

# A favourite is expected to win by a lot, so a big win tells us less about them
# than the same win would about an underdog. Without this, rating gaps quietly
# inflate the strong (the standard margin-of-victory autocorrelation problem).
UPSET_SCALE = 2.2
UPSET_GAP_CAP = 800  # keeps the denominator far from zero, which would flip signs

MAX_POINTS = 99  # a game score above this is a typo, not a marathon
MAX_GAMES = 25   # sessions are any length; this is only a fat-finger guard


def expected(rating_a, rating_b):
    """Probability-ish score side A is expected to take in one game, in [0, 1].
    A 400-point edge is the classic 10:1 favourite."""
    return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400.0))


def k_factor(games_played, doubles=False):
    """How hard one *game* may move a rating.

    Each player brings their own K — a newcomer's rating moves further than the
    veteran's in the very same game. That deliberately breaks strict zero-sum
    (the pool gains a little when a provisional player wins); converging
    newcomers quickly is worth more here than conserving points exactly.
    """
    k = K_PROVISIONAL if games_played < PROVISIONAL_GAMES else K_ESTABLISHED
    return k * DOUBLES_K_FACTOR if doubles else float(k)


def mov_multiplier(margin, winner_points=None):
    """Scale one game's swing by how decisively it was won.

    `winner_points` is the winning score, used to read the margin *relative to
    the game being played*: 21-17 and 11-9 are both "won by about a fifth of the
    game" and should count the same, even though one margin is 4 and the other 2.
    Omit it and the margin is taken at face value, i.e. as a game to 11.

    log damps it and the clamp bounds it, so the multiplier stays in a range a
    player can reason about — roughly 0.5 for a deuce, 1.75 for a whitewash.
    """
    m = abs(margin)
    if winner_points:
        m *= REFERENCE_GAME / float(max(abs(winner_points), MIN_GAME))
    raw = math.log(1.0 + m) / math.log(1.0 + MOV_BASELINE)
    return min(MOV_MAX, max(MOV_MIN, raw ** MOV_GAIN))


def upset_correction(winner_gap):
    """Damp a favourite's big win, amplify an underdog's.

    `winner_gap` is the game winner's rating minus the loser's — positive when
    the favourite won. Capped before use: the denominator would reach zero at a
    gap of −2200 and then go negative, which would flip the sign of the whole
    update and hand the loser the points.
    """
    gap = max(-UPSET_GAP_CAP, min(UPSET_GAP_CAP, winner_gap))
    return UPSET_SCALE / (gap * 0.001 + UPSET_SCALE)


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


def games_played(player):
    """Games, not sessions — what K and the provisional period are measured in."""
    return int(player.get("games_won", 0)) + int(player.get("games_lost", 0))


def session_weight(rating_a, rating_b, games):
    """Σ over games of `mov · upset · (result − E)`, from side A's point of view.

    This is the whole rating signal; a player's change is just their own K times
    this. Side B's weight is exactly the negative of it — same mov, same upset
    correction, and (1−result) − (1−E) == −(result − E) — which is what keeps
    the model zero-sum for players on the same K.
    """
    exp_a = expected(rating_a, rating_b)
    total = 0.0
    for a, b in games:
        if a == b:
            continue  # a dead-even game decided nothing
        won_a = a > b
        gap = (rating_a - rating_b) if won_a else (rating_b - rating_a)
        weight = mov_multiplier(a - b, max(a, b)) * upset_correction(gap)
        total += weight * ((1.0 if won_a else 0.0) - exp_a)
    return total


def rate_match(side_a, side_b, games):
    """Rate one session and return everything needed to store and narrate it.

    side_a / side_b: [{"uid": str, "rating": int, "games": int}, …] — one entry
    for singles, two for doubles. `games`: [(a_points, b_points), …], any length.

    Ratings are read from the arguments, so the caller must pass *current*
    ratings: a session is always rated at the moment it is confirmed, never at
    the moment it was typed, or two sessions confirmed out of order would apply
    stale numbers.
    """
    doubles = len(side_a) > 1
    games_a, games_b, points_a, points_b = tally(games)
    rating_a, rating_b = team_rating(side_a), team_rating(side_b)

    exp_a = expected(rating_a, rating_b)
    weight_a = session_weight(rating_a, rating_b, games)
    decided = games_a + games_b

    deltas, before, after = {}, {}, {}
    for side, weight in ((side_a, weight_a), (side_b, -weight_a)):
        for p in side:
            k = k_factor(p.get("games", 0), doubles=doubles)
            rating = int(p["rating"])
            new = max(RATING_FLOOR, rating + _round_half_away(k * weight))
            before[p["uid"]] = rating
            after[p["uid"]] = new
            # Read the delta back off the floor-clamped result, so the number we
            # report is always the change that actually happened.
            deltas[p["uid"]] = new - rating

    return {
        "doubles": doubles,
        "games_a": games_a, "games_b": games_b,
        "points_a": points_a, "points_b": points_b,
        "score_a": round(games_a / float(decided), 4) if decided else 0.5,
        "expected_a": round(exp_a, 4),
        "weight_a": round(weight_a, 4),
        # Mean margin multiplier across the session — informational only.
        "mov": round(sum(mov_multiplier(a - b, max(a, b)) for a, b in games)
                     / len(games), 4) if games else 1.0,
        "deltas": deltas, "before": before, "after": after,
    }


def win_probability(side_a, side_b):
    """Chance side A takes the next game — what `/tt odds` reports."""
    return expected(team_rating(side_a), team_rating(side_b))
