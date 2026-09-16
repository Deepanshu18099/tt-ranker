"""The whole loop through the Slack handlers: log → confirm → rating moves."""
import itertools
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
    """Echoes back the channel it was posted to, so a channel post and each
    verdict DM are distinguishable. (Real Slack returns a D-id for a DM rather
    than the user id; the code stores whatever comes back either way.)"""
    c = MagicMock()
    counter = itertools.count(1)
    c.chat_postMessage.side_effect = lambda **kw: {
        "channel": kw.get("channel", "C1"), "ts": f"1700000000.{next(counter)}"}
    return c


def run(text, client, user=A, respond=None):
    """Drive `/tt <text>` the way Bolt would. trigger_id is always present on a
    real slash command and is what opens the form."""
    respond = respond or MagicMock()
    bot.handle_tt_command(
        MagicMock(), {"user_id": user, "text": text, "channel_id": "C1",
                      "trigger_id": "tid.1"},
        respond, client=client, context={"bot_user_id": BOT})
    return respond


def press(action, mid, user, client, respond=None, channel="C1", ts="1700000000.1",
          ephemeral=False):
    respond = respond or MagicMock()
    container = {"channel_id": channel, "message_ts": ts}
    if ephemeral:
        container["is_ephemeral"] = True   # as a press from /tt pending arrives
    action({"user": {"id": user}, "actions": [{"value": mid}],
            "container": container}, client, respond)
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


def posts(client):
    return client.chat_postMessage.call_args_list


def channel_post(client):
    """The most recent message that went to a channel, not a verdict DM."""
    for c in reversed(posts(client)):
        if str(c.kwargs.get("channel", "")).startswith("C"):
            return c
    return None


def dm_to(client, uid):
    """The most recent verdict DM sent to one person, or None."""
    for c in reversed(posts(client)):
        if c.kwargs.get("channel") == uid:
            return c
    return None


def buttons_in(call):
    if call is None:
        return []
    for b in call.kwargs.get("blocks") or []:
        if b.get("type") == "actions":
            return [e["action_id"] for e in b["elements"]]
    return []


def posted_mid(client):
    """The pending id on the most recently posted message carrying buttons."""
    for c in reversed(posts(client)):
        for b in c.kwargs.get("blocks") or []:
            if b.get("type") == "actions":
                return b["elements"][0]["value"]
    raise AssertionError("no message carried buttons")


# --- logging ---------------------------------------------------------------

def test_logging_posts_a_prompt_and_moves_nothing_yet(fake, client):
    respond = run(f"log <@{B}> 11-7 9-11 11-5", client)
    text = said(client.chat_postMessage)
    assert f"<@{A}>" in text and f"<@{B}>" in text and "11-7" in text
    assert "Confirm" in text
    assert respond.call_count == 0          # the channel message is the reply
    assert fake.data.get(store.player_key(A)) is None  # nobody rated yet


def test_the_channel_post_names_who_the_verdict_went_to(fake, client):
    run(f"log <@{B}> 11-7 11-9", client)
    assert f"Sent to <@{B}> to confirm" in said(client.chat_postMessage)


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
    monkeypatch.setattr(bot, "PLACEMENT_GAMES", 1)
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


# --- auto-registration on joining the channel ------------------------------

def joined(channel, user, client, context=None):
    bot.handle_member_joined({"channel": channel, "user": user}, client=client,
                             context=context if context is not None else {"bot_user_id": BOT})


def test_joining_the_home_channel_puts_you_on_the_ladder(fake, client, monkeypatch):
    monkeypatch.setattr(bot, "HOME_CHANNEL", "C_TT")
    joined("C_TT", B, client)
    assert store.get_player(B)["rating"] == elo.START_RATING
    dm = said(client.chat_postMessage)
    assert f"<@{B}>" in dm and "Welcome" in dm
    assert client.chat_postMessage.call_args.kwargs["channel"] == B   # a DM, not the channel


def test_joining_some_other_channel_does_nothing(fake, client, monkeypatch):
    """The bot being invited somewhere busy for one match must not enrol that
    channel's whole membership."""
    monkeypatch.setattr(bot, "HOME_CHANNEL", "C_TT")
    joined("C_RANDOM", B, client)
    assert store.get_player(B) is None
    assert client.chat_postMessage.call_count == 0


def test_the_bot_joining_is_not_a_new_player(fake, client, monkeypatch):
    monkeypatch.setattr(bot, "HOME_CHANNEL", "C_TT")
    joined("C_TT", BOT, client)
    assert store.get_player(BOT) is None


