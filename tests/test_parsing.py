"""The `/tt` grammar — mostly about what people will actually type."""
import pytest

import parsing

ME, BOB, CAL, DEE = "U0ME001", "U0BOB1", "U0CAL1", "U0DEE1"


def m(uid, label=None):
    return f"<@{uid}|{label}>" if label else f"<@{uid}>"


def parse(text, caller=ME, **kw):
    return parsing.parse_match(text, caller=caller, **kw)


# --- sides -----------------------------------------------------------------

def test_singles_without_vs_is_you_against_them():
    r = parse(f"{m(BOB)} 11-7 9-11 11-5")
    assert r["side_a"] == [ME] and r["side_b"] == [BOB]
    assert r["games"] == [(11, 7), (9, 11), (11, 5)]


def test_doubles_names_your_partner_before_vs():
    r = parse(f"{m(BOB)} vs {m(CAL)} {m(DEE)} 11-7 11-9")
    assert r["side_a"] == [ME, BOB] and r["side_b"] == [CAL, DEE]


def test_explicit_sides_record_a_match_you_were_not_in():
    r = parse(f"{m(BOB)} {m(CAL)} vs {m(DEE)} <@U0EVE1> 11-7 11-9", caller="U0SCOR1")
    assert r["side_a"] == [BOB, CAL] and r["side_b"] == [DEE, "U0EVE1"]


def test_you_are_not_added_to_a_match_you_already_appear_in():
    r = parse(f"{m(ME)} vs {m(BOB)} 11-7")
    assert r["side_a"] == [ME] and r["side_b"] == [BOB]


def test_vs_with_nobody_in_front_still_means_you():
    assert parse(f"vs {m(BOB)} 11-7")["side_a"] == [ME]


def test_mention_labels_and_punctuation_are_tolerated():
    r = parse(f"{m(BOB, 'bob.smith')}, 11-7, 9-11.")
    assert r["side_b"] == [BOB] and r["games"] == [(11, 7), (9, 11)]


def test_the_bot_is_not_a_player():
    r = parse(f"<@U0BOT01> {m(BOB)} 11-7", bot_id="U0BOT01")
    assert r["side_b"] == [BOB]


def test_a_player_mentioned_twice_counts_once():
    r = parse(f"{m(BOB)} {m(BOB)} 11-7")
    assert r["side_b"] == [BOB]


# --- scores ----------------------------------------------------------------

@pytest.mark.parametrize("text", ["11-7", "11 - 7", "11:7", "11 : 7", "11–7"])
def test_score_separators(text):
    assert parse(f"{m(BOB)} {text}")["games"] == [(11, 7)]


def test_games_to_twenty_one_still_work():
    assert parse(f"{m(BOB)} 21-19 18-21 21-15")["games"] == [(21, 19), (18, 21), (21, 15)]


def test_one_game_is_enough():
    assert parse(f"{m(BOB)} 11-9")["games"] == [(11, 9)]


def test_stray_words_are_ignored():
    r = parse(f"beat {m(BOB)} today 11-7 and 11-9 in the kitchen")
    assert r["games"] == [(11, 7), (11, 9)] and r["side_b"] == [BOB]


# --- rejections ------------------------------------------------------------

@pytest.mark.parametrize("text,fragment", [
    ("11-7 9-11", "who played"),                      # nobody mentioned
    ("<@U0BOB1>", "No game scores"),                   # no scores
    ("<@U0BOB1> 11-11", "has to win"),                 # a tie is not a finished game
    ("<@U0BOB1> <@U0CAL1> 11-7", "Uneven sides"),       # 1 v 2 without vs
    ("<@U0ME001> 11-7", "both sides"),                   # playing yourself
    ("<@U0BOB1> <@U0CAL1> <@U0DEE1> vs <@U0EVE1> <@U0FFF1> <@U0GGG1> 11-7", "more than two a side"),
])
def test_bad_input_explains_itself(text, fragment):
    with pytest.raises(parsing.ParseError) as e:
        parse(text)
    assert fragment in str(e.value)


def test_absurd_scores_are_rejected():
    with pytest.raises(parsing.ParseError, match="out of range"):
        parse(f"{m(BOB)} 99-100")


def test_too_many_games_is_a_typo():
    with pytest.raises(parsing.ParseError, match="typo"):
        parse(f"{m(BOB)} " + " ".join(["11-7"] * (parsing.elo.MAX_GAMES + 1)))


# --- subcommands -----------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("log <@U0BOB1> 11-7", "log"),
    ("add <@U0BOB1> 11-7", "log"),
    ("board", "board"),
    ("leaderboard", "board"),
    ("TOP", "board"),
    ("me", "me"),
    ("stats <@U0BOB1>", "me"),
    ("undo", "undo"),
    ("history", "history"),
    ("pending", "pending"),
    ("odds <@U0BOB1>", "odds"),
    ("", "help"),
    ("   ", "help"),
    ("what is this", "help"),
])
def test_subcommand_aliases(text, expected):
    assert parsing.split_subcommand(text)[0] == expected


