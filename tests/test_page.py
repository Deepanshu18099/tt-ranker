"""The public ladder page. Rendering is pure, so none of this needs a database."""
import re

import page


def P(rating=1000, wins=0, losses=0, gw=0, gl=0, streak=0):
    return {"rating": rating, "wins": wins, "losses": losses, "draws": 0,
            "games_won": gw, "games_lost": gl, "peak": rating, "streak": streak,
            "best_streak": max(streak, 0), "matches": wins + losses,
            "points_won": 0, "points_lost": 0, "joined": "", "last_played": "",
            "last_match": ""}


def render(players=None, names=None, recent=None, delta=None, played=None,
           placement=6, **kw):
    return page.render(players or {}, names or {}, recent or [],
                       delta or {}, played or {}, placement, **kw)


def sub(html):
    return re.search(r'<p class="sub">(.*?)</p>', html, re.S).group(1)


# --- self-containment ------------------------------------------------------

def test_the_page_makes_no_external_requests():
    """It renders inside a Vercel function behind whatever network the viewer
    has; a web font or CDN would be a blank page waiting to happen."""
    html = render({"U1": P(1042, 6, 2, 14, 6)}, {"U1": "Sagnik"})
    assert "http://" not in html and "https://" not in html
    assert "<link" not in html and "@import" not in html


def test_it_declares_itself_to_mobile():
    html = render()
    assert 'name="viewport"' in html and "initial-scale=1" in html


# --- names -----------------------------------------------------------------

def test_a_chosen_name_is_what_shows():
    html = render({"U1": P(1042, 6, 2, 14, 6)}, {"U1": "Sagnik"})
    assert "Sagnik" in html and "U1" not in sub(html)


def test_a_missing_name_falls_back_to_something_short():
    """Better a stable stub than a blank row — and it nudges them to set one."""
    html = render({"U08V0KSE092": P(1042, 6, 2, 14, 6)})
    assert "@E092" in html


def test_names_are_escaped():
    html = render({"U1": P(1042, 6, 2, 14, 6)}, {"U1": '<script>alert(1)</script>'})
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


# --- what it says when there is nothing to show ---------------------------

def test_an_empty_ladder_invites_the_first_game():
    html = render()
    assert "Nobody has joined yet" in sub(html)
    assert "/tt log" in html


def test_before_anyone_qualifies_it_counts_down():
    """The state this launches in, so it has to read as progress not emptiness."""
    html = render({"U1": P(1000, 1, 0, 3, 1), "U2": P(1000, 0, 1, 1, 3)},
                  {"U1": "Sagnik", "U2": "Vikash"})
    assert "Sagnik is 2 away" in sub(html)     # 4 games played, 6 to qualify
    assert '<span class="lead-rating num">2</span>' in html   # countdown is the numeral
    assert "games until the ladder has a leader" in html


def test_a_signed_up_but_unplayed_ladder_says_so():
    html = render({"U1": P(), "U2": P()}, {"U1": "Sagnik"})
    assert "no games played yet" in sub(html)


# --- the ladder itself -----------------------------------------------------

def test_players_are_ranked_and_the_leader_leads():
    html = render({"U1": P(998, 3, 4, 8, 9), "U2": P(1042, 6, 2, 14, 6)},
                  {"U1": "Aman", "U2": "Sagnik"})
    assert html.index("Sagnik") < html.index("Aman")
    assert '<span class="lead-rating num">1042</span>' in html


def test_only_qualified_players_are_ranked():
    html = render({"U1": P(1042, 6, 2, 14, 6), "U2": P(1005, 1, 0, 2, 1)},
                  {"U1": "Sagnik", "U2": "Newbie"}, placement=6)
    assert "Still placing" in html
    assert "3 to go" in html             # 3 of 6 games played


