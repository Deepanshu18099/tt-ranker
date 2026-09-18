"""Titles — what there is to win here besides a number, and who has it.

The page exists because a badge you meet in passing on the ladder raises a
question it can't answer: what *are* these, and what would I have to do to get
one? So every title is listed, held or not, with what it takes underneath it.

A title going spare is shown rather than hidden. "Nobody is On Fire this week"
is a fact about the week, and a more interesting one than a shorter list.
"""
import awards

from .. import components as c
from .. import layout


def render(table, players, names, log_href="", channel_hint="", updated="",
           view=""):
    held = sum(1 for _, uid in awards.holder_rows(table) if uid)
    stats = [c.stat_tile(len(awards.TITLES), "Titles"),
             c.stat_tile(held, "Held")]
    body = [c.page_header(
        "Titles", eyebrow="Beyond the rating",
        lead="A rating says how good you are. These say everything else.",
        stats=stats)]

    cards = "".join(_card(title, uid, players, names, view)
                    for title, uid in awards.holder_rows(table))
    body.append(f'<section class="wrap rise rise-1"><ul class="titles">{cards}</ul>'
                "</section>")
    body.append(
        '<section class="wrap rise rise-2"><p class="note wide">'
        f"Weekly titles count the rolling {awards.WEEK_DAYS} days, the same week "
        "the ladder's <em>This week</em> filter means, and need "
        f"{awards.WEEK_MIN_MATCHES} matches in it before they'll rank you — a "
        "one-match week is not a claim. The all-time one needs "
        f"{awards.CAREER_MIN_GAMES} games. Nothing here is stored: every title is "
        "worked out afresh from the results, so none of them can drift out of "
        "step with the ladder. Level on both counts and nobody holds it."
        "</p></section>")
    return layout.document("Titles — RALLY", "".join(body), current="Titles",
                           log_href=log_href, channel_hint=channel_hint,
                           updated=updated)


def _card(title, uid, players, names, view=""):
    if uid:
        href = f"/player/{uid}" + (f"?view={view}" if view else "")
        holder = (f'<a class="title-holder" href="{c.e(href)}">'
                  f'{c.avatar(uid, names, "avatar-sm")}'
                  f'<span>{c.e(c.display_name(uid, names))}</span></a>')
    else:
        holder = '<span class="title-holder is-vacant">Going spare</span>'
    return (f'<li class="title-card {c.e(title.tone)}">'
            f'<div class="title-card-top">{c.title_chip(title.key)}</div>'
            f'<p class="title-blurb">{c.e(title.blurb)}</p>'
            f'{holder}</li>')