def test_the_log_verb_is_optional_once_you_know_the_bot():
    sub, rest = parsing.split_subcommand("<@U0BOB1> 11-7 9-11")
    assert sub == "log"
    assert parse(rest)["games"] == [(11, 7), (9, 11)]


def test_the_verb_is_stripped_before_the_players():
    sub, rest = parsing.split_subcommand("log <@U0BOB1> 11-7")
    assert sub == "log" and rest == "<@U0BOB1> 11-7"


# --- odds ------------------------------------------------------------------

def test_odds_needs_no_scores():
    assert parsing.parse_odds(f"{m(BOB)}", caller=ME) == ([ME], [BOB])
    assert parsing.parse_odds(f"{m(BOB)} vs {m(CAL)} {m(DEE)}", caller=ME) == \
        ([ME, BOB], [CAL, DEE])


# --- deuce -----------------------------------------------------------------

@pytest.mark.parametrize("score,expected", [
    ("11-9", (11, 9)), ("13-11", (13, 11)), ("15-13", (15, 13)),
    ("18-16", (18, 16)), ("21-19", (21, 19)), ("25-23", (25, 23)),
])
def test_deuce_and_extended_deuce_scores_are_accepted(score, expected):
    """A game can go to deuce repeatedly — 25-23 is a real table tennis score."""
    assert parse(f"{m(BOB)} {score}")["games"] == [expected]


def test_a_whole_session_of_deuce_games():
    r = parse(f"{m(BOB)} 12-10 15-13 18-16 11-13 21-19")
    assert r["games"] == [(12, 10), (15, 13), (18, 16), (11, 13), (21, 19)]


def test_win_by_two_is_not_enforced():
    """Office rules vary — some play straight to 11, some first to 7. Rejecting
    anything that isn't win-by-two would throw out legitimate casual scores."""
    assert parse(f"{m(BOB)} 11-10")["games"] == [(11, 10)]
    assert parse(f"{m(BOB)} 7-5")["games"] == [(7, 5)]


def test_a_skunk_score_is_accepted():
    """11-0 ends the game under the house rule, so it's a real final score."""
    assert parse(f"{m(BOB)} 11-0")["games"] == [(11, 0)]
    assert parse(f"{m(BOB)} 21-14 11-0 21-16")["games"] == [(21, 14), (11, 0), (21, 16)]
    assert parse(f"{m(BOB)} 0-11")["games"] == [(0, 11)]


# --- days ------------------------------------------------------------------

from datetime import datetime, timedelta  # noqa: E402

import store  # noqa: E402

NOON = datetime(2026, 9, 17, 12, 30, tzinfo=store.IST)


def test_today_is_midnight_to_midnight():
    label, start, end = parsing.parse_day("today", NOON)
    assert label == "today"
    assert start == datetime(2026, 9, 17, tzinfo=store.IST)
    assert end - start == timedelta(days=1)


def test_yesterday_is_the_day_before():
    label, start, end = parsing.parse_day("yesterday", NOON)
    assert (label, start.day, end.day) == ("yesterday", 16, 17)


def test_week_is_the_last_seven_days_including_today():
    label, start, end = parsing.parse_day("week", NOON)
    assert label == "this week"
    assert start == datetime(2026, 9, 11, tzinfo=store.IST)
    assert end == datetime(2026, 9, 18, tzinfo=store.IST)


@pytest.mark.parametrize("text", ["2026-09-16", "16/9", "16/09/2026", "16.9.26"])
def test_a_date_is_read_in_the_formats_people_type(text):
    label, start, _ = parsing.parse_day(text, NOON)
    assert start.date().isoformat() == "2026-09-16"
    assert label == "yesterday"   # it happens to be, and the label should say so


def test_a_date_further_back_is_labelled_as_a_date():
    label, start, _ = parsing.parse_day("2026-09-01", NOON)
    assert label == "1 Sep"
    label, _, _ = parsing.parse_day("2025-09-01", NOON)
    assert label == "1 Sep 2025"


@pytest.mark.parametrize("text", ["", "tomorrow", "11-7", "2026-13-40", "31/2"])
def test_nonsense_is_not_a_day(text):
    assert parsing.parse_day(text, NOON) is None


def test_the_day_can_sit_anywhere_in_the_command():
    assert parsing.split_day("<@U1> today") == ("today", "<@U1>")
    assert parsing.split_day("today <@U1>") == ("today", "<@U1>")
    assert parsing.split_day("<@U1> this week") == ("thisweek", "<@U1>")
    assert parsing.split_day("<@U1>") == ("", "<@U1>")


def test_a_score_is_never_mistaken_for_a_date():
    assert parsing.split_day("<@U1> 11-7 9-11") == ("", "<@U1> 11-7 9-11")