def test_rejoining_does_not_welcome_you_twice(fake, client, monkeypatch):
    """Slack retries event deliveries; ensure_players only reports genuinely new
    uids, so the second delivery is silent."""
    monkeypatch.setattr(bot, "HOME_CHANNEL", "C_TT")
    joined("C_TT", B, client)
    joined("C_TT", B, client)
    assert client.chat_postMessage.call_count == 1


def test_a_failed_welcome_dm_still_registers_the_player(fake, client, monkeypatch):
    monkeypatch.setattr(bot, "HOME_CHANNEL", "C_TT")
    client.chat_postMessage.side_effect = Exception("cannot_dm_bot")
    joined("C_TT", B, client)
    assert store.get_player(B)["rating"] == elo.START_RATING


def test_auto_registration_is_off_without_a_home_channel(fake, client, monkeypatch):
    monkeypatch.setattr(bot, "HOME_CHANNEL", "")
    joined("C_TT", B, client)
    assert store.get_player(B) is None


# --- /tt sync --------------------------------------------------------------

def members(client, *uids, pages=None):
    """Stub conversations.members, optionally paginated."""
    if pages:
        client.conversations_members.side_effect = [
            {"members": page, "response_metadata": {"next_cursor": cur}}
            for page, cur in pages]
    else:
        client.conversations_members.return_value = {"members": list(uids)}


def test_sync_backfills_everyone_already_in_the_channel(fake, client):
    members(client, A, B, C, BOT)
    out = said(run("sync", client))
    assert "Added *3*" in out and f"<@{C}>" in out
    assert sorted(store.all_players()) == sorted([A, B, C])   # not the bot


def test_sync_a_second_time_adds_nobody(fake, client):
    members(client, A, B)
    run("sync", client)
    assert "already on the ladder" in said(run("sync", client))


def test_sync_follows_slack_pagination(fake, client):
    members(client, pages=[([A, B], "cur1"), ([C, D], "")])
    run("sync", client)
    assert sorted(store.all_players()) == sorted([A, B, C, D])


def test_sync_says_what_to_fix_when_it_cannot_read_the_channel(fake, client):
    client.conversations_members.side_effect = Exception("missing_scope")
    out = said(run("sync", client))
    assert "channels:read" in out and "missing_scope" in out
    assert store.all_players() == {}


def test_sync_mentions_auto_registration_only_in_the_home_channel(fake, client, monkeypatch):
    members(client, A, B)
    monkeypatch.setattr(bot, "HOME_CHANNEL", "C1")     # run() posts from C1
    assert "automatically" in said(run("sync", client))
    monkeypatch.setattr(bot, "HOME_CHANNEL", "C_OTHER")
    members(client, C, D)
    assert "automatically" not in said(run("sync", client))


# --- the guided form -------------------------------------------------------

def submit(state, client, user=A, channel="C1", respond=None):
    ack = MagicMock()
    bot.handle_log_modal(ack, {"user": {"id": user}},
                         {"state": {"values": state}, "private_metadata": channel},
                         client=client)
    return ack


def form_state(side_a, side_b, games):
    return {"side_a": {"v": {"selected_users": side_a}},
            "side_b": {"v": {"selected_users": side_b}},
            "games": {"v": {"value": games}}}


def test_a_bare_log_opens_the_form(fake, client):
    run("log", client)
    view = client.views_open.call_args.kwargs["view"]
    assert view["callback_id"] == bot.LOG_MODAL
    assert view["private_metadata"] == "C1"
    assert [b["block_id"] for b in view["blocks"]] == ["side_a", "side_b", "games"]


def test_the_form_pre_picks_you_on_your_own_side(fake, client):
    run("log", client)
    view = client.views_open.call_args.kwargs["view"]
    assert view["blocks"][0]["element"]["initial_users"] == [A]


def test_the_form_caps_each_side_at_two(fake, client):
    run("log", client)
    view = client.views_open.call_args.kwargs["view"]
    assert all(b["element"]["max_selected_items"] == 2 for b in view["blocks"][:2])


def test_a_form_that_cannot_open_falls_back_to_the_typed_form(fake, client):
    client.views_open.side_effect = Exception("expired_trigger_id")
    assert "type it instead" in said(run("log", client))


def test_submitting_the_form_logs_the_match(fake, client):
    ack = submit(form_state([A], [B], "11-7 9-11 11-5"), client)
    ack.assert_called_once_with()          # closed cleanly, no errors
    record = store.get_pending(posted_mid(client))
    assert record["side_a"] == [A] and record["side_b"] == [B]
    assert record["games"] == [[11, 7], [9, 11], [11, 5]]


