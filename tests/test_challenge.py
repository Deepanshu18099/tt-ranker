"""Challenging someone, and agreeing how long the session runs.

`/tt schedule` states a fact. A challenge is the step before it, where the other
person still gets a say — so nothing reaches the board until they answer, and
what they're answering includes how many games it runs to.

Accepting turns it into an ordinary fixture, which is the point: betting, moving
it and calling it off are all machinery that already exists, and a challenge
never becomes a second kind of scheduled match to keep in step.
"""
from datetime import timedelta
from unittest.mock import MagicMock

import pytest

import betting
import bot
import challenge
import elo
import parsing
import store
from tests.fake_kv import FakeRedis

A, B, C, D = "U0AAA1", "U0BBB1", "U0CCC1", "U0DDD1"


@pytest.fixture
def fake():
    redis = FakeRedis()
    with redis.patched():
        yield redis


def command(text, user=A, channel="C1"):
    return {"user_id": user, "text": text, "channel_id": channel, "trigger_id": "t"}


def said(mock):
    import json
    return "\n".join(json.dumps(a, default=str, ensure_ascii=False)
                     for c in mock.call_args_list
                     for a in list(c.args) + list(c.kwargs.values()))


def issue(side_a=(A,), side_b=(B,), games=3, first_to=2, when=None, by=None):
    return challenge.issue(list(side_a), list(side_b), games, by=by or side_a[0],
                           first_to=first_to, starts_at=when, channel="C1")


# --- saying how long it runs ----------------------------------------------

@pytest.mark.parametrize("text,games,first_to", [
    ("best of 5", 5, 3),
    ("bestof5", 5, 3),
    ("bo7", 7, 4),
    ("best-of-3", 3, 2),
    ("first to 3", 5, 3),
    ("ft2", 3, 2),
    ("5 games", 5, None),
    ("4 matches", 4, None),      # what people here actually call them
    ("1 game", 1, None),
    ("2 sets", 2, None),
])
def test_the_ways_to_say_how_long(text, games, first_to):
    assert parsing.parse_length(text)[:2] == (games, first_to)


def test_no_length_given_is_a_different_fact_from_a_short_one():
    """The caller supplies the default, so "they didn't say" stays visible."""
    assert parsing.parse_length("nothing here")[:2] == (None, None)


def test_best_of_five_means_first_to_three():
    games, first_to, _ = parsing.parse_length("best of 5")
    assert games == 5 and first_to == 3


def test_first_to_three_means_up_to_five_games():
    games, first_to, _ = parsing.parse_length("first to 3")
    assert games == 5 and first_to == 3


def test_the_length_reads_back_the_way_it_was_asked_for():
    assert challenge.length_note({"games": 5, "first_to": 3}) == "Best of 5 — first to 3"
    assert challenge.length_note({"games": 5, "first_to": None}) == "5 games"
    assert challenge.length_note({"games": 1, "first_to": None}) == "One game"


# --- parsing the whole thing ----------------------------------------------

def m(uid):
    return f"<@{uid}>"


def test_a_bare_challenge_takes_the_default_length():
    now = store.now_ist()
    side_a, side_b, games, first_to, when = parsing.parse_challenge(
        m(B), caller=A, now=now, default_games=3)
    assert side_a == [A] and side_b == [B]
    assert (games, first_to, when) == (3, 2, None)


def test_a_time_is_optional_on_a_challenge():
    """Unlike /tt schedule. "Play me some time today" is a real thing to say."""
    now = store.now_ist()
    assert parsing.parse_challenge(m(B), caller=A, now=now)[4] is None
    when = parsing.parse_challenge(f"{m(B)} at 6pm", caller=A, now=now)[4]
    assert when and when.hour == 18


def test_doubles_challenges_split_on_vs():
    now = store.now_ist()
    side_a, side_b, *_ = parsing.parse_challenge(
        f"{m(B)} vs {m(C)} {m(D)}", caller=A, now=now)
    assert side_a == [A, B] and side_b == [C, D]


def test_you_cannot_challenge_yourself():
    now = store.now_ist()
    with pytest.raises(parsing.ParseError):
        parsing.parse_challenge(f"{m(B)} vs {m(A)}", caller=A, now=now)


def test_a_session_longer_than_the_cap_is_refused():
    now = store.now_ist()
    with pytest.raises(parsing.ParseError, match=str(elo.MAX_GAMES)):
        parsing.parse_challenge(f"{m(B)} {elo.MAX_GAMES + 1} games",
                                caller=A, now=now)


