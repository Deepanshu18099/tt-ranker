"""`/tt edit` — correcting a match that was logged wrong.

The awkward part isn't the edit, it's everything after it. A match rated in
January set the ratings that February's matches were rated against, so changing
it means re-rating the lot. These tests are mostly about that: that the ladder
afterwards is exactly the ladder you'd have had if the right thing had been
logged the first time.
"""
import json
from unittest.mock import MagicMock

import pytest

import bot
import elo
import parsing
import rerate
import store
from tests.fake_kv import FakeRedis

A, B, C, D = "U0AAA1", "U0BBB1", "U0CCC1", "U0DDD1"
ADMIN = "U0ADM1"


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setenv("TT_ADMINS", ADMIN)
    redis = FakeRedis()
    with redis.patched():
        yield redis


def play(side_a, side_b, games):
    record = store.create_pending(side_a, side_b, games, logged_by=side_a[0])
    assert store.claim_pending(record["id"])
    return store.apply_match(record, confirmed_by=side_b[0])


def ratings():
    return {u: p["rating"] for u, p in store.all_players().items()}


def do(mid, **kw):
    plan, *rest = rerate.plan_edit(mid, **kw)
    rerate.commit_edit(plan, *rest)
    return plan


# --- the ladder afterwards is the ladder you should have had ---------------

def test_it_matches_a_clean_run_of_the_same_history(fake):
    """Edit match 1 of 3, then compare against a ladder that only ever saw the
    corrected version. Elo isn't commutative, so this is a real check."""
    play([A], [B], [(21, 17), (19, 21)])
    play([B], [C], [(21, 15), (21, 12)])
    play([A], [C], [(21, 19), (18, 21), (21, 14)])
    do("1", games=[(21, 17), (21, 19)])
    edited = ratings()

    for key in list(fake.data):
        del fake.data[key]
    play([A], [B], [(21, 17), (21, 19)])
    play([B], [C], [(21, 15), (21, 12)])
    play([A], [C], [(21, 19), (18, 21), (21, 14)])
    assert edited == ratings()


def test_a_swap_is_the_same_as_having_logged_the_names_the_other_way(fake):
    play([A], [B], [(21, 17), (21, 19)])
    do("1", swap=True)
    swapped = ratings()

    for key in list(fake.data):
        del fake.data[key]
    play([B], [A], [(21, 17), (21, 19)])
    assert swapped == ratings()


def test_a_swap_moves_only_the_names(fake):
    """The scores stay in the columns they were typed in — that's what flips the
    result. Turning those round as well would invert it twice and do nothing."""
    play([A], [B], [(21, 17), (21, 19)])         # A won
    assert store.get_player(A)["rating"] > store.get_player(B)["rating"]
    do("1", swap=True)
    blob = store.get_match("1")
    assert blob["side_a"] == [B] and blob["side_b"] == [A]
    assert [tuple(g) for g in blob["games"]] == [(21, 17), (21, 19)]
    assert store.get_player(B)["rating"] > store.get_player(A)["rating"]   # now B


def test_later_matches_are_re_rated_not_left_stale(fake):
    play([A], [B], [(21, 17), (19, 21)])     # 1 — the one we'll fix
    play([A], [C], [(21, 10), (21, 12)])     # 2 — rated off A's rating from 1
    before = store.get_match("2")["before"][A]
    do("1", games=[(21, 17), (21, 19)])
    assert store.get_match("2")["before"][A] != before


def test_the_undo_snapshots_are_rebuilt(fake):
    """Otherwise /tt undo on a later match would restore pre-correction numbers
    and quietly put the old ladder back."""
    play([A], [B], [(21, 17), (19, 21)])
    blob = play([A], [C], [(21, 10), (21, 12)])
    do("1", games=[(21, 17), (21, 19)])
    fresh = store.get_match(blob["id"])
    before = {u: store.get_player(u) for u in (A, C)}
    store.undo_match(fresh)
    assert {u: store.get_player(u) for u in (A, C)} != before
    play([A], [C], [(21, 10), (21, 12)])
    assert {u: store.get_player(u)["rating"] for u in (A, C)} == \
           {u: p["rating"] for u, p in before.items()}


