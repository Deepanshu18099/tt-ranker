"""The singles-only ladder.

It exists because a doubles result is one number split between two people: a
player who only ever partners the same person has a rating the maths cannot pin
down, since only the pair's total is determined. Singles has no such hole.
"""
import pytest

import elo
import bot
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


# --- the two ratings move independently ------------------------------------

def test_a_singles_win_moves_both_ratings(fake):
    play([A], [B])
    a = store.get_player(A)
    assert a["rating"] > elo.START_RATING
    assert store.singles_view(a)["rating"] > elo.START_RATING


def test_a_doubles_result_never_touches_the_singles_rating(fake):
    """The whole point. A doubles-only player stays at the start line."""
    play([A, B], [C, D])
    for uid in (A, B, C, D):
        player = store.get_player(uid)
        assert player["rating"] != elo.START_RATING          # overall moved
        assert store.singles_view(player)["rating"] == elo.START_RATING
        assert elo.games_played(store.singles_view(player)) == 0


def test_the_singles_record_counts_only_singles(fake):
    play([A, B], [C, D])          # doubles
    play([A], [C])                # singles
    singles = store.singles_view(store.get_player(A))
    assert singles["matches"] == 1
    assert (singles["wins"], singles["losses"]) == (1, 0)
    assert elo.games_played(singles) == 2
    assert store.get_player(A)["matches"] == 2               # overall counts both


def test_the_two_ratings_diverge(fake):
    """Win your singles, lose your doubles, and the boards disagree — which is
    the information the singles board exists to carry."""
    play([A], [B])                # A wins singles
    play([C, D], [A, B])          # A loses doubles
    player = store.get_player(A)
    assert player["rating"] < store.singles_view(player)["rating"]


def test_a_singles_rating_is_rated_off_singles_ratings(fake):
    """Not the overall number with doubles filtered out — the history that
    produced the overall number still has doubles in it."""
    play([A, B], [C, D])          # shifts A's overall, not their singles
    before = store.get_player(A)
    blob = play([A], [C])
    assert blob["before"][A] == before["rating"]          # overall: already moved
    assert blob["singles_rated"]["before"][A] == elo.START_RATING   # singles: fresh


def test_the_pool_is_conserved_on_both_ladders(fake):
    play([A], [B])
    play([B], [A], games=[(21, 10)] * 3)
    overall = sum(store.get_player(u)["rating"] for u in (A, B))
    singles = sum(store.singles_view(store.get_player(u))["rating"] for u in (A, B))
    assert overall == singles == 2 * elo.START_RATING


# --- reading it back -------------------------------------------------------

def test_a_singles_view_is_shaped_like_an_ordinary_record(fake):
    """So every piece of ranking and display code works on it unchanged."""
    play([A], [B])
    view = store.singles_view(store.get_player(A))
    for field in store.INT_FIELDS:
        assert isinstance(view[field], int)
    assert bot.board_text({A: view}, view="singles")


def test_a_record_written_before_singles_existed_reads_as_unplayed(fake):
    """Not as a zero rating, which would put them bottom of a board they have
    never played on."""
    legacy = {k: v for k, v in store.new_player().items()
              if not k.startswith(store.SINGLES)}
    fake.data[store.player_key(A)] = {k: str(v) for k, v in legacy.items()}
    view = store.singles_view(store.get_player(A))
    assert view["rating"] == elo.START_RATING
    assert elo.games_played(view) == 0


def test_undo_restores_the_singles_record_too(fake):
    play([A], [B])
    before = store.get_player(A)
    blob = play([A], [B])
    store.undo_match(blob)
    assert store.get_player(A) == before


# --- the boards ------------------------------------------------------------

def test_the_singles_board_leaves_out_doubles_only_players(fake, monkeypatch):
    monkeypatch.setattr(bot, "PLACEMENT_GAMES", 2)
    play([A], [B])                          # 2 singles games each
    play([C, D], [A, B], games=[(21, 5)] * 3)
    board = bot.board_text(store.singles_players(store.all_players()),
                           view="singles")
    assert f"<@{A}>" in board and f"<@{B}>" in board
    assert "Still placing" in board          # C and D have no singles games


def test_each_board_says_which_one_it_is(fake, monkeypatch):
    monkeypatch.setattr(bot, "PLACEMENT_GAMES", 1)
    play([A], [B])
    players = store.all_players()
    assert "singles only" in bot.board_text(
        store.singles_players(players), view="singles").lower()
    assert "singles and doubles together" in bot.board_text(
        players, view="overall").lower()


# --- the Slack command -----------------------------------------------------