def test_the_form_logs_doubles_from_the_pickers_alone(fake, client):
    submit(form_state([A, B], [C, D], "11-7 11-9"), client)
    record = store.get_pending(posted_mid(client))
    assert record["side_a"] == [A, B] and record["side_b"] == [C, D]


def test_a_form_match_confirms_like_any_other(fake, client):
    submit(form_state([A], [B], "11-7 11-9"), client)
    press(bot.handle_confirm, posted_mid(client), B, client)
    assert fake.rating(A) > elo.START_RATING > fake.rating(B)


@pytest.mark.parametrize("state,field,fragment", [
    (form_state([A], [B], "not scores"), "games", "No game scores"),
    (form_state([A], [B], "11-11"), "games", "has to win"),
    (form_state([A], [B, C], "11-7"), "side_b", "Uneven sides"),
    (form_state([A], [A], "11-7"), "side_b", "both sides"),
    (form_state([A], [], "11-7"), "side_b", "who played"),
])
def test_form_errors_come_back_on_the_field(fake, client, state, field, fragment):
    """Attached to the field rather than posted after the modal closes, so a typo
    is one correction instead of a retype."""
    ack = submit(state, client)
    kwargs = ack.call_args.kwargs
    assert kwargs["response_action"] == "errors"
    assert fragment in kwargs["errors"][field]
    assert store.list_pending() == []      # nothing parked on a rejected form


def test_a_form_match_that_cannot_be_posted_is_explained_by_dm(fake, client):
    client.chat_postMessage.side_effect = Exception("not_in_channel")
    submit(form_state([A], [B], "11-7"), client)
    assert client.chat_postMessage.call_args.kwargs["channel"] == A   # DM to the logger
    assert store.list_pending() == []


# --- the pinnable intro ----------------------------------------------------

def test_intro_posts_the_how_it_works_message(fake, client):
    respond = run("intro", client)
    posted = said(client.chat_postMessage)
    assert "Welcome to the table tennis ladder" in posted
    assert "/tt log @opponent" in posted
    assert "Pin to channel" in said(respond)


def test_the_intro_quotes_the_constants_the_code_actually_runs_on(fake, client):
    """It's a command rather than a wiki page precisely so it can't drift."""
    run("intro", client)
    posted = said(client.chat_postMessage)
    assert str(elo.START_RATING) in posted
    assert str(bot.PLACEMENT_GAMES) in posted
    assert str(store.AUTO_CONFIRM_HOURS) in posted


def test_intro_falls_back_to_showing_the_caller(fake, client):
    client.chat_postMessage.side_effect = Exception("not_in_channel")
    assert "Welcome to the table tennis ladder" in said(run("intro", client))


@pytest.mark.parametrize("alias", ["intro", "welcome", "rules", "howto"])
def test_intro_aliases(alias):
    import parsing
    assert parsing.split_subcommand(alias)[0] == "intro"


# --- per-game scoring, end to end -----------------------------------------

def test_a_longer_session_moves_ratings_further(fake, client):
    run(f"log <@{B}> " + " ".join(["11-7"] * 3), client)
    press(bot.handle_confirm, posted_mid(client), B, client)
    short = fake.rating(A) - elo.START_RATING

    run(f"log <@{C}> " + " ".join(["11-7"] * 10), client)
    press(bot.handle_confirm, posted_mid(client), C, client)
    long_ = fake.rating(A) - elo.START_RATING - short
    assert long_ > short > 0


def test_an_even_session_leaves_both_ratings_untouched(fake, client):
    run(f"log <@{B}> 11-7 7-11 11-9 9-11", client)
    press(bot.handle_confirm, posted_mid(client), B, client)
    assert fake.rating(A) == fake.rating(B) == elo.START_RATING
    assert fake.player(A)["games_won"] == 2 and fake.player(A)["games_lost"] == 2


def test_the_board_counts_games_not_sessions(fake, client, monkeypatch):
    monkeypatch.setattr(bot, "PLACEMENT_GAMES", 5)
    run(f"log <@{B}> 11-7 11-9 11-8 11-6 11-5", client)   # one session, five games
    press(bot.handle_confirm, posted_mid(client), B, client)
    board = bot.board_text(store.all_players())
    assert "Still placing" not in board      # five games qualifies them both
    assert f"<@{A}>" in board


