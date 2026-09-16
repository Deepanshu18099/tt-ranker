"""The whole loop through the Slack handlers: log → confirm → rating moves."""
import json
from datetime import timedelta
from unittest.mock import MagicMock

import pytest

import bot
import elo
import standings
import store
from tests.fake_kv import FakeRedis

A, B, C, D = "U0AAA1", "U0BBB1", "U0CCC1", "U0DDD1"
BOT = "U0BOT01"


@pytest.fixture
def fake():
    redis = FakeRedis()
    with redis.patched():
        yield redis


@pytest.fixture
def client():
    c = MagicMock()
    c.chat_postMessage.return_value = {"channel": "C1", "ts": "1700000000.1"}
    return c


def run(text, client, user=A, respond=None):
    """Drive `/tt <text>` the way Bolt would."""
    respond = respond or MagicMock()
    bot.handle_tt_command(
        MagicMock(), {"user_id": user, "text": text, "channel_id": "C1"},
        respond, client=client, context={"bot_user_id": BOT})
    return respond


def press(action, mid, user, client, respond=None, channel="C1", ts="1700000000.1"):
    respond = respond or MagicMock()
    body = {"user": {"id": user}, "actions": [{"value": mid}],
            "container": {"channel_id": channel, "message_ts": ts}}
    action(body, client, respond)
    return respond


def said(mock):
    """Everything a mock was told to say, as one searchable string.

    ensure_ascii=False so the en-dashes and emoji in the real messages survive
    the round trip and can be asserted on.
    """
    parts = []
    for call in mock.call_args_list:
        parts += [json.dumps(a, default=str, ensure_ascii=False) for a in call.args]
        parts += [json.dumps(v, default=str, ensure_ascii=False)
                  for v in call.kwargs.values()]
    return "\n".join(parts)


def posted_mid(client):
    """The pending id carried by the buttons on the message just posted."""
    blocks = client.chat_postMessage.call_args.kwargs["blocks"]
    actions = next(b for b in blocks if b["type"] == "actions")
    return actions["elements"][0]["value"]


# --- logging ---------------------------------------------------------------

def test_logging_posts_a_prompt_and_moves_nothing_yet(fake, client):
    respond = run(f"log <@{B}> 11-7 9-11 11-5", client)
    text = said(client.chat_postMessage)
    assert f"<@{A}>" in text and f"<@{B}>" in text and "11-7" in text
    assert "Confirm" in text
    assert respond.call_count == 0          # the channel message is the reply
    assert fake.data.get(store.player_key(A)) is None  # nobody rated yet


def test_the_prompt_names_who_has_to_confirm(fake, client):
    run(f"log <@{B}> 11-7 11-9", client)
    assert f"<@{B}> — confirm" in said(client.chat_postMessage)


def test_a_bad_command_explains_itself_privately(fake, client):
    respond = run(f"log <@{B}>", client)
    assert "No game scores" in said(respond)
    assert client.chat_postMessage.call_count == 0


def test_a_channel_it_cannot_post_in_leaves_no_orphan(fake, client):
    client.chat_postMessage.side_effect = Exception("not_in_channel")
    respond = run(f"log <@{B}> 11-7", client)
    assert "invite me" in said(respond)
    assert store.list_pending() == []


# --- confirming ------------------------------------------------------------

def test_the_opponent_confirming_applies_the_rating(fake, client):
    run(f"log <@{B}> 11-7 9-11 11-5", client)
    mid = posted_mid(client)
    press(bot.handle_confirm, mid, B, client)

    assert fake.rating(A) > elo.START_RATING > fake.rating(B)
    updated = said(client.chat_update)
    assert "beat" in updated and str(fake.rating(A)) in updated
    assert store.get_pending(mid) is None


def test_the_prompt_is_replaced_so_the_buttons_cannot_be_pressed_again(fake, client):
    run(f"log <@{B}> 11-7", client)
    press(bot.handle_confirm, posted_mid(client), B, client)
    blocks = client.chat_update.call_args.kwargs["blocks"]
    assert not any(b["type"] == "actions" for b in blocks)


