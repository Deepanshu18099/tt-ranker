"""The five tables you can play on.

A theme is eleven colour roles and nothing else, so most of what's worth
asserting here is that no theme is missing one, that everything else is derived
rather than written out again, and that the page still reaches for a custom
property instead of a hex — which is what makes a theme swap possible at all.
"""
import re

import pytest

from web import layout, styles, tokens

ROLES = ("bg", "surface", "raised", "ink", "text", "muted", "ball", "wood",
         "wood-deep", "paddle", "paddle-deep", "ball-hover", "scrim")


def luminance(hex_colour):
    value = hex_colour.lstrip("#")
    channels = [int(value[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    channels = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
                for c in channels]
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast(one, two):
    a, b = luminance(one), luminance(two)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


@pytest.mark.parametrize("theme", tokens.THEME_ORDER)
def test_every_theme_fills_every_role(theme):
    colours = tokens.THEMES[theme]["colors"]
    assert set(colours) == set(ROLES)
    assert tokens.THEMES[theme]["scheme"] in ("dark", "light")
    assert len(tokens.THEMES[theme]["avatars"]) == len(tokens.AVATAR_TINTS)


@pytest.mark.parametrize("theme", tokens.THEME_ORDER)
def test_text_is_readable_on_every_ground(theme):
    """AA on body text, and on the muted text that carries most of the labels.

    The one figure deliberately not asserted is the original blue table's red on
    a panel (4.24) — it predates the other themes and is the brand.
    """
    colours = tokens.THEMES[theme]["colors"]
    for ground in ("bg", "surface", "raised"):
        assert contrast(colours["text"], colours[ground]) >= 4.5
    assert contrast(colours["muted"], colours["bg"]) >= 4.5
    # Text sitting on a filled control has to survive too.
    assert contrast(colours["ink"], colours["ball"]) >= 4.5


@pytest.mark.parametrize("theme", tokens.THEME_ORDER)
def test_a_theme_derives_its_tints_rather_than_restating_them(theme):
    """A chip's background is its accent at a fixed alpha, every time. Restate
    one by hand and two themes start disagreeing about how loud a chip is."""
    palette = tokens.palette(theme)
    colours = tokens.THEMES[theme]["colors"]
    assert palette["up"] == colours["wood"] and palette["down"] == colours["paddle"]
    assert palette["up-bg"] == tokens.rgba(colours["wood"], .15)
    assert palette["line"] == tokens.rgba(colours["text"], .10)
    assert palette["nav-bg"] == tokens.rgba(colours["bg"], .88)


def test_rgba_reads_both_lengths_of_hex():
    assert tokens.rgba("#E8B36B", .15) == "rgba(232,179,107,.15)"
    assert tokens.rgba("#fff", .4) == "rgba(255,255,255,.4)"


def test_the_default_theme_is_the_blue_table_and_needs_no_attribute():
    """Nothing in the markup says `blue`: it is what :root already holds, so the
    page a reader who has never touched the picker gets is one stylesheet."""
    css = tokens.css_root()
    assert css.startswith(":root{--bg:#0C2559")
    assert '[data-theme="blue"]' not in css
    for theme in tokens.THEME_ORDER:
        if theme != tokens.DEFAULT_THEME:
            assert f':root[data-theme="{theme}"]{{' in css


def test_the_stylesheet_names_no_colour_of_its_own():
    """The rule that makes theming work at all: every colour in the sheet is a
    custom property, so swapping the properties swaps the page."""
    body = "".join(part for part in (
        styles.BASE, styles.NAV, styles.BUTTONS, styles.HERO, styles.TABS,
        styles.FEATURED, styles.BOARD, styles.PIECES, styles.MATCHES,
        styles.PAGES, styles.FOOTER, styles.MOTION, styles.RESPONSIVE))
    assert not re.search(r"#[0-9A-Fa-f]{3,6}\b", body)
    assert "rgba(" not in body


def test_an_avatar_asks_for_a_property_not_a_colour():
    tint = tokens.avatar_tint("U0BOB")
    assert re.fullmatch(r"var\(--avatar-\d\)", tint)
    assert tokens.avatar_tint("U0BOB") == tint      # still stable per player


def test_the_page_carries_the_picker_and_sets_the_theme_before_it_paints():
    html = layout.document("Test", "<p>hi</p>")
    head = html[:html.index("</head>")]
    # The theme is applied in the head, after the sheet: do it later and the
    # reader watches the page change colour.
    assert "localStorage" in head and "data-theme" in head
    assert head.index("<style>") < head.index("<script>")
    assert '<meta name="color-scheme" content="dark light">' in head
    for theme in tokens.THEME_ORDER:
        assert f'data-theme-set="{theme}"' in html


def test_the_picker_is_hidden_until_script_reveals_it():
    """Without script the buttons would do nothing, and a dead control is worse
    than no control."""
    assert '<details class="menu themes" id="themes" hidden>' in layout.nav()
    assert "themes.hidden = false" in layout.SCRIPT


def test_a_theme_still_costs_no_external_request():
    html = layout.document("Test", "<p>hi</p>")
    assert "http://" not in html and "https://" not in html