# --- voiding ---------------------------------------------------------------

def test_voiding_removes_the_match_everywhere(fake):
    play([A], [B], [(21, 17), (21, 19)])
    do("1")
    assert store.get_match("1") is None
    assert store.recent_matches(limit=10) == []
    assert store.last_match_by(A) is None


def test_voiding_the_only_match_returns_everyone_to_the_start_line(fake):
    play([A], [B], [(21, 17), (21, 19)])
    do("1")
    for uid in (A, B):
        player = store.get_player(uid)
        assert player["rating"] == elo.START_RATING
        assert elo.games_played(player) == 0
        assert player["matches"] == 0


def test_voiding_keeps_the_day_they_joined(fake):
    play([A], [B], [(21, 17), (21, 19)])
    joined = store.get_player(A)["joined"]
    do("1")
    assert store.get_player(A)["joined"] == joined


def test_voiding_a_duplicate_leaves_the_rest_of_the_ladder_right(fake):
    play([A], [B], [(21, 17), (21, 19)])
    play([A], [B], [(21, 17), (21, 19)])     # logged twice by mistake
    do("2")
    once = ratings()

    for key in list(fake.data):
        del fake.data[key]
    play([A], [B], [(21, 17), (21, 19)])
    assert once == ratings()


def test_the_format_ladders_are_rebuilt_too(fake):
    play([A, B], [C, D], [(21, 17), (19, 21), (21, 10)])   # A+B won 2-1
    do("1", swap=True)
    for uid in (C, D):
        assert store.doubles_view(store.get_player(uid))["rating"] > elo.START_RATING
        assert store.singles_view(store.get_player(uid))["rating"] == elo.START_RATING


# --- what the plan reports -------------------------------------------------

def test_the_plan_names_who_moves_and_by_how_much(fake):
    play([A], [B], [(21, 17), (21, 19)])
    plan, *_ = rerate.plan_edit("1", games=[(21, 5), (21, 3)])   # A won either way
    assert set(plan["moved"]) == {A, B}
    was, now = plan["moved"][A]
    assert now > was                       # a wider margin is worth more
    assert plan["winner_flipped"] is False


def test_turning_a_drawn_session_into_a_win_counts_as_a_flip(fake):
    """Anyone who backed it was paid on a draw, so it needs the same warning."""
    play([A], [B], [(21, 17), (19, 21)])
    plan, *_ = rerate.plan_edit("1", games=[(21, 17), (21, 19)])
    assert plan["winner_flipped"] is True


def test_it_flags_a_correction_that_changes_who_won(fake):
    """Bets were paid on the old result, so this is not a silent change."""
    play([A], [B], [(21, 17), (21, 19)])
    plan, *_ = rerate.plan_edit("1", swap=True)
    assert plan["winner_flipped"] is True


def test_it_counts_the_matches_it_would_re_rate(fake):
    play([A], [B], [(21, 17), (19, 21)])
    play([B], [C], [(21, 15), (21, 12)])
    play([A], [C], [(21, 15), (21, 12)])
    plan, *_ = rerate.plan_edit("1", games=[(21, 17), (21, 19)])
    assert plan["replayed"] == 2


def test_planning_writes_nothing(fake):
    play([A], [B], [(21, 17), (19, 21)])
    before = ratings()
    rerate.plan_edit("1", games=[(21, 17), (21, 19)])
    assert ratings() == before


def test_an_unknown_match_is_refused(fake):
    with pytest.raises(rerate.EditError, match="No match"):
        rerate.plan_edit("99", swap=True)


def test_an_edit_that_changes_nothing_is_refused(fake):
    play([A], [B], [(21, 17), (21, 19)])
    with pytest.raises(rerate.EditError, match="already says"):
        rerate.plan_edit("1", games=[(21, 17), (21, 19)])