def test_a_long_session_is_still_one_undoable_entry(fake, client):
    run(f"log <@{B}> " + " ".join(["11-7"] * 8), client)
    press(bot.handle_confirm, posted_mid(client), B, client)
    assert "Undid" in said(run("undo", client))
    assert fake.rating(A) == fake.rating(B) == elo.START_RATING
    assert fake.player(A)["games_won"] == 0


# --- the shortcuts-menu entry ----------------------------------------------

def shortcut(client, user=A):
    ack = MagicMock()
    bot.handle_log_shortcut(ack, {"user": {"id": user}, "trigger_id": "tid.9"},
                            client=client)
    return ack


def test_the_shortcut_opens_the_same_form(fake, client):
    ack = shortcut(client)
    ack.assert_called_once_with()
    view = client.views_open.call_args.kwargs["view"]
    assert view["callback_id"] == bot.LOG_MODAL
    assert view["blocks"][0]["element"]["initial_users"] == [A]


def test_the_shortcut_form_asks_which_channel(fake, client):
    """A global shortcut carries no channel context, so it has to ask."""
    shortcut(client)
    blocks = client.views_open.call_args.kwargs["view"]["blocks"]
    assert [b["block_id"] for b in blocks] == ["side_a", "side_b", "games", "channel"]
    assert blocks[-1]["element"]["type"] == "conversations_select"


def test_the_channel_picker_starts_on_the_home_channel(fake, client, monkeypatch):
    monkeypatch.setattr(bot, "HOME_CHANNEL", "C_TT")
    shortcut(client)
    picker = client.views_open.call_args.kwargs["view"]["blocks"][-1]["element"]
    assert picker["initial_conversation"] == "C_TT"


def test_the_picker_has_no_preset_without_a_home_channel(fake, client, monkeypatch):
    """initial_conversation pointing at nothing would stop the view opening."""
    monkeypatch.setattr(bot, "HOME_CHANNEL", "")
    shortcut(client)
    picker = client.views_open.call_args.kwargs["view"]["blocks"][-1]["element"]
    assert "initial_conversation" not in picker


def test_the_slash_command_form_has_no_channel_picker(fake, client):
    """It already knows where it was run."""
    run("log", client)
    blocks = client.views_open.call_args.kwargs["view"]["blocks"]
    assert "channel" not in [b["block_id"] for b in blocks]


def test_a_session_logged_from_the_shortcut_posts_to_the_chosen_channel(fake, client):
    state = form_state([A], [B], "11-7 9-11 11-5")
    state["channel"] = {"v": {"selected_conversation": "C_PICKED"}}
    submit(state, client, channel="")           # no private_metadata, as a shortcut
    assert channel_post(client).kwargs["channel"] == "C_PICKED"
    assert store.get_pending(posted_mid(client))["side_b"] == [B]


def test_a_shortcut_session_confirms_like_any_other(fake, client):
    state = form_state([A], [B], "11-7 11-9")
    state["channel"] = {"v": {"selected_conversation": "C_PICKED"}}
    submit(state, client, channel="")
    press(bot.handle_confirm, posted_mid(client), B, client)
    assert fake.rating(A) > elo.START_RATING > fake.rating(B)


def test_the_shortcut_form_rejects_an_empty_channel(fake, client):
    state = form_state([A], [B], "11-7")
    state["channel"] = {"v": {"selected_conversation": None}}
    ack = submit(state, client, channel="")
    assert ack.call_args.kwargs["response_action"] == "errors"
    assert "channel" in ack.call_args.kwargs["errors"]
    assert store.list_pending() == []


def test_a_shortcut_that_cannot_open_is_explained_by_dm(fake, client):
    client.views_open.side_effect = Exception("expired_trigger_id")
    shortcut(client)
    assert client.chat_postMessage.call_args.kwargs["channel"] == A
    assert "/tt log @opponent" in said(client.chat_postMessage)


# --- a bystander's click must not touch the channel's view -----------------

def ephemeral_calls(respond):
    return [c.kwargs for c in respond.call_args_list
            if c.kwargs.get("response_type") == "ephemeral"]


def test_a_bystander_pressing_confirm_leaves_the_prompt_alone(fake, client):
    """A reply to an interactive component replaces the message it came from
    unless told otherwise — so without replace_original=False a passer-by's
    click would wipe the buttons for the people who can actually press them."""
    run(f"log <@{B}> 11-7 11-9", client)
    mid = posted_mid(client)
    respond = press(bot.handle_confirm, mid, C, client)

    assert all(c["replace_original"] is False for c in ephemeral_calls(respond))
    assert client.chat_update.call_count == 0      # channel message untouched
    assert store.get_pending(mid) is not None      # still confirmable
    press(bot.handle_confirm, mid, B, client)      # and B can still settle it
    assert fake.rating(A) > elo.START_RATING


