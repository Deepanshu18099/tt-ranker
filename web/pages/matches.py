"""Every match, newest first, grouped by the day it was played.

The ladder answers "did I move?". This page answers "what happened?" — so the
match card is the unit, the filters are the furniture, and nothing is
summarised: each card keeps its individual game scores, because a 2–1 that went
11–9 in the decider is a different story from a 2–1 that didn't.
"""
from .. import components as c
from .. import derive, layout

SHOWN = 60   # a page, not an archive; the filters are how you go deeper

FILTER_GROUPS = (c.FORMAT_GROUP, c.DAY_GROUP)


def render(matches, players, names, params=None, iso="", now=None, total=None,
           log_href="", channel_hint="", updated="", titles=None):
    """`matches` is already filtered and validated by the caller — this page
    renders what it is given and never second-guesses a query string."""
    params = params or {}
    shown = list(matches[:SHOWN])
    stats = [c.stat_tile(total if total is not None else len(matches), "Matches"),
             c.stat_tile(sum(len(b.get("games", ())) for b in matches), "Games")]
    singles = sum(1 for b in matches if not b.get("doubles"))
    if singles and singles != len(matches):
        stats.append(c.stat_tile(singles, "Singles"))
        stats.append(c.stat_tile(len(matches) - singles, "Doubles"))

    body = [c.page_header("Matches", eyebrow=_eyebrow(params, names),
                          lead="Every result, as it was played.",
                          stats=stats if matches else ())]
    body.append('<section class="wrap rise rise-1">'
                + c.filter_bar(players, names, params, FILTER_GROUPS, iso=iso,
                               player_select=False, search=_find(params))
                + _count(matches, shown)
                + _days(shown, names, now, _view_of(params), titles)
                + "</section>")
    return layout.document("Matches — RALLY", "".join(body), current="Matches",
                           log_href=log_href, channel_hint=channel_hint,
                           updated=updated)


def _find(params):
    """Search by name, in the filter bar itself — it does the job the player
    picker used to, so it stands where the picker stood and takes the width
    the row has spare."""
    return c.search_box(params.get("q", ""), target=".day-list", item=".match",
                        placeholder="Search by player", label="Search matches",
                        empty_text="No match here has that name in it.",
                        standalone=False)


def _eyebrow(params, names):
    """What this list is, when it isn't everything."""
    bits = []
    if params.get("player"):
        bits.append(c.display_name(params["player"], names))
    if params.get("format"):
        bits.append(params["format"].title())
    if params.get("label"):
        bits.append(params["label"])
    return " · ".join(bits) if bits else "The league"


def _count(matches, shown):
    if not matches:
        return ""
    if len(matches) > len(shown):
        return (f'<p class="count">{len(matches)} matches, showing the latest '
                f'{len(shown)}. Narrow it with a day or a player.</p>')
    return (f'<p class="count">{len(shown)} '
            f'match{"es" if len(shown) != 1 else ""}.</p>')


def _days(matches, names, now, view, titles=None):
    if not matches:
        return c.empty_state(
            "Nothing here",
            "No match matches these filters. Try another day, or clear them.",
            "Clear filters", "?", cta_icon=False)
    if now is None:
        return f'<div class="matches">{_cards(matches, names, view, titles)}</div>'
    out = []
    for label, day, group in derive.group_by_day(matches, now):
        stamp = f'<time datetime="{day.isoformat()}">{day.day} ' \
                f'{day.strftime("%b")}</time>' if day else ""
        out.append(f'<div class="day"><div class="day-head">'
                   f'<h3>{c.e(label)}</h3>{stamp}'
                   f'<span class="day-count num">{len(group)}</span></div>'
                   f'<div class="matches">{_cards(group, names, view, titles)}'
                   "</div></div>")
    return f'<div class="day-list">{"".join(out)}</div>'


def _cards(matches, names, view=derive.OVERALL, titles=None):
    return "".join(c.match_card(blob, names, view, titles) for blob in matches)


def _view_of(params):
    """Which ladder's rating change the cards should report. Filtered to one
    format, that format's own; unfiltered, the overall figure, which is the
    only one every match in a mixed list has."""
    fmt = params.get("format") or ""
    return {"singles": "", "doubles": derive.DOUBLES}.get(fmt, derive.OVERALL)
