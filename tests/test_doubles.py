"""The doubles-only ladder.

It is a real rating — fed only by doubles results and rated off doubles ratings
— but a narrower claim than the singles one. A doubles result moves both
partners by the same amount, so what the maths actually pins down is the pair's
combined rating; the split between the two is never separately measured. Varied
partners break the tie, a fixed pairing does not. Every surface that shows the
board says so, and these tests hold it to that.
"""
import pytest

import bot
import elo
import store
from tests.fake_kv import FakeRedis

A, B, C, D = "U0AAA1", "U0BBB1", "U0CCC1", "U0DDD1"
WIN = [(21, 14), (21, 16)]


@pytest.fixture
def fake():
    redis = FakeRedis()
    with redis.patched():
        yield redis


def play(side_a, side_b, games=WIN, by=None):
    record = store.create_pending(side_a, side_b, games, logged_by=by or side_a[0])
    assert store.claim_pending(record["id"])
    return store.apply_match(record, confirmed_by=side_b[0])


# --- the rating is its own ---------------------------------------------------

def test_a_doubles_win_moves_the_doubles_rating(fake):
    play([A, B], [C, D])
    assert store.doubles_view(store.get_player(A))["rating"] > elo.START_RATING
    assert store.doubles_view(store.get_player(C))["rating"] < elo.START_RATING


def test_a_singles_result_never_touches_the_doubles_rating(fake):
    """The mirror of the singles guarantee, and the reason for two ladders
    rather than one filtered view."""
    play([A], [B])
    for uid in (A, B):
        player = store.get_player(uid)
        assert player["rating"] != elo.START_RATING           # overall moved
        assert store.doubles_view(player)["rating"] == elo.START_RATING
        assert elo.games_played(store.doubles_view(player)) == 0


def test_the_doubles_record_counts_only_doubles(fake):
    play([A], [C])                # singles
    play([A, B], [C, D])          # doubles
    doubles = store.doubles_view(store.get_player(A))
    assert doubles["matches"] == 1
    assert (doubles["wins"], doubles["losses"]) == (1, 0)
    assert elo.games_played(doubles) == 2
    assert store.get_player(A)["matches"] == 2                # overall counts both


def test_a_doubles_rating_is_rated_off_doubles_ratings(fake):
    """Not the overall number with singles filtered out — the history behind the
    overall number still has singles in it."""
    play([A], [C])                # shifts A's overall, not their doubles
    before = store.get_player(A)
    blob = play([A, B], [C, D])
    assert blob["before"][A] == before["rating"]              # overall: already moved
    assert blob["split_rated"]["before"][A] == elo.START_RATING   # doubles: fresh
    assert blob["split_prefix"] == store.DOUBLES
    # The old field is singles-only, so a doubles match leaves it empty and
    # /tt history keeps reading what it always did.
    assert blob["singles_rated"] == {}


def test_the_two_ratings_diverge(fake):
    play([A, B], [C, D])          # A wins doubles
    play([C], [A], games=[(21, 8)] * 3)   # A loses singles badly
    player = store.get_player(A)
    assert player["rating"] < store.doubles_view(player)["rating"]


def test_the_pool_is_conserved_on_the_doubles_ladder(fake):
    play([A, B], [C, D])
    play([C, D], [A, B], games=[(21, 10)] * 3)
    total = sum(store.doubles_view(store.get_player(u))["rating"]
                for u in (A, B, C, D))
    assert total == 4 * elo.START_RATING


def test_partners_move_together(fake):
    """The structural fact the tab has to be honest about: one number, split
    equally, so nothing in a doubles result can tell partners apart."""
    play([A, B], [C, D])
    a, b = (store.doubles_view(store.get_player(u)) for u in (A, B))
    assert a["rating"] == b["rating"]


# --- reading it back ---------------------------------------------------------

def test_a_doubles_view_is_shaped_like_an_ordinary_record(fake):
    play([A, B], [C, D])
    view = store.doubles_view(store.get_player(A))
    for field in store.INT_FIELDS:
        assert isinstance(view[field], int)
    assert bot.board_text({A: view}, view="doubles")


def test_a_record_written_before_doubles_existed_reads_as_unplayed(fake):
    legacy = {k: v for k, v in store.new_player().items()
              if not k.startswith(store.DOUBLES)}
    fake.data[store.player_key(A)] = {k: str(v) for k, v in legacy.items()}
    view = store.doubles_view(store.get_player(A))
    assert view["rating"] == elo.START_RATING
    assert elo.games_played(view) == 0


def test_undo_restores_the_doubles_record_too(fake):
    play([A, B], [C, D])
    before = {u: store.get_player(u) for u in (A, B, C, D)}
    blob = play([A, B], [C, D])
    store.undo_match(blob)
    assert {u: store.get_player(u) for u in (A, B, C, D)} == before


# --- the boards --------------------------------------------------------------