def test_a_bystander_pressing_dispute_leaves_the_prompt_alone(fake, client):
    run(f"log <@{B}> 11-7", client)
    mid = posted_mid(client)
    respond = press(bot.handle_dispute, mid, C, client)
    assert all(c["replace_original"] is False for c in ephemeral_calls(respond))
    assert client.chat_update.call_count == 0
    assert store.get_pending(mid) is not None


@pytest.mark.parametrize("user,action", [
    (A, bot.handle_confirm),      # the reporter confirming their own
    (C, bot.handle_confirm),      # a bystander
    (C, bot.handle_dispute),      # a bystander
])
def test_every_refusal_is_private_and_non_destructive(fake, client, user, action):
    run(f"log <@{B}> 11-7 11-9", client)
    respond = press(action, posted_mid(client), user, client)
    calls = ephemeral_calls(respond)
    assert calls, "a refusal must say something"
    assert all(c["replace_original"] is False for c in calls)
    assert store.get_pending(posted_mid(client)) is not None


def test_settling_the_match_still_replaces_the_prompt(fake, client):
    """The guard must not have broken the case that *should* edit the message."""
    run(f"log <@{B}> 11-7", client)
    press(bot.handle_confirm, posted_mid(client), B, client)
    edited = {c.kwargs["channel"] for c in client.chat_update.call_args_list}
    assert "C1" in edited                      # the channel post became the result
    assert all(not any(b["type"] == "actions" for b in c.kwargs["blocks"])
               for c in client.chat_update.call_args_list)


# --- admin: record a result with no confirmation --------------------------

ADMIN = "U0ADMIN1"


@pytest.fixture
def admin(monkeypatch):
    monkeypatch.setenv("TT_ADMINS", ADMIN)
    return ADMIN


def test_an_admin_session_is_rated_immediately(fake, client, admin):
    run(f"log <@{B}> 11-7 11-9 11-8", client, user=ADMIN)
    assert store.list_pending() == []            # never waits on anyone
    assert fake.rating(ADMIN) > elo.START_RATING > fake.rating(B)
    posted = said(client.chat_postMessage)
    assert "beat" in posted and str(fake.rating(ADMIN)) in posted


def test_the_admin_result_has_no_buttons_to_press(fake, client, admin):
    run(f"log <@{B}> 11-7", client, user=ADMIN)
    blocks = client.chat_postMessage.call_args.kwargs["blocks"]
    assert not any(b["type"] == "actions" for b in blocks)


def test_skipping_confirmation_is_visible_to_the_channel(fake, client, admin):
    """An admin result must not be indistinguishable from an agreed one."""
    run(f"log <@{B}> 11-7", client, user=ADMIN)
    assert f"recorded by <@{ADMIN}>" in said(client.chat_postMessage)


def test_a_non_admin_still_needs_confirmation(fake, client, admin):
    run(f"log <@{B}> 11-7", client, user=A)
    assert len(store.list_pending()) == 1
    assert fake.data.get(store.player_key(A)) is None


def test_admin_rights_come_from_the_environment(fake, client, monkeypatch):
    monkeypatch.setenv("TT_ADMINS", "")
    run(f"log <@{B}> 11-7", client, user=ADMIN)
    assert len(store.list_pending()) == 1        # nobody is an admin by default


@pytest.mark.parametrize("raw", ["U0ADMIN1", "U0ADMIN1,U0AAA1", "U0ADMIN1 U0AAA1",
                                 " U0ADMIN1 , U0AAA1 "])
def test_the_admin_list_accepts_commas_or_spaces(monkeypatch, raw):
    monkeypatch.setenv("TT_ADMINS", raw)
    assert bot.is_admin(ADMIN)
    assert not bot.is_admin("U0NOBODY")


def test_an_admin_can_settle_someone_elses_stuck_session(fake, client, admin):
    """The only way to clear a session whose players have gone quiet, short of
    waiting for the daily sweep."""
    run(f"log <@{B}> 11-7 11-9", client, user=A)
    mid = posted_mid(client)
    press(bot.handle_confirm, mid, ADMIN, client)
    assert store.get_pending(mid) is None
    assert fake.rating(A) > elo.START_RATING


def test_an_admin_can_throw_out_someone_elses_session(fake, client, admin):
    run(f"log <@{B}> 11-7", client, user=A)
    press(bot.handle_dispute, posted_mid(client), ADMIN, client)
    assert store.list_pending() == []
    assert fake.data.get(store.player_key(A)) is None


