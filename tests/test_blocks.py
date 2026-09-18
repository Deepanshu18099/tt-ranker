"""Every message the bot builds, checked against Slack's Block Kit rules.

This file exists because a duplicate action_id shipped. Two Back buttons in one
actions block both used "tt_bet", Slack rejected the whole message as
invalid_blocks, and the only symptom anyone saw was a fixture that wouldn't
post. Length checks alone didn't catch it — structure needs checking too.
"""
from datetime import timedelta

import pytest

import betting
import bot
import elo
import store
from tests.fake_kv import FakeRedis

A, B, C, D = "U0AAA1", "U0BBB1", "U0CCC1", "U0DDD1"

# https://docs.slack.dev/reference/block-kit
LIMITS = {"blocks": 50, "block_id": 255, "action_id": 255, "section": 3000,
          "context_elements": 10, "context_text": 3000, "button_text": 75,
          "value": 2000, "elements": 25, "modal_title": 24, "modal_button": 24}


def check_blocks(blocks, where):
    """Assert a block list is something Slack will accept."""
    assert len(blocks) <= LIMITS["blocks"], f"{where}: too many blocks"
    for block in blocks:
        kind = block.get("type")
        assert kind, f"{where}: a block with no type"
        assert len(str(block.get("block_id", ""))) <= LIMITS["block_id"], where

        if kind == "section":
            text = block["text"]["text"]
            assert text, f"{where}: empty section"
            assert len(text) <= LIMITS["section"], f"{where}: section too long"
        elif kind == "context":
            assert 0 < len(block["elements"]) <= LIMITS["context_elements"], where
            for el in block["elements"]:
                assert el["text"], f"{where}: empty context element"
                assert len(el["text"]) <= LIMITS["context_text"], where
        elif kind == "actions":
            elements = block["elements"]
            assert 0 < len(elements) <= LIMITS["elements"], where
            seen = set()
            for el in elements:
                action = el["action_id"]
                # The one that actually bit: unique *within the block*.
                assert action not in seen, \
                    f"{where}: duplicate action_id {action!r} in one actions block"
                seen.add(action)
                assert len(action) <= LIMITS["action_id"], where
                assert el["text"]["type"] == "plain_text", where
                assert 0 < len(el["text"]["text"]) <= LIMITS["button_text"], \
                    f"{where}: button text {el['text']['text']!r}"
                assert len(str(el.get("value", ""))) <= LIMITS["value"], where
                assert el.get("style") in (None, "primary", "danger"), where
        elif kind == "input":
            assert block.get("element"), f"{where}: input with no element"
            assert block["label"]["type"] == "plain_text", where


def check_view(view, where):
    assert view["type"] == "modal", where
    assert len(view["title"]["text"]) <= LIMITS["modal_title"], f"{where}: title too long"
    for key in ("submit", "close"):
        if view.get(key):
            assert len(view[key]["text"]) <= LIMITS["modal_button"], \
                f"{where}: {key} label too long"
    ids = [b["block_id"] for b in view["blocks"] if b.get("block_id")]
    assert len(ids) == len(set(ids)), f"{where}: duplicate block_id in a view"
    check_blocks(view["blocks"], where)


@pytest.fixture
def fake():
    redis = FakeRedis()
    with redis.patched():
        yield redis


def a_session(side_a=(A,), side_b=(B,), games=((21, 14), (11, 0), (21, 16))):
    record = store.create_pending(list(side_a), list(side_b), [list(g) for g in games],
                                  logged_by=side_a[0], channel="C1")
    return record


# --- match messages --------------------------------------------------------

@pytest.mark.parametrize("side_a,side_b", [((A,), (B,)), ((A, B), (C, D))])
def test_the_channel_post_and_every_verdict_dm_are_valid(fake, side_a, side_b):
    record = a_session(side_a, side_b)
    check_blocks(bot.pending_blocks(record), "pending_blocks")
    for uid, role in bot.verdict_audience(record).items():
        check_blocks(bot.verdict_blocks(record, role), f"verdict_blocks[{role}]")


def test_a_settled_match_message_is_valid(fake):
    record = a_session()
    store.claim_pending(record["id"])
    blob = store.apply_match(record, confirmed_by=B)
    check_blocks(bot.applied_blocks(blob), "applied_blocks")


def test_the_admin_pending_list_is_valid(fake):
    records = [a_session(), a_session((A,), (C,)), a_session((A,), (D,))]
    check_blocks(bot.admin_pending_blocks(records, A), "admin_pending_blocks")


# --- fixtures --------------------------------------------------------------

def a_fixture(side_a=(A,), side_b=(B,)):
    return betting.schedule(list(side_a), list(side_b),
                            store.now_ist() + timedelta(hours=2),
                            created_by=side_a[0], channel="C1")


@pytest.mark.parametrize("side_a,side_b", [((A,), (B,)), ((A, B), (C, D))])
def test_a_fixture_message_is_valid_at_every_stage(fake, side_a, side_b):
    """The one that shipped broken: both Back buttons shared an action_id."""
    record = a_fixture(side_a, side_b)
    check_blocks(bot.fixture_blocks(record), "fixture_blocks[open]")

    betting.place_bet(record, C if C not in side_a + side_b else A, "a", 50)
    check_blocks(bot.fixture_blocks(record), "fixture_blocks[with a bet]")

    betting.place_bet(record, side_a[0], "b", 25)      # backing their own opponent
    check_blocks(bot.fixture_blocks(record), "fixture_blocks[against self]")

    record["state"] = "closed"
    check_blocks(bot.fixture_blocks(record), "fixture_blocks[closed]")

    pot = betting.pool(record["id"])
    betting.claim(record["id"])
    settled = betting.settle(record, "a", match_id="1")
    check_blocks(bot.settled_fixture_blocks(settled, pot), "settled_fixture_blocks")


