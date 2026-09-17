"""The shared pieces — chiefly the promises they make to a reader who can't see
the colours."""
from web import components as c

NAMES = {"U0BOB": "Bob", "U0X": "Bob Smith", "U0Y": ""}


# --- identity ---------------------------------------------------------------

def test_a_monogram_is_one_letter_for_one_name_and_two_for_two():
    assert c.initials("Bob") == "B"
    assert c.initials("Bob Smith") == "BS"


def test_a_player_with_no_name_still_gets_a_monogram():
    """The page falls back to @E092 for someone Slack never named; the avatar
    has to survive that rather than render an empty circle."""
    assert c.initials(c.display_name("U08V0KSE092", {})) == "E"


def test_an_avatar_keeps_its_colour():
    assert c.avatar("U0BOB", NAMES) == c.avatar("U0BOB", NAMES)


def test_an_avatar_is_not_read_out_twice():
    """The name is always beside it, so the monogram is decorative."""
    assert 'aria-hidden="true"' in c.avatar("U0BOB", NAMES)


def test_a_name_is_escaped_wherever_it_lands():
    hostile = {"U0BOB": '<script>alert(1)</script>'}
    assert "<script>" not in c.avatar("U0BOB", hostile)


# --- never colour alone -----------------------------------------------------

def test_a_rise_carries_a_glyph_and_a_sentence():
    up = c.movement(36, 2)
    assert "&#9650;" in up and "+36" in up and "rating gained this week" in up


def test_a_fall_carries_a_glyph_and_a_sentence():
    down = c.movement(-12, 3)
    assert "&#9660;" in down and "-12" in down and "rating lost this week" in down


def test_level_and_did_not_play_are_different_sentences():
    assert "level" in c.movement(0, 4) and "no games" in c.movement(0, 0)


def test_the_compact_form_still_says_which_week_to_a_screen_reader():
    short = c.movement(0, 0, compact=True)
    assert "no games" in short and 'class="sr-only"> this week' in short


def test_rank_movement_names_the_direction():
    assert "places up this week" in c.rank_move(2)
    assert "places down this week" in c.rank_move(-1)
    assert c.rank_move(0) == ""


def test_form_is_letters_first_and_spelled_out_for_a_reader():
    strip = c.form_strip("WWDLW")
    assert strip.count("form-cell") == 5
    assert "won, won, drew, lost, won" in strip


# --- streaks ----------------------------------------------------------------

def test_a_streak_starts_at_three():
    assert c.streak_badge(2) == "" and c.streak_badge(-2) == ""
    assert "3W streak" in c.streak_badge(3)
    assert "4 win streak" in c.streak_badge(4, long=True)


def test_a_cold_streak_is_named_not_just_coloured():
    assert "3L streak" in c.streak_badge(-3)
    assert "streak cold" in c.streak_badge(-3)


# --- match card -------------------------------------------------------------

def blob(**kw):
    base = {"side_a": ["U0BOB"], "side_b": ["U0X"], "games_a": 2, "games_b": 1,
            "games": [[11, 7], [9, 11], [11, 5]], "deltas": {"U0BOB": 7, "U0X": -7},
            "applied_at": "2026-09-17T17:53:00+05:30"}
    base.update(kw)
    return base


def test_a_card_marks_the_winner_in_words():
    card = c.match_card(blob(), NAMES)
    assert "winner" in card and "Singles" in card


def test_a_drawn_card_crowns_nobody():
    card = c.match_card(blob(games_a=1, games_b=1), NAMES)
    assert "winner" not in card and ">Drawn<" in card


def test_a_doubles_card_names_all_four():
    card = c.match_card(blob(side_a=["U0BOB", "U0X"], side_b=["U0Y", "U0Z"],
                             doubles=True, deltas={}), {**NAMES, "U0Z": "Zed"})
    assert "Doubles" in card and card.count('class="side-name"') == 4


def test_every_game_is_still_there():
    card = c.match_card(blob(), NAMES)
    assert "11&#8211;7" in card and "9&#8211;11" in card and "11&#8211;5" in card


def test_a_match_too_old_for_a_timestamp_still_renders():
    assert "<time" not in c.match_card(blob(applied_at=""), NAMES)


# --- empty states -----------------------------------------------------------

def test_an_empty_state_says_what_to_do_next():
    out = c.empty_state("No matches yet", "Your first rally is waiting.",
                        "Log the first match", "#how")
    assert "No matches yet" in out and "Log the first match" in out
    assert "no data" not in out.lower()
