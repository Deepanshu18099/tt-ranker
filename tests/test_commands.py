"""The command list inside /tt help, and what happens when somebody mistypes.

The list is part of help rather than a command of its own: "what can I type?" is
the question people bring to help, and answering it somewhere else means knowing
to go there. It only stays useful if it can't fall behind the parser, which is
most of what is asserted here.
"""
import pytest

import bot
import parsing


# --- the list can't drift --------------------------------------------------

def test_every_command_the_parser_knows_is_on_the_list():
    """The list is hand-written, because a blurb can't be generated — so this
    is the test that stops it quietly falling behind parsing.SUBCOMMANDS."""
    listed = [name for _, entries in bot.QUICK for name, _, _ in entries]
    assert set(listed) == set(parsing.SUBCOMMANDS.values())


def test_no_command_is_listed_twice():
    listed = [name for _, entries in bot.QUICK for name, _, _ in entries]
    assert len(listed) == len(set(listed))


def test_every_usage_example_is_a_command_that_parses():
    """A cheat sheet whose examples don't work is worse than no cheat sheet."""
    for _, entries in bot.QUICK:
        for name, usage, _ in entries:
            sub, _rest = parsing.split_subcommand(f"{name} {usage}".strip())
            assert sub == name, f"/tt {name} {usage} parses as {sub}"


def test_the_admin_group_is_the_commands_that_are_actually_gated():
    admins = {name for group, entries in bot.QUICK if group == "Admins"
              for name, _, _ in entries}
    assert admins == bot.ADMIN_ONLY


# --- who sees what ---------------------------------------------------------

def test_help_leaves_out_what_you_cannot_run(monkeypatch):
    monkeypatch.setenv("TT_ADMINS", "U0BOSS")
    theirs = bot.help_text("U0AAA1")
    assert "/tt board" in theirs
    assert "Admins" not in theirs and "/tt transfer" not in theirs


def test_an_admin_gets_the_padlocked_ones(monkeypatch):
    monkeypatch.setenv("TT_ADMINS", "U0BOSS")
    theirs = bot.help_text("U0BOSS")
    assert "Admins" in theirs and "/tt transfer" in theirs
    assert "/tt board" in theirs          # and everything else as well


def test_help_is_one_answer_and_not_two():
    """The list, how to log, and how the rating works — all of it under the one
    command people already reach for."""
    said = bot.help_text(None)
    assert "/tt log" in said                    # how to log
    assert "/tt titles" in said                 # the generated list
    assert "How the rating works" in said       # the prose
    assert "/tt commands" not in said           # no second command to learn


# --- did you mean ----------------------------------------------------------

@pytest.mark.parametrize("typed,expected", [
    ("boad", "board"),
    ("leaderbord", "board"),
    ("histry", "history"),
    ("accpet", "accept"),
    ("titel", "titles"),
    ("hlep", "help"),
])
def test_a_near_miss_is_guessed(typed, expected):
    assert parsing.suggest(typed)[0] == expected


def test_an_unambiguous_abbreviation_is_taken_at_its_word():
    """`chal` scores badly against `challenge` and reads obviously to a person."""
    assert parsing.suggest("chal") == ["challenge"]


def test_nothing_is_guessed_when_nothing_is_close():
    """A wrong guess is worse than none: it sends someone off to read about a
    command they never wanted."""
    assert parsing.suggest("xyzzy") == []
    assert "Did you mean" not in bot.did_you_mean("xyzzy")


def test_the_answer_to_a_typo_is_not_the_whole_manual():
    answer = bot.did_you_mean("boad")
    assert "`boad`" in answer and "/tt board" in answer
    assert len(answer.splitlines()) <= 3
    assert "How the rating works" not in answer


# --- what the parser hands the dispatcher ----------------------------------

def test_a_typo_is_reported_rather_than_swallowed():
    assert parsing.unknown_verb("boad") == "boad"
    assert parsing.unknown_verb("boad @bob") == "boad"


@pytest.mark.parametrize("text", ["", "board", "help", "<@U0BBB1> 11-7 9-11"])
def test_what_is_not_a_typo_is_left_alone(text):
    """An empty command, a known word, and a bare scoreline are all fine —
    the last one is what people type once they know the bot."""
    assert parsing.unknown_verb(text) == ""


def test_the_aliases_the_footer_promises_are_real():
    for alias, name in (("top", "board"), ("standings", "board"),
                        ("chal", "challenge"), ("oops", "undo")):
        assert parsing.SUBCOMMANDS[alias] == name