def test_a_clock_time_already_gone_today_means_tomorrow():
    """Challenging someone at 11am when it is noon is an invitation for
    tomorrow, not an error — parse_when rolls a bare clock time forward, and a
    challenge has no reason to disagree with the scheduler about that."""
    now = store.now_ist().replace(hour=12, minute=0)
    when = parsing.parse_challenge(f"{m(B)} at 11am", caller=A, now=now)[4]
    assert when > now and when.hour == 11
    assert when.date() == (now + timedelta(days=1)).date()


def test_a_date_beyond_the_horizon_is_refused():
    now = store.now_ist()
    with pytest.raises(parsing.ParseError, match="days out"):
        parsing.parse_challenge(f"{m(B)} in {parsing.MAX_LEAD_DAYS * 24 + 48}h",
                                caller=A, now=now)


# --- the record ------------------------------------------------------------

def test_a_challenge_starts_open_and_is_listed(fake):
    record = issue()
    assert record["state"] == "open"
    assert [r["id"] for r in challenge.live()] == [record["id"]]


def test_only_the_challenged_side_may_answer(fake):
    record = issue(side_a=[A], side_b=[B])
    assert challenge.may_answer(record, B)
    assert not challenge.may_answer(record, A)     # that's just /tt schedule
    assert not challenge.may_answer(record, C)


def test_the_challenger_may_take_it_back(fake):
    record = issue(side_a=[A], side_b=[B])
    assert challenge.may_withdraw(record, A)
    assert not challenge.may_withdraw(record, B)


def test_only_one_challenge_stands_between_two_sides(fake):
    issue(side_a=[A], side_b=[B])
    assert challenge.open_between([A], [B])
    assert challenge.open_between([B], [A]), "either way round is the same pair"
    assert not challenge.open_between([A], [C])


def test_answering_frees_the_pair_to_challenge_again(fake):
    record = issue(side_a=[A], side_b=[B])
    challenge.claim(record["id"])
    challenge.decline(record, B)
    assert not challenge.open_between([A], [B])


def test_only_one_person_can_answer_a_challenge(fake):
    """Two of a doubles pair pressing Accept at once would otherwise put two
    fixtures up for the same match."""
    record = issue(side_a=[A], side_b=[C, D])
    assert challenge.claim(record["id"]) is True
    assert challenge.claim(record["id"]) is False


# --- accepting -------------------------------------------------------------

def test_accepting_puts_a_fixture_up(fake):
    now = store.now_ist()
    record = issue(side_a=[A], side_b=[B], games=5, first_to=3)
    fixture = challenge.accept(record, B, now=now)
    assert fixture["side_a"] == [A] and fixture["side_b"] == [B]
    assert betting.get(fixture["id"])["state"] == "open"
    assert record["state"] == "accepted" and record["fixture"] == fixture["id"]


def test_the_agreed_length_is_carried_onto_the_fixture(fake):
    record = issue(games=5, first_to=3)
    fixture = challenge.accept(record, B)
    assert fixture["note"] == "Best of 5 — first to 3"


def test_a_challenge_with_a_time_keeps_it(fake):
    now = store.now_ist()
    when = now + timedelta(hours=3)
    record = issue(when=when)
    fixture = challenge.accept(record, B, now=now)
    assert betting.starts_at(fixture) == when.replace(microsecond=0)


def test_a_challenge_with_no_time_starts_shortly_after_it_is_accepted(fake):
    now = store.now_ist()
    record = issue(when=None)
    fixture = challenge.accept(record, B, now=now)
    assert betting.starts_at(fixture) > now


def test_a_time_that_has_gone_by_while_it_sat_unanswered_is_pushed_out(fake):
    """Otherwise accepting would open a fixture that is already due, and
    betting would shut the instant it appeared."""
    now = store.now_ist()
    record = issue(when=now + timedelta(minutes=10))
    later = now + timedelta(hours=2)
    fixture = challenge.accept(record, B, now=later)
    assert betting.starts_at(fixture) > later
    assert fixture["state"] == "open"


def test_the_fixture_can_then_be_bet_on_like_any_other(fake):
    """The whole reason accepting makes a fixture rather than a third thing."""
    record = issue()
    fixture = challenge.accept(record, B)
    ok, _ = betting.place_bet(fixture, C, "a", 50)
    assert ok and betting.pool(fixture["id"])["total"] == 50