def test_you_cannot_confirm_your_own_result(fake, client):
    run(f"log <@{B}> 11-7 11-9", client)
    respond = press(bot.handle_confirm, posted_mid(client), A, client)
    assert "Only" in said(respond)
    assert store.get_pending(posted_mid(client)) is not None
    assert fake.data.get(store.player_key(A)) is None


def test_a_bystander_cannot_confirm(fake, client):
    run(f"log <@{B}> 11-7", client)
    respond = press(bot.handle_confirm, posted_mid(client), C, client)
    assert "Only" in said(respond)


def test_in_doubles_either_opponent_can_confirm(fake, client):
    run(f"log <@{B}> vs <@{C}> <@{D}> 11-7 11-9", client)
    assert bot.confirmers(store.get_pending(posted_mid(client))) == [C, D]
    press(bot.handle_confirm, posted_mid(client), D, client)
    assert fake.player(A)["matches"] == 1


def test_a_match_logged_by_a_bystander_can_be_confirmed_by_any_player(fake, client):
    run(f"log <@{A}> vs <@{B}> 11-7", client, user=C)
    record = store.get_pending(posted_mid(client))
    assert bot.confirmers(record) == [A, B]
    press(bot.handle_confirm, posted_mid(client), A, client)
    assert fake.player(A)["matches"] == 1


def test_two_people_confirming_at_once_rate_the_match_once(fake, client):
    run(f"log <@{B}> vs <@{C}> <@{D}> 11-7 11-9", client)
    mid = posted_mid(client)
    press(bot.handle_confirm, mid, C, client)
    rating = fake.rating(A)
    respond = press(bot.handle_confirm, mid, D, client)
    assert fake.rating(A) == rating
    assert "already been settled" in said(respond)


def test_confirming_a_vanished_match_says_so(fake, client):
    respond = press(bot.handle_confirm, "999", B, client)
    assert "already been settled" in said(respond)


def test_a_failure_while_rating_leaves_the_match_confirmable(fake, client, monkeypatch):
    run(f"log <@{B}> 11-7", client)
    mid = posted_mid(client)
    monkeypatch.setattr(store, "apply_match", MagicMock(side_effect=RuntimeError("boom")))
    respond = press(bot.handle_confirm, mid, B, client)
    assert "went wrong" in said(respond)
    monkeypatch.undo()
    press(bot.handle_confirm, mid, B, client)   # the retry works
    assert fake.player(A)["matches"] == 1


# --- disputing -------------------------------------------------------------

def test_disputing_throws_the_match_out(fake, client):
    run(f"log <@{B}> 11-7 11-9", client)
    mid = posted_mid(client)
    press(bot.handle_dispute, mid, B, client)
    assert store.get_pending(mid) is None
    assert fake.data.get(store.player_key(A)) is None
    assert "Thrown out" in said(client.chat_update)


def test_the_reporter_can_cancel_their_own_mistake(fake, client):
    run(f"log <@{B}> 11-7", client)
    press(bot.handle_dispute, posted_mid(client), A, client)
    assert store.list_pending() == []


def test_a_bystander_cannot_dispute(fake, client):
    run(f"log <@{B}> 11-7", client)
    respond = press(bot.handle_dispute, posted_mid(client), C, client)
    assert "Only the players" in said(respond)
    assert store.list_pending()


# --- nobody presses anything ----------------------------------------------

def test_an_ignored_match_applies_itself_after_the_window(fake, client):
    run(f"log <@{B}> 11-7 11-9", client)
    mid = posted_mid(client)
    later = store.now_ist() + timedelta(hours=store.AUTO_CONFIRM_HOURS + 1)

    assert standings.sweep_pending(client, now=store.now_ist())["applied"] == []
    result = standings.sweep_pending(client, now=later)

    assert result["applied"] == [mid]
    assert fake.rating(A) > elo.START_RATING
    assert "auto-confirmed" in said(client.chat_update)


def test_the_sweep_leaves_fresh_matches_alone(fake, client):
    run(f"log <@{B}> 11-7", client)
    assert standings.sweep_pending(client)["still_waiting"] == 1
    assert store.list_pending()