def command(text, user=A):
    return {"user_id": user, "text": text, "channel_id": "C1", "trigger_id": "t"}


def said(mock):
    import json
    return "\n".join(json.dumps(a, default=str, ensure_ascii=False)
                     for c in mock.call_args_list for a in c.args)


def test_board_singles_shows_the_singles_ladder(fake, monkeypatch):
    from unittest.mock import MagicMock
    monkeypatch.setattr(bot, "PLACEMENT_GAMES", 1)
    play([A], [B])
    respond = MagicMock()
    bot.handle_board(command("board singles"), respond)
    assert "Singles ladder" in said(respond)


@pytest.mark.parametrize("word", ["singles", "single", "solo", "1v1"])
def test_the_ways_to_ask_for_singles(fake, word, monkeypatch):
    from unittest.mock import MagicMock
    monkeypatch.setattr(bot, "PLACEMENT_GAMES", 1)
    play([A], [B])
    respond = MagicMock()
    bot.handle_board(command(f"board {word}"), respond)
    assert "Singles ladder" in said(respond)


def test_asking_for_a_doubles_board_explains_why_there_isnt_one(fake):
    from unittest.mock import MagicMock
    respond = MagicMock()
    bot.handle_board(command("board doubles"), respond)
    assert "can't say who did what" in said(respond)


def test_the_card_shows_both_ratings_once_singles_have_been_played(fake):
    from unittest.mock import MagicMock
    play([A], [B])
    respond = MagicMock()
    bot.handle_me(command("me"), respond)
    assert "*Singles*" in said(respond)


def test_the_card_leaves_singles_out_until_there_are_any(fake):
    from unittest.mock import MagicMock
    play([A, B], [C, D])
    respond = MagicMock()
    bot.handle_me(command("me"), respond)
    assert "*Singles*" not in said(respond)


# --- the page --------------------------------------------------------------

def test_the_page_has_a_tab_for_each_view(fake):
    import page
    html = page.render({}, {}, [], {}, {}, 6)
    assert 'href="?view=overall"' in html and 'class="tabs"' in html


def test_singles_is_the_tab_you_land_on(fake):
    """It is the honest ladder — a doubles result can't say who did what."""
    import page
    html = page.render({}, {}, [], {}, {}, 6)
    assert '<a class="on" href="?">Singles</a>' in html
    assert page.VIEWS[0][1] == "Singles"


def test_the_singles_view_explains_itself(fake):
    import page
    assert "no doubles result has ever touched these numbers" in \
        page.render({}, {}, [], {}, {}, 6)


def test_weekly_movement_is_hidden_on_singles_and_shown_on_overall(fake):
    """The weekly figures count every game, so they'd be a lie next to a
    singles-only rating."""
    import page
    players = {A: dict(store.new_player(), rating=1100, games_won=10, wins=5)}
    singles = page.render(players, {A: "S"}, [], {A: 25}, {A: 4}, 6)
    overall = page.render(players, {A: "S"}, [], {A: 25}, {A: 4}, 6, view="overall")
    assert "25 this week" in overall
    assert "this week" not in singles


def test_the_singles_board_has_its_own_qualifying_bar(fake):
    """Singles games are a subset of all games, so the same bar leaves the
    singles board empty while the overall one is full."""
    assert bot.SINGLES_PLACEMENT_GAMES < bot.PLACEMENT_GAMES
    play([A], [B], games=[(21, 14)] * bot.SINGLES_PLACEMENT_GAMES)
    board = bot.board_text(store.singles_players(store.all_players()),
                           title="Singles ladder", view="singles",
                           placement=bot.SINGLES_PLACEMENT_GAMES)
    assert f"<@{A}>" in board and "No one has played" not in board


def test_the_overall_bar_is_untouched(fake):
    play([A], [B], games=[(21, 14)] * bot.SINGLES_PLACEMENT_GAMES)
    board = bot.board_text(store.all_players(), view="overall")
    assert "Still placing" in board          # 4 games is short of the overall 6


def test_an_old_singles_link_still_lands_on_singles(fake):
    """?view=singles was pasted into the channel before singles became the
    default; those links have to keep working and light the right tab."""
    import page
    legacy = page.render({}, {}, [], {}, {}, 6, view="")     # what the route folds it to
    assert '<a class="on" href="?">Singles</a>' in legacy


def test_overall_is_still_reachable(fake):
    import page
    html = page.render({}, {}, [], {}, {}, 6, view="overall")
    assert '<a class="on" href="?view=overall">Overall</a>' in html
    assert "no doubles result has ever touched" not in html