def test_the_two_back_buttons_do_not_share_an_action_id(fake):
    """Stated on its own, because this is the rule that was broken."""
    record = a_fixture()
    actions = next(b for b in bot.fixture_blocks(record) if b["type"] == "actions")
    ids = [e["action_id"] for e in actions["elements"]]
    assert len(ids) == len(set(ids))
    assert set(bot.BET_ACTIONS) <= set(ids)


def test_a_fixture_with_no_names_set_is_still_valid(fake):
    """Button labels fall back to a stub, which must not blow the length cap."""
    record = betting.schedule(["U08V0KSE092"], ["U02LZMRNB7C"],
                              store.now_ist() + timedelta(hours=1),
                              created_by="U08V0KSE092", channel="C1")
    check_blocks(bot.fixture_blocks(record), "fixture_blocks[unnamed]")


def test_long_real_names_do_not_overflow_a_button(fake):
    store.remember_names({A: "Bartholomew Featherstonehaugh-Cholmondeley",
                          B: "Wolfeschlegelsteinhausenbergerdorff Jr"})
    record = a_fixture((A, B), (C, D))
    check_blocks(bot.fixture_blocks(record), "fixture_blocks[very long names]")


# --- modals ----------------------------------------------------------------

@pytest.mark.parametrize("pick_channel", [False, True])
def test_the_log_form_is_a_valid_view(fake, pick_channel):
    check_view(bot.build_log_modal(A, "C1", pick_channel=pick_channel), "log modal")


@pytest.mark.parametrize("pick_channel", [False, True])
def test_the_schedule_form_is_a_valid_view(fake, pick_channel):
    check_view(bot.build_schedule_modal(A, "C1", pick_channel=pick_channel),
               "schedule modal")


def test_the_bet_form_is_a_valid_view(fake):
    record = a_fixture()
    check_view(bot.bet_modal(record, "a", 500), "bet modal")
    betting.place_bet(record, C, "a", 50)
    check_view(bot.bet_modal(record, "b", 500), "bet modal[with a pool]")


# --- the edit preview ------------------------------------------------------

def _edit_blocks(fake, monkeypatch, text, players=(A, B), games=((21, 14), (21, 16))):
    from unittest.mock import MagicMock
    monkeypatch.setenv("TT_ADMINS", A)
    record = store.create_pending([players[0]], [players[1]],
                                  [list(g) for g in games], logged_by=players[0])
    store.claim_pending(record["id"])
    store.apply_match(record, confirmed_by=players[1])
    respond = MagicMock()
    bot.handle_edit({"user_id": A, "text": text, "channel_id": "C1"}, respond)
    blocks = respond.call_args.kwargs.get("blocks")
    assert blocks, f"no preview for {text!r}: {respond.call_args}"
    return blocks


@pytest.mark.parametrize("text", ["edit 1 21-14 21-19", "edit 1 swap", "edit 1 void"])
def test_the_edit_preview_is_valid(fake, monkeypatch, text):
    check_blocks(_edit_blocks(fake, monkeypatch, text), f"handle_edit({text})")


def test_the_edit_button_value_fits_slacks_limit(fake, monkeypatch):
    """The whole edit spec rides in the button's value, and a long session is
    the case that would push it over."""
    games = tuple((21, 10) for _ in range(elo.MAX_GAMES))
    text = "edit 1 " + " ".join(f"{a}-{b}" for a, b in games)
    blocks = _edit_blocks(fake, monkeypatch, text, games=((21, 14),))
    button = next(el for b in blocks if b["type"] == "actions"
                  for el in b["elements"])
    assert len(button["value"]) <= LIMITS["value"]


def test_a_correction_that_moves_the_whole_ladder_still_fits_a_section():
    """Editing an early match can move everybody. The preview truncates rather
    than building a section Slack will reject."""
    plan = {"id": "1", "void": False, "replayed": 300, "winner_flipped": True,
            "moved": {f"U0PL{i:03d}": (1000, 1000 + i) for i in range(1, 300)},
            "before": {"side_a": [A], "side_b": [B], "games": [(21, 14)]},
            "after": {"side_a": [A], "side_b": [B], "games": [(21, 19)]}}
    effect = bot._edit_effect(plan)
    assert len(effect) <= LIMITS["section"]
    assert "and 287 more" in effect          # 299 moved, 12 shown
    check_blocks([{"type": "section", "text": {"type": "mrkdwn", "text": effect}}],
                 "_edit_effect(wide)")


# --- moving a fixture ------------------------------------------------------

def test_the_reschedule_form_is_a_valid_view(fake):
    record = betting.schedule([A], [B], store.now_ist() + timedelta(hours=1),
                              created_by=A, channel="C1")
    check_view(bot.build_reschedule_modal(record), "build_reschedule_modal")


def test_the_reschedule_form_is_valid_with_a_pot_on_it(fake):
    record = betting.schedule([A], [B], store.now_ist() + timedelta(hours=1),
                              created_by=A, channel="C1")
    betting.place_bet(record, C, "a", 4000)
    check_view(bot.build_reschedule_modal(record), "build_reschedule_modal(staked)")


def test_a_moved_fixture_message_is_valid_at_every_stage(fake):
    now = store.now_ist()
    record = betting.schedule([A, B], [C, D], now + timedelta(minutes=10),
                              created_by=A, channel="C1", now=now)
    betting.reschedule(record, now + timedelta(hours=4), by=A, now=now)
    check_blocks(bot.fixture_blocks(record, now), "fixture_blocks(moved, open)")
    betting.close_if_due(record, now + timedelta(hours=5))
    check_blocks(bot.fixture_blocks(record, now + timedelta(hours=5)),
                 "fixture_blocks(moved, closed)")