def test_this_weeks_movement_is_shown_next_to_the_rating():
    """The page's whole job is answering 'did I move?'"""
    html = render({"U1": P(1042, 6, 2, 14, 6)}, {"U1": "Sagnik"}, delta={"U1": 13})
    assert "13 this week" in html and 'class="move up"' in html
    html = render({"U1": P(1042, 6, 2, 14, 6)}, {"U1": "Sagnik"}, delta={"U1": -8})
    assert "8 this week" in html and 'class="move down"' in html
    html = render({"U1": P(1042, 6, 2, 14, 6)}, {"U1": "Sagnik"}, played={"U1": 2})
    assert "level this week" in html


def test_playing_and_breaking_even_is_not_the_same_as_not_playing():
    """They used to render identically, which made "level" unreadable."""
    even = render({"U1": P(1042, 6, 2, 14, 6)}, {"U1": "S"}, played={"U1": 3})
    absent = render({"U1": P(1042, 6, 2, 14, 6)}, {"U1": "S"})
    assert "level this week" in even
    assert "no games this week" in absent


# --- recent sessions -------------------------------------------------------

def test_recent_sessions_name_the_winner_first():
    recent = [{"side_a": ["U2"], "side_b": ["U1"], "games": [[21, 14], [11, 0]],
               "games_a": 0, "games_b": 2, "deltas": {"U2": -9, "U1": 9}}]
    html = render({"U1": P(1042, 6, 2, 14, 6)}, {"U1": "Sagnik", "U2": "Aman"},
                  recent=recent)
    block = html[html.index("Recent sessions"):]
    assert block.index("Sagnik") < block.index("Aman")
    assert "beat" in block


def test_a_drawn_session_is_not_described_as_a_win():
    recent = [{"side_a": ["U1"], "side_b": ["U2"], "games": [[21, 14], [14, 21]],
               "games_a": 1, "games_b": 1, "deltas": {"U1": 0, "U2": 0}}]
    html = render({"U1": P(1042, 6, 2, 14, 6)}, {"U1": "A", "U2": "B"}, recent=recent)
    assert "drew with" in html


def test_game_scores_appear_for_each_session():
    recent = [{"side_a": ["U1"], "side_b": ["U2"], "games": [[21, 14], [11, 0]],
               "games_a": 2, "games_b": 0, "deltas": {"U1": 9, "U2": -9}}]
    html = render({"U1": P(1042, 6, 2, 14, 6)}, {"U1": "A", "U2": "B"}, recent=recent)
    assert "21&#8211;14" in html and "11&#8211;0" in html


# --- liveness --------------------------------------------------------------

def test_the_page_refreshes_itself_only_while_being_looked_at():
    """Reloading a backgrounded tab every minute is traffic nobody reads."""
    html = render()
    assert "visibilityState" in html and "location.reload()" in html


def test_gains_are_green_and_losses_red():
    """Convention, reinforcing the triangles — never the only signal, since the
    glyphs say the same thing without colour."""
    up = render({"U1": P(1042, 6, 2, 14, 6)}, {"U1": "S"}, delta={"U1": 13})
    down = render({"U1": P(1042, 6, 2, 14, 6)}, {"U1": "S"}, delta={"U1": -13})
    assert "&#9650;" in up and "&#9660;" in down
    assert ".up{color:#3FCB86}" in up and ".down{color:#FF7A70}" in down


# --- spins -----------------------------------------------------------------

def test_the_spins_table_ranks_the_richest_first():
    html = page.render({"U1": P(), "U2": P()}, {"U1": "Sagnik", "U2": "Aman"}, [], {}, {}, 6,
                       spins=[("U2", 7000, 2000), ("U1", 3000, -2000)], start_spins=5000)
    block = html[html.index("<h2>Spins</h2>"):]
    assert block.index("Aman") < block.index("Sagnik")
    assert "7,000" in block and "2,000 up" in block and "2,000 down" in block
    assert "10,000 in circulation" in block


def test_a_table_where_nobody_has_moved_is_not_shown():
    """Twelve identical 5,000s is not a leaderboard; it's noise above the
    matches people actually came to read."""
    html = page.render({"U1": P(), "U2": P()}, {}, [], {}, {}, 6,
                       spins=[("U1", 5000, 0), ("U2", 5000, 0)], start_spins=5000)
    assert "<h2>Spins</h2>" not in html