def test_a_non_admin_bystander_still_cannot(fake, client, admin):
    run(f"log <@{B}> 11-7", client, user=A)
    respond = press(bot.handle_confirm, posted_mid(client), C, client)
    assert "Only" in said(respond)
    assert store.list_pending()


def test_an_admin_session_is_undoable_like_any_other(fake, client, admin):
    run(f"log <@{B}> 11-7 11-9", client, user=ADMIN)
    assert "Undid" in said(run("undo", client, user=ADMIN))
    assert fake.rating(ADMIN) == fake.rating(B) == elo.START_RATING


def test_an_admin_session_that_cannot_be_posted_still_counts(fake, client, admin):
    """Rated before posting, so a channel problem can't silently drop a result."""
    client.chat_postMessage.side_effect = Exception("not_in_channel")
    respond = run(f"log <@{B}> 11-7", client, user=ADMIN)
    assert fake.rating(ADMIN) > elo.START_RATING
    assert "Ratings updated" in said(respond)


def test_an_admin_can_record_a_session_between_two_other_people(fake, client, admin):
    run(f"log <@{A}> vs <@{B}> 11-7 11-9", client, user=ADMIN)
    assert store.list_pending() == []
    assert fake.rating(A) > elo.START_RATING > fake.rating(B)
    assert fake.data.get(store.player_key(ADMIN)) is None   # not a player here


# --- the verdict goes to the people it costs, not the channel -------------

def test_the_channel_post_carries_no_buttons(fake, client):
    """Buttons in a channel invite everyone who can see them to press, and the
    ones who shouldn't only find out after clicking."""
    run(f"log <@{B}> 11-7 9-11 11-5", client)
    assert buttons_in(channel_post(client)) == []
    assert f"<@{A}>" in said(client.chat_postMessage)       # still shows the claim
    assert "11-7" in said(client.chat_postMessage)


def test_the_opponent_gets_the_buttons_by_dm(fake, client):
    run(f"log <@{B}> 11-7 11-9", client)
    assert buttons_in(dm_to(client, B)) == [bot.CONFIRM_ACTION, bot.DISPUTE_ACTION]


def test_the_logger_gets_a_cancel_only_dm(fake, client):
    """Their mistake to take back, but not their result to wave through."""
    run(f"log <@{B}> 11-7", client)
    assert buttons_in(dm_to(client, A)) == [bot.DISPUTE_ACTION]
    assert "Cancel" in said(client.chat_postMessage)


def test_nobody_else_is_messaged(fake, client):
    run(f"log <@{B}> 11-7", client)
    assert dm_to(client, C) is None and dm_to(client, D) is None


def test_both_opponents_get_asked_in_doubles(fake, client):
    run(f"log <@{B}> vs <@{C}> <@{D}> 11-7 11-9", client)
    assert buttons_in(dm_to(client, C)) == [bot.CONFIRM_ACTION, bot.DISPUTE_ACTION]
    assert buttons_in(dm_to(client, D)) == [bot.CONFIRM_ACTION, bot.DISPUTE_ACTION]
    assert dm_to(client, B) is None          # the logger's partner is not asked


def test_the_dm_locations_are_remembered(fake, client):
    run(f"log <@{B}> 11-7", client)
    record = store.get_pending(posted_mid(client))
    assert set(record["dms"]) == {A, B}
    assert all(len(loc) == 2 for loc in record["dms"].values())


def test_confirming_updates_the_channel_and_every_dm(fake, client):
    """Otherwise live buttons sit in someone's DM for a settled session."""
    run(f"log <@{B}> vs <@{C}> <@{D}> 11-7 11-9", client)
    press(bot.handle_confirm, posted_mid(client), C, client)

    updated = {c.kwargs["channel"] for c in client.chat_update.call_args_list}
    assert updated == {"C1", A, C, D}        # channel + logger + both opponents
    for call in client.chat_update.call_args_list:
        assert not any(b["type"] == "actions" for b in call.kwargs["blocks"])


def test_disputing_updates_the_channel_and_every_dm(fake, client):
    run(f"log <@{B}> 11-7", client)
    press(bot.handle_dispute, posted_mid(client), B, client)
    updated = {c.kwargs["channel"] for c in client.chat_update.call_args_list}
    assert updated == {"C1", A, B}


