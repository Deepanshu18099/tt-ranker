"""Everyone on the ladder, as cards.

The standings answer where people stand against each other; this answers who is
here. Sorted the same way the board is, so the two never disagree, with the
players still placing kept together at the end rather than mixed in at a rank
they haven't earned.
"""
import elo

from .. import components as c
from .. import derive, layout


def render(players, names, history=(), week="", view="", placement_games=4,
           week_delta=None, week_played=None, query="", compare=(),
           comparing=False, slots=0, log_href="", channel_hint="", updated="",
           titles=None):
    """`query` narrows the grid by name. It is applied here as well as in the
    browser so the no-script path and a shared link both work; with script, the
    same box filters what is already on screen and never waits for a round
    trip."""
    if query:
        want = query.strip().lower()
        players = {uid: p for uid, p in players.items()
                   if want in c.display_name(uid, names).lower()}
    ranked = sorted(((u, p) for u, p in players.items()
                     if elo.games_played(p) >= placement_games),
                    key=lambda i: (-i[1]["rating"], -elo.games_played(i[1]), i[0]))
    placing = sorted(((u, p) for u, p in players.items()
                      if elo.games_played(p) < placement_games),
                     key=lambda i: (-elo.games_played(i[1]), i[0]))

    if view == derive.OVERALL:
        delta, played = dict(week_delta or {}), dict(week_played or {})
    else:
        delta, played = derive.weekly(history, view, week)
    known = view == derive.OVERALL or bool(history)
    form = derive.form(history, view)

    def card(uid, player, rank=None):
        return c.player_card(
            uid, player, names, rank=rank, pickable=comparing,
            picked=uid in (compare or ()),
            movement=(c.movement(delta.get(uid, 0), played.get(uid, 0), compact=True)
                      if known else ""),
            form=form.get(uid, ""), href=_href(uid, view), titles=titles)

    body = [c.page_header(
        "Players", eyebrow="The league",
        lead="Everyone on the ladder, and where they are.",
        # A count of nobody is not a statistic; it is a gap where one would go.
        stats=[c.stat_tile(len(players), "Players"), c.stat_tile(len(ranked), "Ranked")]
        + ([c.stat_tile(len(placing), "Placing")] if placing else []) if players else (),
        extra=_tabs(view) + _find(query, names, view, compare, comparing, slots))]

    if not players:
        body.append('<section class="wrap rise">' + (c.empty_state(
            "Nobody by that name", f"No player here matches \u201c{c.e(query)}\u201d.",
            "Show everyone", "/players", cta_icon=False) if query else c.empty_state(
            "Nobody here yet", "Playing a match puts you on the ladder.",
            "How to log a match", log_href or "/log")) + "</section>")
    else:
        if ranked:
            body.append(c.section(
                "Ranked", '<div class="pc-grid">'
                + "".join(card(uid, p, i) for i, (uid, p) in enumerate(ranked, 1))
                + "</div>", eyebrow=f"{len(ranked)} on the board", classes="rise-1"))
        if placing:
            body.append(c.section(
                "Still placing",
                '<div class="pc-grid">'
                + "".join(card(uid, p) for uid, p in placing) + "</div>",
                note=f"{placement_games} games and they join the board above. "
                     "Their ratings are already moving.", classes="rise-2"))
    if comparing:
        body.append(c.compare_dialog())
    return layout.document("Players — RALLY", "".join(body), current="Players",
                           log_href=log_href, channel_hint=channel_hint,
                           updated=updated)


def _find(query, names, view, chosen, comparing, slots):
    """Search on the left, the compare switch on the right, and — once that is
    on — the pickers underneath it.

    Comparing is a mode rather than a permanent fixture: most visits are here to
    look someone up, and the pickers would be furniture in the way of that.
    """
    from urllib.parse import urlencode
    params = {k: v for k, v in (("view", view), ("q", query)) if v}
    if not comparing:
        params["compare"] = "1"
    href = ("?" + urlencode(params)) if params else "?"
    row = ('<div class="find">'
           + c.search_box(query, target=".pc-grid", item=".pc",
                          placeholder="Search players")
           + c.compare_toggle(comparing, href)
           + "</div>")
    if not comparing:
        return row
    return row + c.compare_tray(names, chosen, view, slots)


def _href(uid, view):
    return f"/player/{uid}" + (f"?view={view}" if view else "")


def _tabs(view):
    links = []
    for value, label in (("", "Singles"), ("doubles", "Doubles"), ("overall", "Overall")):
        on = ' class="on" aria-current="page"' if (view or "") == value else ""
        href = f"?view={value}" if value else "?"
        links.append(f'<a{on} href="{c.e(href)}" data-keep>{label}</a>')
    return ('<nav class="tabs" aria-label="Format">' + "".join(links) + "</nav>")