def test_a_dry_sweep_changes_nothing(fake, client):
    run(f"log <@{B}> 11-7", client)
    later = store.now_ist() + timedelta(days=2)
    assert standings.sweep_pending(client, now=later, dry_run=True)["applied"]
    assert store.list_pending()          # still there
    assert fake.data.get(store.player_key(A)) is None


# --- the read-only commands ------------------------------------------------

def test_register_then_register_again(fake, client):
    assert str(elo.START_RATING) in said(run("register", client))
    assert "already on the ladder" in said(run("register", client))


def test_the_card_shows_the_record(fake, client):
    run(f"log <@{B}> 11-7 9-11 11-5", client)
    press(bot.handle_confirm, posted_mid(client), B, client)
    card = said(run("me", client))
    assert "1-0" in card and str(fake.rating(A)) in card


def test_the_card_of_a_stranger(fake, client):
    assert "isn't on the ladder" in said(run(f"me <@{C}>", client))


def test_the_board_separates_the_settled_from_the_settling(fake, client):
    for opponent in (B, C, D):
        run(f"log <@{opponent}> 11-7 11-9", client)
        press(bot.handle_confirm, posted_mid(client), opponent, client)
    board = said(run("board", client))
    assert "Still placing" in board and f"<@{A}>" in board


def test_the_board_is_ordered_by_rating(fake, client, monkeypatch):
    monkeypatch.setattr(bot, "PLACEMENT_MATCHES", 1)
    run(f"log <@{B}> 11-2 11-3", client)
    press(bot.handle_confirm, posted_mid(client), B, client)
    board = bot.board_text(store.all_players())
    assert board.index(f"<@{A}>") < board.index(f"<@{B}>")


def test_history_lists_the_match(fake, client):
    run(f"log <@{B}> 11-7 11-9", client)
    press(bot.handle_confirm, posted_mid(client), B, client)
    assert "2–0" in said(run("history", client))


def test_pending_lists_what_is_waiting(fake, client):
    run(f"log <@{B}> 11-7", client)
    listed = said(run("pending", client))
    assert f"#{posted_mid(client)}" in listed and f"<@{B}>" in listed


def test_pending_when_everything_is_settled(fake, client):
    assert "Nothing waiting" in said(run("pending", client))


def test_undo_rolls_the_last_match_back(fake, client):
    run(f"log <@{B}> 11-7 11-9", client)
    press(bot.handle_confirm, posted_mid(client), B, client)
    assert fake.rating(A) > elo.START_RATING

    assert "Undid" in said(run("undo", client))
    assert fake.rating(A) == elo.START_RATING
    assert fake.rating(B) == elo.START_RATING


def test_undo_with_nothing_to_undo(fake, client):
    assert "haven't logged any" in said(run("undo", client))


def test_undo_will_not_erase_a_later_match(fake, client):
    """A undoes their own match, but B has played again since — rewinding B to
    the snapshot would silently wipe that later result too."""
    run(f"log <@{B}> 11-7", client, user=A)
    press(bot.handle_confirm, posted_mid(client), B, client)
    run(f"log <@{C}> 11-9", client, user=B)
    press(bot.handle_confirm, posted_mid(client), C, client)

    rating = fake.rating(A)
    assert "already played another match" in said(run("undo", client, user=A))
    assert fake.rating(A) == rating


def test_odds_reads_the_gap(fake, client):
    store.ensure_players([A, B])
    store.kv.hset(store.player_key(B), "rating", 1400)
    odds = said(run(f"odds <@{B}>", client))
    assert "9%" in odds and "91%" in odds


def test_help_needs_no_database(fake, client):
    assert "TT Ranker" in said(run("help", client))


def test_without_a_database_it_says_so(client, monkeypatch):
    monkeypatch.setattr(bot.kv, "kv_available", lambda: False)
    assert "No database" in said(run("board", client))


def test_an_unexpected_failure_is_not_a_stack_trace(fake, client, monkeypatch):
    monkeypatch.setattr(store, "all_players", MagicMock(side_effect=RuntimeError("boom")))
    assert "went wrong" in said(run("board", client))