def test_the_sweep_clears_every_copy_too(fake, client):
    run(f"log <@{B}> 11-7 11-9", client)
    later = store.now_ist() + timedelta(hours=store.AUTO_CONFIRM_HOURS + 1)
    standings.sweep_pending(client, now=later)
    updated = {c.kwargs["channel"] for c in client.chat_update.call_args_list}
    assert updated == {"C1", A, B}


def test_one_unreachable_person_does_not_stop_the_others(fake, client):
    def selective(**kwargs):
        if kwargs.get("channel") == A:
            raise Exception("cannot_dm_bot")
        return {"channel": kwargs.get("channel"), "ts": "1.1"}
    client.chat_postMessage.side_effect = selective

    respond = run(f"log <@{B}> 11-7", client)
    record = store.get_pending(posted_mid(client))
    assert set(record["dms"]) == {B}          # B still got asked
    assert respond.call_count == 0            # and it's not reported as a failure
    press(bot.handle_confirm, posted_mid(client), B, client)
    assert fake.rating(A) > elo.START_RATING


def test_if_nobody_could_be_asked_the_logger_is_told(fake, client):
    """Silently sitting until the sweep would look like it simply worked."""
    def channel_only(**kwargs):
        if not str(kwargs.get("channel", "")).startswith("C"):
            raise Exception("cannot_dm_bot")
        return {"channel": kwargs["channel"], "ts": "1.1"}
    client.chat_postMessage.side_effect = channel_only

    respond = run(f"log <@{B}> 11-7", client)
    assert "couldn't DM anyone to confirm" in said(respond)
    assert len(store.list_pending()) == 1     # still valid, still sweepable


def test_a_settled_session_can_still_be_settled_from_an_old_message(fake, client):
    """A session logged before DMs existed has no stored locations; the press
    still has to land somewhere."""
    run(f"log <@{B}> 11-7", client)
    mid = posted_mid(client)
    record = store.get_pending(mid)
    record.pop("dms"), record.pop("channel"), record.pop("ts")
    store.kv.set_(store.pending_key(mid), json.dumps(record))

    press(bot.handle_confirm, mid, B, client)
    assert fake.rating(A) > elo.START_RATING
    assert client.chat_update.call_count == 1     # the container fallback


# --- an admin settling someone else's session -----------------------------

def admin_pending(client, caller=ADMIN):
    respond = MagicMock()
    bot.handle_pending({"user_id": caller}, respond)
    return respond


def blocks_of(respond):
    for c in respond.call_args_list:
        if c.kwargs.get("blocks"):
            return c.kwargs["blocks"]
    return []


def action_ids_for(respond, mid):
    for b in blocks_of(respond):
        if b.get("block_id") == f"tt_admin_{mid}":
            return [e["action_id"] for e in b["elements"]]
    return []


def test_pending_gives_an_admin_buttons(fake, client, admin):
    """The verdict DMs go to the players, so without this an admin holds the
    permission and has nowhere to use it."""
    run(f"log <@{B}> 11-7 11-9", client, user=A)
    mid = posted_mid(client)
    assert action_ids_for(admin_pending(client), mid) == \
        [bot.CONFIRM_ACTION, bot.DISPUTE_ACTION]


def test_pending_stays_plain_text_for_everyone_else(fake, client, admin):
    run(f"log <@{B}> 11-7", client, user=A)
    assert blocks_of(admin_pending(client, caller=C)) == []
    assert "Waiting on confirmation" in said(admin_pending(client, caller=C))


def test_an_admin_confirms_another_persons_session_from_the_list(fake, client, admin):
    run(f"log <@{B}> 11-7 11-9", client, user=A)
    mid = posted_mid(client)
    respond = MagicMock()
    press(bot.handle_confirm, mid, ADMIN, client, respond=respond, ephemeral=True)

    assert store.get_pending(mid) is None
    assert fake.rating(A) > elo.START_RATING > fake.rating(B)
    assert f"Settled `#{mid}`" in said(respond)       # the list looks unchanged otherwise


def test_an_admin_throws_out_another_persons_session_from_the_list(fake, client, admin):
    run(f"log <@{B}> 11-7", client, user=A)
    mid = posted_mid(client)
    respond = MagicMock()
    press(bot.handle_dispute, mid, ADMIN, client, respond=respond, ephemeral=True)
    assert store.list_pending() == []
    assert f"Threw out `#{mid}`" in said(respond)


def test_settling_from_the_list_still_updates_the_players_copies(fake, client, admin):
    run(f"log <@{B}> 11-7", client, user=A)
    press(bot.handle_confirm, posted_mid(client), ADMIN, client, ephemeral=True)
    updated = {c.kwargs["channel"] for c in client.chat_update.call_args_list}
    assert updated == {"C1", A, B}          # channel + both players' DMs


