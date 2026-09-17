"""The numbers — what the season has actually produced.

Every figure is computed from stored records, and any that can't be is absent
rather than zero. That rule is enforced in `derive.numbers`, which returns only
the entries it could work out; this page renders what it gets.
"""
from .. import components as c
from .. import derive, layout


def render(players, names, history=(), week="", log_href="", channel_hint="",
           updated="", window=0):
    figures = derive.numbers(players, history, names)
    stats = []
    if players:
        stats.append(c.stat_tile(len(players), "Players"))
    if history:
        stats.append(c.stat_tile(len(history), "Matches"))
        stats.append(c.stat_tile(sum(len(b.get("games", ())) for b in history), "Games"))

    body = [c.page_header("The Numbers", eyebrow="Season so far",
                          lead="What the ladder has produced, counted.",
                          stats=stats)]
    if not figures:
        body.append('<section class="wrap rise">' + c.empty_state(
            "Nothing to count yet",
            "A few matches and this page fills itself in.",
            "How to log a match", log_href or "/log") + "</section>")
    else:
        # Grouped by where each figure comes from, not by how many fit a row:
        # a career record and a count over recent matches are different claims.
        leaders = [row for row in figures if row[3] == "players"]
        counted = [row for row in figures if row[3] == "matches"]
        if leaders:
            body.append(c.section(
                "Leaders", f'<ul class="sc-grid">{_cards(leaders)}</ul>',
                eyebrow="From the players' own records", classes="rise-1"))
        if counted:
            body.append(c.section(
                "From the matches", f'<ul class="sc-grid">{_cards(counted)}</ul>',
                note=_window_note(window, history), classes="rise-2"))
    body.append(_rivalry(history, names))
    return layout.document("The Numbers — RALLY",
                           "".join(part for part in body if part),
                           current="Stats", log_href=log_href,
                           channel_hint=channel_hint, updated=updated)


def _cards(figures):
    return "".join(c.stat_card(label, value, detail)
                   for label, value, detail, _ in figures)


def _window_note(window, history):
    """Says what these figures were counted over, because "most" over the last
    120 matches is a different claim from "most ever"."""
    if not window or len(history) < window:
        return (f"Counted over all {len(history)} matches on record."
                if history else "")
    return (f"Counted over the last {len(history)} matches — as far back as the "
            "ladder keeps them.")


def _rivalry(history, names):
    """The most-played pair, shown as the head-to-head it is."""
    pair = derive._rivalry(history)
    if not pair:
        return ""
    (one, two), _ = pair
    h2h = derive.head_to_head(history, one, two)
    if not h2h:
        return ""
    return c.section("The rivalry", c.head_to_head(h2h, one, two, names),
                     eyebrow="Most played", classes="rise-3")