def test_the_doubles_board_leaves_out_singles_only_players(fake, monkeypatch):
    monkeypatch.setattr(bot, "DOUBLES_PLACEMENT_GAMES", 2)
    play([A, B], [C, D])
    play([A], [B], games=[(21, 5)] * 3)
    board = bot.board_text(store.doubles_players(store.all_players()),
                           view="doubles", placement=2)
    assert all(f"<@{u}>" in board for u in (A, B, C, D))
    assert "Still placing" not in board


def test_the_doubles_board_carries_the_caveat(fake, monkeypatch):
    """Not a footnote we can drop: without it the number reads as a claim about
    a person that the maths never makes."""
    monkeypatch.setattr(bot, "DOUBLES_PLACEMENT_GAMES", 1)
    play([A, B], [C, D])
    board = bot.board_text(store.doubles_players(store.all_players()),
                           view="doubles", placement=1).lower()
    assert "doubles only" in board
    assert "both partners move by the same amount" in board
    assert "`/tt board singles`" in board


@pytest.mark.parametrize("word", ["doubles", "double", "2v2", "pairs"])
def test_the_ways_to_ask_for_doubles(fake, word, monkeypatch):
    from unittest.mock import MagicMock
    monkeypatch.setattr(bot, "DOUBLES_PLACEMENT_GAMES", 1)
    play([A, B], [C, D])
    respond = MagicMock()
    bot.handle_board(command(f"board {word}"), respond)
    assert "Doubles ladder" in said(respond)


def command(text, user=A):
    return {"user_id": user, "text": text, "channel_id": "C1", "trigger_id": "t"}


def said(mock):
    import json
    return "\n".join(json.dumps(a, default=str, ensure_ascii=False)
                     for c in mock.call_args_list for a in c.args)


def test_the_card_shows_doubles_once_any_have_been_played(fake):
    from unittest.mock import MagicMock
    play([A, B], [C, D])
    respond = MagicMock()
    bot.handle_me(command("me"), respond)
    assert "*Doubles*" in said(respond)
    assert "*Singles*" not in said(respond)


def test_the_card_leaves_doubles_out_until_there_are_any(fake):
    from unittest.mock import MagicMock
    play([A], [B])
    respond = MagicMock()
    bot.handle_me(command("me"), respond)
    assert "*Doubles*" not in said(respond)


# --- the page ----------------------------------------------------------------

def test_the_page_has_a_doubles_tab(fake):
    import page
    html = page.render({}, {}, [], {}, {}, 4, view="doubles")
    assert 'href="?view=doubles"' in html
    assert '<a class="on" aria-current="page" href="?view=doubles"' in html


def test_the_doubles_tab_states_the_caveat(fake):
    import page
    html = page.render({}, {}, [], {}, {}, 4, view="doubles")
    assert "moves both partners by the same amount" in html
    assert "Singles is the tab that can" in html


def test_the_doubles_tab_never_borrows_the_overall_figure(fake):
    """The weekly counters count every game, so they would be a lie beside a
    doubles-only rating. With no doubles matches to sum, the tab says nothing."""
    import page
    players = {A: dict(store.new_player(), rating=1200, matches=9,
                       games_won=9, wins=3)}
    html = page.render(players, {A: "Ada"}, [], {A: 40}, {A: 9}, 1, view="doubles")
    assert "Ada" in html and "this week" not in html
    # Overall does show it, so the absence above means something.
    assert "+40" in page.render(players, {A: "Ada"}, [], {A: 40}, {A: 9}, 1,
                                view="overall")


def test_the_doubles_tab_moves_on_doubles_matches(fake):
    """Given doubles matches, movement is summed from the doubles Elo in them."""
    import page
    players = {A: dict(store.new_player(), rating=1200, matches=9,
                       games_won=9, wins=3)}
    history = [{"side_a": [A, "U0X"], "side_b": ["U0Y", "U0Z"], "games_a": 2,
                "games_b": 1, "doubles": True, "week": "tt:wk:2026-W38",
                "deltas": {A: 40}, "split_rated": {"deltas": {A: 12}}}]
    html = page.render(players, {A: "Ada"}, [], {A: 40}, {A: 9}, 1, view="doubles",
                       history=history, week="tt:wk:2026-W38")
    assert "+12" in html and "+40" not in html


def test_no_format_tab_carries_the_spins_table(fake):
    """Spins are won on fixtures, not on a ladder, so they belong to no format
    — they have a board of their own instead."""
    import page
    for view in ("", "doubles", "overall"):
        html = page.render({}, {}, [], {}, {}, 4, view=view,
                           spins=[(A, 6000, 1000)], start_spins=5000, circulating=5000)
        assert "Play money" not in html
    # ...and the spins board does show it, so the check isn't vacuous.
    assert "Play money" in page.render({}, {}, [], {}, {}, 4, board="spins",
                                       spins=[(A, 6000, 1000)], start_spins=5000,
                                       circulating=5000)