# --- declining, withdrawing, expiring --------------------------------------

def test_declining_closes_it_without_a_fixture(fake):
    record = issue()
    challenge.claim(record["id"])
    challenge.decline(record, B)
    assert record["state"] == "declined"
    assert betting.live() == []


def test_withdrawing_closes_it_too(fake):
    record = issue()
    challenge.claim(record["id"])
    challenge.withdraw(record, A)
    assert challenge.get(record["id"])["state"] == "withdrawn"


def test_an_unanswered_challenge_expires(fake):
    now = store.now_ist()
    record = challenge.issue([A], [B], 3, by=A, now=now)
    assert not challenge.is_expired(record, now + timedelta(hours=1))
    assert challenge.is_expired(
        record, now + timedelta(hours=challenge.EXPIRE_HOURS + 1))


def test_an_answered_challenge_never_expires(fake):
    now = store.now_ist()
    record = challenge.issue([A], [B], 3, by=A, now=now)
    challenge.decline(record, B, now)
    assert not challenge.is_expired(
        record, now + timedelta(hours=challenge.EXPIRE_HOURS + 1))


def test_the_sweep_closes_stale_challenges(fake):
    import standings
    now = store.now_ist()
    fresh = challenge.issue([A], [B], 3, by=A, now=now)
    stale = challenge.issue([C], [D], 3, by=C,
                            now=now - timedelta(hours=challenge.EXPIRE_HOURS + 2))
    out = standings.sweep_challenges(MagicMock(), now=now)
    assert out["expired"] == [stale["id"]]
    assert challenge.get(stale["id"])["state"] == "expired"
    assert challenge.get(fresh["id"])["state"] == "open"


# --- the ratings on it -----------------------------------------------------

def test_the_challenge_carries_both_ratings(fake):
    """A challenge is a claim about which of two numbers is better, so the
    numbers are on it."""
    store.ensure_players([A, B])
    players = store.get_players([A, B])
    line = bot.challenge_line(issue(), players=players)
    assert f"<@{A}> `{elo.START_RATING}`" in line
    assert f"<@{B}> `{elo.START_RATING}`" in line


def test_a_player_with_no_record_still_shows_a_rating(fake):
    """They are rated — at the opening rating, which is a fact, not a blank."""
    line = bot.challenge_line(issue(), players={})
    assert f"`{elo.START_RATING}`" in line


def test_the_favourite_is_named_from_the_ratings(fake):
    players = {A: {"rating": 1300}, B: {"rating": 1000}}
    line = bot.favourite_line([A], [B], players)
    assert f"<@{A}>" in line and "%" in line


def test_an_even_match_is_called_even(fake):
    players = {A: {"rating": 1005}, B: {"rating": 1000}}
    assert "Too close to call" in bot.favourite_line([A], [B], players)


def test_the_doubles_favourite_is_read_off_the_pair(fake):
    players = {A: {"rating": 1200}, B: {"rating": 1200},
               C: {"rating": 900}, D: {"rating": 900}}
    assert f"<@{A}>" in bot.favourite_line([A, B], [C, D], players)


def test_the_channel_post_shows_the_ratings_and_the_odds(fake):
    store.ensure_players([A, B])
    blocks = bot.challenge_blocks(issue())
    flat = " ".join(b["text"]["text"] if b["type"] == "section"
                    else " ".join(e["text"] for e in b["elements"])
                    for b in blocks)
    assert f"`{elo.START_RATING}`" in flat and "Too close to call" in flat


# --- the Slack routes ------------------------------------------------------

def test_the_command_posts_and_dms_the_buttons(fake):
    respond, client = MagicMock(), MagicMock()
    client.chat_postMessage.return_value = {"ts": "1", "channel": "C1"}
    bot.handle_challenge(command(f"challenge {m(B)} best of 5"), respond, client)
    channels = [c.kwargs["channel"] for c in client.chat_postMessage.call_args_list]
    assert "C1" in channels, "the channel sees the callout"
    assert B in channels, "the challenged side gets the buttons"
    assert A in channels, "the challenger gets a way to take it back"


