"""What's changed, and when — the notes, newest first.

Not in the top bar. This is a page you read once when you notice something is
different, not one you check; the ladder is the product. So it lives in the
footer, next to the version line that sends people here in the first place.

The notes themselves are data in releases.py, written by hand. Rendering them is
all that happens here.
"""
import re

import releases

from .. import components as c
from .. import layout

# A note reads better with the command in it set as code. Escaped first,
# then the backtick pairs become tags — so anything that arrived as markup
# is inert by the time this runs, and only the marks we put there mean
# anything.
_CODE = re.compile(r"`([^`]+)`")


def render(log_href="", channel_hint="", updated=""):
    entries = releases.RELEASES
    body = [c.page_header(
        "Releases", eyebrow="What's changed",
        lead="Every change that altered what you see or what your rating does, "
             "newest first.",
        stats=[c.stat_tile(len(entries), "Releases"),
               c.stat_tile(releases.CURRENT.date, "Latest")])]
    body.append('<section class="wrap rise rise-1"><ol class="releases">'
                + "".join(_entry(r, i == 0) for i, r in enumerate(entries))
                + "</ol></section>")
    body.append(
        '<section class="wrap rise rise-2"><p class="note wide">'
        "Dated rather than numbered: a version number implies a promise about "
        "compatibility that an office ladder doesn't make, and a date answers "
        "the question people actually have. A bug fix nobody noticed doesn't "
        "get an entry — if a change didn't alter what you see or what your "
        "rating does, it isn't here."
        "</p></section>")
    return layout.document("Releases — RALLY", "".join(body), current="",
                           log_href=log_href, channel_hint=channel_hint,
                           updated=updated)


def _prose(text):
    return _CODE.sub(r"<code>\1</code>", c.e(text))


def _entry(release, latest=False):
    notes = "".join(f"<li>{_prose(note)}</li>" for note in release.changes)
    # Plain numbers, not links: the page is asserted to contain no URL at all.
    prs = (f'<span class="rel-prs num">'
           + " ".join(f"#{n}" for n in release.prs) + "</span>"
           if release.prs else "")
    tag = '<span class="rel-now">Current</span>' if latest else ""
    return (f'<li class="rel{" is-now" if latest else ""}">'
            f'<div class="rel-when"><span class="rel-date num">'
            f"{c.e(release.date)}</span>{tag}</div>"
            '<div class="rel-body">'
            f'<h2 class="rel-name">{c.e(release.name)}{prs}</h2>'
            f'<p class="rel-summary">{_prose(release.summary)}</p>'
            f'<ul class="rel-notes">{notes}</ul>'
            "</div></li>")