def test_an_admin_cannot_confirm_a_session_they_logged_themselves(fake, client, monkeypatch):
    """Nobody waves through their own result — an admin least defensibly of all.
    (Reachable only if admin was granted after the session was logged.)"""
    run(f"log <@{B}> 11-7 11-9", client, user=A)      # A logs it as a normal player
    mid = posted_mid(client)
    monkeypatch.setenv("TT_ADMINS", A)                # A is promoted afterwards

    respond = press(bot.handle_confirm, mid, A, client)
    assert "Only" in said(respond)
    assert store.get_pending(mid) is not None
    assert action_ids_for(admin_pending(client, caller=A), mid) == [bot.DISPUTE_ACTION]


def test_an_admin_can_still_cancel_their_own(fake, client, monkeypatch):
    run(f"log <@{B}> 11-7", client, user=A)
    mid = posted_mid(client)
    monkeypatch.setenv("TT_ADMINS", A)
    press(bot.handle_dispute, mid, A, client)
    assert store.list_pending() == []


def test_a_normal_dm_press_gets_no_extra_note(fake, client):
    """Pressing from a DM edits that DM, so an extra 'settled' note is noise."""
    run(f"log <@{B}> 11-7", client, user=A)
    respond = press(bot.handle_confirm, posted_mid(client), B, client)
    assert "Settled" not in said(respond)


def test_the_admin_list_is_capped(fake, client, admin, monkeypatch):
    monkeypatch.setattr(bot, "ADMIN_PENDING_LIMIT", 2)
    for opponent in (B, C, D):
        run(f"log <@{opponent}> 11-7", client, user=A)
    respond = admin_pending(client)
    assert len([b for b in blocks_of(respond) if b["type"] == "actions"]) == 2
    assert "1 more" in said(respond)


# --- choosing a name for the ladder ---------------------------------------

def test_setting_a_name(fake, client):
    assert "Sagnik" in said(run("name Sagnik", client))
    assert store.chosen_names()[A] == "Sagnik"


def test_a_chosen_name_beats_the_slack_handle(fake, client):
    """The handle is a fallback; what someone asked to be called always wins."""
    store.remember_handle(A, "praneat.data")
    run("name Sagnik", client)
    assert store.names()[A] == "Sagnik"


def test_the_handle_is_kept_when_no_name_is_chosen(fake, client):
    respond = MagicMock()
    bot.handle_tt_command(MagicMock(),
                          {"user_id": A, "user_name": "praneat.data", "text": "board",
                           "channel_id": "C1", "trigger_id": "t"},
                          respond, client=client, context={})
    assert store.names()[A] == "praneat.data"


def test_asking_what_your_name_is(fake, client):
    assert "haven't set a name" in said(run("name", client))
    run("name Sagnik", client)
    assert "You're *Sagnik*" in said(run("name", client))


def test_clearing_a_name(fake, client):
    run("name Sagnik", client)
    assert "Cleared" in said(run("name clear", client))
    assert A not in store.chosen_names()


def test_a_name_is_tidied_and_capped(fake, client):
    run("name    Sagnik   the    Destroyer of Worlds and Several Bats", client)
    saved = store.chosen_names()[A]
    assert len(saved) <= store.MAX_NAME and "  " not in saved


def test_nudging_asks_everyone_without_a_name(fake, client, admin):
    store.ensure_players([A, B, C])
    store.set_name(B, "Vikash")
    respond = run("nudge", client, user=ADMIN)
    asked = {c.kwargs["channel"] for c in client.chat_postMessage.call_args_list}
    assert asked == {A, C}                    # B already chose one
    assert "Asked *2*" in said(respond)


def test_only_an_admin_can_nudge_everyone(fake, client, admin):
    store.ensure_players([A, B])
    respond = run("nudge", client, user=B)
    assert "Only an admin" in said(respond)
    assert client.chat_postMessage.call_count == 0


def test_nudging_when_everyone_is_named(fake, client, admin):
    store.ensure_players([A])
    store.set_name(A, "Sagnik")
    assert "Everyone on the ladder has chosen" in said(run("nudge", client, user=ADMIN))


def test_the_welcome_dm_asks_for_a_name(fake, client, monkeypatch):
    monkeypatch.setattr(bot, "HOME_CHANNEL", "C_TT")
    bot.handle_member_joined({"channel": "C_TT", "user": B}, client=client,
                             context={"bot_user_id": BOT})
    assert "/tt name" in said(client.chat_postMessage)