def test_the_ladder_renders_without_spins_at_all():
    assert "<h2>Spins</h2>" not in render({"U1": P(1042, 6, 2, 14, 6)})
# --- filters ---------------------------------------------------------------

def recent_between(*pairs):
    out = []
    for i, (a, b) in enumerate(pairs, start=1):
        out.append({"id": str(i), "side_a": [a], "side_b": [b], "games": [[11, 7]],
                    "games_a": 1, "games_b": 0, "deltas": {a: 5, b: -5},
                    "applied_at": "2026-09-17T18:42:00+05:30"})
    return out


def test_the_filter_bar_lists_every_player_and_the_day_chips():
    html = render({"U1": P(1042, 6, 2, 14, 6), "U2": P()}, {"U1": "Sagnik", "U2": "Aman"},
                  recent=recent_between(("U1", "U2")))
    bar = html[html.index('id="filters"'):html.index("</form>")]
    assert '<option value="U1"' in bar and ">Sagnik<" in bar and ">Aman<" in bar
    assert ">Today<" in bar and ">Yesterday<" in bar and ">This week<" in bar
    assert 'type="date"' in bar
    assert 'class="on" href="?"' in bar       # "All" is lit when nothing is filtered


def test_an_active_filter_is_lit_and_named_in_the_heading():
    html = page.render({"U1": P(), "U2": P()}, {"U1": "Sagnik", "U2": "Aman"},
                       recent_between(("U1", "U2")), {}, {}, 6,
                       filters={"player": "U1", "day": "today", "label": "today"})
    assert "Sessions · Sagnik · today" in html
    assert 'class="on" href="?player=U1&amp;day=today"' in html
    assert '<option value="U1" selected>' in html
    assert "1 session." in html


def test_an_empty_filtered_list_says_so_instead_of_vanishing():
    html = page.render({"U1": P(), "U2": P()}, {"U1": "Sagnik"}, [], {}, {}, 6,
                       filters={"player": "U1", "day": "yesterday", "label": "yesterday"})
    assert "No sessions match" in html and 'id="filters"' in html


def test_a_filtered_list_shows_more_than_the_default_glance():
    lots = recent_between(*[("U1", "U2")] * 20)
    plain = page.render({"U1": P(), "U2": P()}, {}, lots, {}, {}, 6)
    filtered = page.render({"U1": P(), "U2": P()}, {}, lots, {}, {}, 6,
                           filters={"player": "U1", "day": "", "label": ""})
    assert plain.count('class="session"') == page.RECENT_SHOWN
    assert filtered.count('class="session"') == 20


def test_each_session_says_when_it_happened():
    html = render({"U1": P(), "U2": P()}, {}, recent=recent_between(("U1", "U2")))
    assert "Thu 17 Sep, 18:42" in html


def test_filter_values_are_escaped():
    html = page.render({"U1": P()}, {"U1": '<b>x</b>'}, [], {}, {}, 6,
                       filters={"player": "U1", "day": "", "label": '"><script>'})
    assert '"><script>' not in html and "&quot;&gt;&lt;script&gt;" in html
    assert "&lt;b&gt;x&lt;/b&gt;" in html


def test_a_non_iso_day_still_fills_the_date_picker():
    """parse_day accepts `16/9`, which <input type="date"> silently drops —
    leaving the picker blank on a view that is in fact filtered. The route
    resolves it to ISO and passes it as `iso`."""
    filters = {"player": "", "day": "16/9", "label": "16 Sep", "iso": "2026-09-16"}
    html = render(recent=[{"side_a": ["U1"], "side_b": ["U2"], "games": [[21, 14]],
                           "games_a": 1, "games_b": 0, "deltas": {"U1": 5, "U2": -5},
                           "applied_at": "2026-09-16T12:00:00+05:30"}],
                  filters=filters)
    assert 'value="2026-09-16"' in html
    assert 'value="16/9"' not in html