def test_the_channel_post_carries_no_buttons(fake):
    """Same rule as a pending result: the channel reads it, it doesn't rule."""
    respond, client = MagicMock(), MagicMock()
    client.chat_postMessage.return_value = {"ts": "1", "channel": "C1"}
    bot.handle_challenge(command(f"challenge {m(B)}"), respond, client)
    posted = next(c for c in client.chat_postMessage.call_args_list
                  if c.kwargs["channel"] == "C1")
    assert not any(b["type"] == "actions" for b in posted.kwargs["blocks"])


def test_a_bare_challenge_command_explains_itself(fake):
    respond = MagicMock()
    bot.handle_challenge(command("challenge"), respond, MagicMock())
    assert "best of 5" in said(respond)


def test_a_second_challenge_between_the_same_pair_is_refused(fake):
    respond, client = MagicMock(), MagicMock()
    client.chat_postMessage.return_value = {"ts": "1", "channel": "C1"}
    bot.handle_challenge(command(f"challenge {m(B)}"), respond, client)
    bot.handle_challenge(command(f"challenge {m(B)} bo7"), respond, client)
    assert "already an open challenge" in said(respond)


def _press(action, cid, user):
    return {"user": {"id": user}, "trigger_id": "t",
            "actions": [{"action_id": action, "value": cid}]}


def test_accepting_by_button_puts_the_fixture_up(fake):
    record = issue(side_a=[A], side_b=[B])
    client, respond = MagicMock(), MagicMock()
    client.chat_postMessage.return_value = {"ts": "9", "channel": "C1"}
    bot.handle_challenge_button(_press(bot.ACCEPT_ACTION, record["id"], B),
                                client, respond)
    assert challenge.get(record["id"])["state"] == "accepted"
    assert len(betting.live()) == 1


def test_the_challenger_cannot_accept_their_own(fake):
    record = issue(side_a=[A], side_b=[B])
    respond = MagicMock()
    bot.handle_challenge_button(_press(bot.ACCEPT_ACTION, record["id"], A),
                                MagicMock(), respond)
    assert "Only" in said(respond)
    assert challenge.get(record["id"])["state"] == "open"
    assert betting.live() == []


def test_a_bystander_cannot_answer(fake):
    record = issue(side_a=[A], side_b=[B])
    respond = MagicMock()
    bot.handle_challenge_button(_press(bot.DECLINE_ACTION, record["id"], C),
                                MagicMock(), respond)
    assert challenge.get(record["id"])["state"] == "open"


def test_declining_by_button_closes_it(fake):
    record = issue(side_a=[A], side_b=[B])
    bot.handle_challenge_button(_press(bot.DECLINE_ACTION, record["id"], B),
                                MagicMock(), MagicMock())
    assert challenge.get(record["id"])["state"] == "declined"
    assert betting.live() == []


def test_the_challenger_can_take_it_back(fake):
    record = issue(side_a=[A], side_b=[B])
    bot.handle_challenge_button(_press(bot.WITHDRAW_ACTION, record["id"], A),
                                MagicMock(), MagicMock())
    assert challenge.get(record["id"])["state"] == "withdrawn"


def test_answering_twice_is_refused(fake):
    record = issue(side_a=[A], side_b=[B])
    bot.handle_challenge_button(_press(bot.DECLINE_ACTION, record["id"], B),
                                MagicMock(), MagicMock())
    respond = MagicMock()
    bot.handle_challenge_button(_press(bot.ACCEPT_ACTION, record["id"], B),
                                MagicMock(), respond)
    assert "already declined" in said(respond)


def test_the_typed_route_works_when_the_dm_never_arrived(fake):
    record = issue(side_a=[A], side_b=[B])
    client, respond = MagicMock(), MagicMock()
    client.chat_postMessage.return_value = {"ts": "9", "channel": "C1"}
    bot.handle_answer_command(command(f"accept {record['id']}", user=B),
                              respond, client)
    assert challenge.get(record["id"])["state"] == "accepted"


def test_accept_with_no_number_lists_what_is_waiting_on_you(fake):
    record = issue(side_a=[A], side_b=[B])
    respond = MagicMock()
    bot.handle_answer_command(command("accept", user=B), respond, MagicMock())
    assert f"#{record['id']}" in said(respond)


def test_the_challenges_list_shows_what_is_open(fake):
    record = issue(side_a=[A], side_b=[B], games=5, first_to=3)
    respond = MagicMock()
    bot.handle_challenges(command("challenges"), respond)
    out = said(respond)
    assert f"#{record['id']}" in out and "Best of 5" in out
