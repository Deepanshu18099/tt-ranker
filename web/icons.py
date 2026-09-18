"""The icon set — one style, drawn inline.

Geometric, 1.75px stroke, currentColor, sized by CSS. Inline because the page
makes no external requests, which rules out an icon font or a sprite fetched
from a CDN; hand-drawn rather than pulled from a package because the whole set
is six glyphs and a dependency would cost more than it saves.

No xmlns attribute: inline SVG in an HTML document doesn't need one, and the
page has a test asserting it contains no URLs at all.
"""

_OPEN = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
         'stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" '
         'aria-hidden="true" focusable="false">')


def _icon(paths):
    return _OPEN + paths + "</svg>"


def flame():
    """A streak that is running hot."""
    return _icon('<path d="M12 3c2.5 3 1 5 3 7 1.4 1.4 2 2.8 2 4.2A5 5 0 0 1 7 '
                 '14.2C7 11 9.5 9.6 10 7c.3-1.6-.2-3-.2-3S11 5 12 3Z"/>')


def snow():
    """A streak that has gone cold."""
    return _icon('<path d="M12 3v18M4.5 7.5l15 9M19.5 7.5l-15 9"/>')


def plus():
    return _icon('<path d="M12 5v14M5 12h14"/>')


def menu():
    return _icon('<path d="M4 7h16M4 12h16M4 17h16"/>')


def search():
    return _icon('<circle cx="11" cy="11" r="7"/><path d="m20 20-3.6-3.6"/>')


def swap():
    """Two ways to read the same list."""
    return _icon('<path d="M7 4v13M4 14l3 3 3-3M17 20V7M14 10l3-3 3 3"/>')


def arrow_up():
    return _icon('<path d="M12 19V5M6 11l6-6 6 6"/>')


def arrow_down():
    return _icon('<path d="M12 5v14M18 13l-6 6-6-6"/>')


def palette():
    """Which table you'd rather play on. A ball, and the swatch it sits on."""
    return _icon('<path d="M4 6h16v12H4z"/><circle cx="12" cy="12" r="2.6"/>'
                 '<path d="M8 6v12"/>')


# --- brand geometry --------------------------------------------------------
# Abstract, never illustrative: an arc is the flight of a rally, a circle is the
# ball, a straight run of hairlines is the table. They sit behind content at low
# opacity and are decorative, so they carry aria-hidden and no title.

def rally_arc():
    """The hero's trajectory: a ball, its arc, and the far edge of the table."""
    return ('<svg class="hero-arc" viewBox="0 0 400 220" fill="none" '
            'aria-hidden="true" focusable="false">'
            '<path d="M8 196C60 74 150 26 250 26s118 52 142 92" stroke="currentColor" '
            'stroke-width="1.5" stroke-dasharray="5 7"/>'
            '<path d="M8 196C74 132 168 96 392 118" stroke="currentColor" '
            'stroke-width="1.5" opacity=".55"/>'
            '<circle cx="250" cy="26" r="9" fill="currentColor"/>'
            '<path d="M0 196h400" stroke="currentColor" stroke-width="1" opacity=".5"/>'
            '<path d="M200 168v28" stroke="currentColor" stroke-width="1" opacity=".5"/>'
            "</svg>")


def net():
    """The featured panel's backdrop: a net, seen end-on."""
    lines = "".join(
        f'<path d="M{x} 0v200" stroke="currentColor" stroke-width="1" opacity=".5"/>'
        for x in range(10, 320, 22))
    return ('<svg class="featured-net" viewBox="0 0 320 200" preserveAspectRatio="none" '
            'fill="none" aria-hidden="true" focusable="false">'
            + lines +
            '<path d="M0 12h320M0 188h320" stroke="currentColor" stroke-width="1.5"/>'
            "</svg>")