def test_a_gap_in_the_history_stops_the_edit(fake):
    """A replay on an incomplete history would invent a ladder. Better to
    refuse than to write a confident wrong answer."""
    play([A], [B], [(21, 17), (21, 19)])
    play([A], [C], [(21, 15), (21, 12)])
    del fake.data[store.match_key("1")]
    with pytest.raises(rerate.EditError, match="no stored record"):
        rerate.plan_edit("2", swap=True)


# --- the Slack command -----------------------------------------------------

def command(text, user=ADMIN):
    return {"user_id": user, "text": text, "channel_id": "C1", "trigger_id": "t"}


def said(mock):
    return "\n".join(json.dumps(a, default=str, ensure_ascii=False)
                     for c in mock.call_args_list
                     for a in list(c.args) + list(c.kwargs.values()))


def test_only_an_admin_may_edit(fake):
    play([A], [B], [(21, 17), (19, 21)])
    respond = MagicMock()
    bot.handle_edit(command("edit 1 swap", user=A), respond)
    assert "Only an admin" in said(respond)
    assert store.get_match("1")["side_a"] == [A]


def test_the_command_previews_without_writing(fake):
    play([A], [B], [(21, 17), (19, 21)])
    before = ratings()
    respond = MagicMock()
    bot.handle_edit(command("edit 1 21-17 21-19"), respond)
    assert ratings() == before
    assert "Nothing has changed yet" in said(respond)


def _press(plan_value, user=ADMIN):
    return {"user": {"id": user},
            "actions": [{"action_id": bot.EDIT_ACTION, "value": plan_value}]}


def _value_from(respond):
    for call in respond.call_args_list:
        for block in call.kwargs.get("blocks", []):
            for el in block.get("elements", []):
                if el.get("action_id") == bot.EDIT_ACTION:
                    return el["value"]
    raise AssertionError("no edit button was offered")


def test_the_button_applies_it(fake):
    play([A], [B], [(21, 17), (19, 21)])         # logged as 1-1; A really won 2-0
    respond = MagicMock()
    bot.handle_edit(command("edit 1 21-17 21-19"), respond)
    bot.handle_edit_apply(_press(_value_from(respond)), MagicMock(), MagicMock())
    assert store.get_player(A)["rating"] > store.get_player(B)["rating"]
    assert [tuple(g) for g in store.get_match("1")["games"]] == [(21, 17), (21, 19)]


def test_a_non_admin_cannot_press_the_button(fake):
    play([A], [B], [(21, 17), (19, 21)])
    respond = MagicMock()
    bot.handle_edit(command("edit 1 21-17 21-19"), respond)
    value = _value_from(respond)
    before = ratings()
    out = MagicMock()
    bot.handle_edit_apply(_press(value, user=B), MagicMock(), out)
    assert "Only an admin" in said(out)
    assert ratings() == before


def test_applying_tells_the_channel(fake, monkeypatch):
    monkeypatch.setattr(bot, "HOME_CHANNEL", "C_HOME")
    play([A], [B], [(21, 17), (19, 21)])
    respond = MagicMock()
    bot.handle_edit(command("edit 1 21-17 21-19"), respond)
    client = MagicMock()
    bot.handle_edit_apply(_press(_value_from(respond)), client, MagicMock())
    posted = client.chat_postMessage.call_args.kwargs
    assert posted["channel"] == "C_HOME"
    assert "corrected match" in posted["text"]
    assert f"<@{ADMIN}>" in posted["text"]


def test_the_button_recomputes_rather_than_trusting_the_preview(fake):
    """A match logged between the preview and the press has to be rated in."""
    play([A], [B], [(21, 17), (19, 21)])
    respond = MagicMock()
    bot.handle_edit(command("edit 1 21-17 21-19"), respond)
    value = _value_from(respond)
    play([A], [C], [(21, 10), (21, 12)])       # happens while the preview sits
    bot.handle_edit_apply(_press(value), MagicMock(), MagicMock())
    assert store.get_match("2") is not None
    assert elo.games_played(store.get_player(A)) == 4
