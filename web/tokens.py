"""RALLY's design tokens — the only place a colour or a measurement is chosen.

Every value is emitted as a CSS custom property, so components reference
`var(--ball)` and never a hex code. Changing the brand is changing this file.

The palette is the table itself, read off a blue tournament top: a deep blue
ground, white lines and a white ball, one red paddle and the wood of its
handle. Nothing else. That rations the accents for us —

  ball          the thing in play: the primary action, the live dot, the
                lines that divide the page the way they divide the table.
  wood          earned: a rating that rose, a win, a streak, the leader's rank.
  paddle        a rating that fell, a loss, and the marks that flag a panel
                as the one to look at.

The majority of every page stays quiet, so the three that aren't get noticed.
Colour is never the only signal — a glyph and a word carry the same meaning,
because a colour is the one signal a reader may not receive.

**Themes.** There are five tables to play on, and each one is nothing but those
same eleven roles filled in differently: the roles are the contract, the hexes
are not. Everything else in here — the tints behind chips, the hairlines, the
avatar colours — is *derived* from the palette rather than written out again,
so adding a sixth theme is choosing eleven colours and nothing else.
"""

# A theme is these eleven roles and no more. `scheme` is what the browser is
# told, so form controls, scrollbars and the date picker match the page.
THEMES = {
    "blue": {
        "label": "Blue table",
        "scheme": "dark",
        "colors": {
            # the table, in three depths
            "bg": "#0C2559",          # the far half
            "surface": "#10306E",     # a panel sitting on it
            "raised": "#17408C",      # a panel on a panel, and hover states
            "ink": "#081533",         # the black paddle: text on anything bright
            # the lines
            "text": "#F4F7FF",
            "muted": "#9DB2DE",
            # the three that mean something — see the module docstring
            "ball": "#FFFFFF",
            "wood": "#E8B36B",
            "wood-deep": "#C08A45",
            "paddle": "#FF6152",
            "paddle-deep": "#E03B28",
            # the filled control under the pointer, and the scrim behind a dialog:
            # both are this theme's, because "a bit lighter" is the wrong move on a
            # light ground and "nearly black" is the wrong scrim on one.
            "ball-hover": "#E6EEFF",
            "scrim": "rgba(4,14,36,.72)",
        },
        "avatars": ("#F4F7FF", "#E8B36B", "#FF8A7A", "#93B9FF"),
    },
    "green": {
        "label": "Green table",
        "scheme": "dark",
        # The other tournament top. Greens sit lower than blues at the same
        # lightness, so the ground is lifted a little to keep text off the floor.
        "colors": {
            "bg": "#0B2C22",
            "surface": "#0F3A2C",
            "raised": "#155040",
            "ink": "#06190F",
            "text": "#F1F8F3",
            "muted": "#9CC4AE",
            "ball": "#FFFFFF",
            "wood": "#E7B86F",
            "wood-deep": "#BE8D46",
            "paddle": "#FF6F5C",
            "paddle-deep": "#DF4430",
            # the filled control under the pointer, and the scrim behind a dialog:
            # both are this theme's, because "a bit lighter" is the wrong move on a
            # light ground and "nearly black" is the wrong scrim on one.
            "ball-hover": "#E8F6EC",
            "scrim": "rgba(3,20,14,.72)",
        },
        "avatars": ("#F1F8F3", "#E7B86F", "#FF8F7E", "#7FD3A8"),
    },
    "slate": {
        "label": "Slate",
        "scheme": "dark",
        # No table at all: the neutral one, for anyone who finds a coloured
        # ground tiring to read against all day.
        "colors": {
            "bg": "#16181D",
            "surface": "#1D2026",
            "raised": "#282C34",
            "ink": "#0B0C0F",
            "text": "#F2F4F8",
            "muted": "#A0A7B4",
            "ball": "#FFFFFF",
            "wood": "#E3B573",
            "wood-deep": "#B98B4C",
            "paddle": "#FF6F61",
            "paddle-deep": "#DE4536",
            # the filled control under the pointer, and the scrim behind a dialog:
            # both are this theme's, because "a bit lighter" is the wrong move on a
            # light ground and "nearly black" is the wrong scrim on one.
            "ball-hover": "#E9ECF2",
            "scrim": "rgba(6,7,10,.72)",
        },
        "avatars": ("#F2F4F8", "#E3B573", "#FF8C80", "#8FB8E8"),
    },
    "light": {
        "label": "Daylight",
        "scheme": "light",
        # A bright desk, or a projector in the meeting room. The roles do not
        # move: `ball` is still the one action worth taking, which here has to
        # be dark enough to read *on* the ground rather than white.
        "colors": {
            "bg": "#F2F5FC",
            "surface": "#FFFFFF",
            "raised": "#E7EDFA",
            "ink": "#FFFFFF",         # text sitting on a `ball`-filled control
            "text": "#101B38",
            "muted": "#5A6788",
            "ball": "#123A8C",
            "wood": "#9A6516",
            "wood-deep": "#7A4F0F",
            "paddle": "#C6372A",
            "paddle-deep": "#A32A1E",
            # the filled control under the pointer, and the scrim behind a dialog:
            # both are this theme's, because "a bit lighter" is the wrong move on a
            # light ground and "nearly black" is the wrong scrim on one.
            "ball-hover": "#0B2A6B",
            "scrim": "rgba(16,27,56,.45)",
        },
        "avatars": ("#123A8C", "#9A6516", "#C6372A", "#2F6A8F"),
    },
    "midnight": {
        "label": "Midnight",
        "scheme": "dark",
        # The dim-room one: near black, so an OLED screen turns most of the
        # page off. Text drops off pure white to keep the contrast from
        # shimmering against a ground this dark.
        "colors": {
            "bg": "#050608",
            "surface": "#0D0F14",
            "raised": "#161A21",
            "ink": "#000000",
            "text": "#E8ECF4",
            "muted": "#8A93A6",
            "ball": "#F5F8FF",
            "wood": "#D8AA69",
            "wood-deep": "#A97F41",
            "paddle": "#F2604F",
            "paddle-deep": "#C93B2C",
            # the filled control under the pointer, and the scrim behind a dialog:
            # both are this theme's, because "a bit lighter" is the wrong move on a
            # light ground and "nearly black" is the wrong scrim on one.
            "ball-hover": "#FFFFFF",
            "scrim": "rgba(0,0,0,.78)",
        },
        "avatars": ("#E8ECF4", "#D8AA69", "#F2604F", "#7FA6E0"),
    },
}

DEFAULT_THEME = "blue"

# What the picker offers, in the order it offers it.
THEME_ORDER = ("blue", "green", "slate", "light", "midnight")

# Kept as the default theme's palette: this is what `tokens.COLORS` meant before
# there were five of them, and it is still the answer to "what colour is RALLY".
COLORS = THEMES[DEFAULT_THEME]["colors"]
AVATAR_TINTS = THEMES[DEFAULT_THEME]["avatars"]

# A 4px base. Nothing on the page uses a spacing value that isn't here.
SPACE = {"s1": "4px", "s2": "8px", "s3": "12px", "s4": "16px", "s6": "24px",
         "s8": "32px", "s12": "48px", "s16": "64px", "s24": "96px"}

RADII = {"r-sm": "6px", "r": "10px", "r-lg": "14px", "r-btn": "9px"}

# Space Grotesk and Space Mono are named first so they are used wherever they
# happen to be installed, then the stack falls through to the system grotesk.
# No @font-face and no <link>: the page must make zero external requests (see
# web/pages/ladder.py), and a webfont is the one thing that would break that.
FONTS = {
    "sans": ('"Space Grotesk",ui-sans-serif,-apple-system,"Segoe UI",Inter,'
             'Roboto,Helvetica,Arial,sans-serif'),
    "mono": ('"Space Mono",ui-monospace,SFMono-Regular,"SF Mono",Menlo,'
             'Consolas,monospace'),
}

# How strong each derived value is. Written once, applied to every theme, so a
# chip can never drift from its palette and two themes can't disagree about how
# loud a hairline is.
TINT_RECIPE = (
    ("up-bg", "wood", .15), ("up-line", "wood", .42),
    ("down-bg", "paddle", .14), ("down-line", "paddle", .40),
    ("ball-bg", "ball", .10), ("ball-line", "ball", .45),
    # The sticky bar, sitting over whatever scrolls under it.
    ("nav-bg", "bg", .88),
    # A section that exists but isn't built yet, said quietly twice over.
    ("soon", "muted", .55), ("soon-dim", "muted", .45),
    # The outline numerals behind a hero, and the two washes that mark a drawn
    # game. All of them the page's own ink, so they invert with it.
    ("ghost", "text", .10), ("ghost-line", "text", .40),
    ("wash", "text", .07), ("wash-strong", "text", .30),
)
# Hairlines, not shadows: the structure is drawn with 1px lines at three
# strengths, the way a table is marked out, so panels separate without a single
# box-shadow on the page. Drawn from `text`, which is why they stay visible on
# a light ground — there they are dark lines rather than pale ones.
LINE_RECIPE = (("line", .10), ("line-mid", .18), ("line-strong", .32))


def rgba(hex_colour, alpha):
    """`#E8B36B` at .15 → `rgba(232,179,107,.15)`. The one place a colour is
    allowed to become transparent, so no component writes its own rgba()."""
    value = hex_colour.lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    r, g, b = (int(value[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{str(alpha).lstrip('0')})"


def palette(theme=DEFAULT_THEME):
    """Every colour custom property for one theme — the eleven roles, the tints
    derived from them, the hairlines, and the avatar set."""
    spec = THEMES.get(theme) or THEMES[DEFAULT_THEME]
    colors = spec["colors"]
    out = dict(colors)
    out["up"], out["down"] = colors["wood"], colors["paddle"]
    for name, source, alpha in TINT_RECIPE:
        out[name] = rgba(colors[source], alpha)
    for name, alpha in LINE_RECIPE:
        out[name] = rgba(colors["text"], alpha)
    for i, tint in enumerate(spec["avatars"]):
        out[f"avatar-{i}"] = tint
    # Told to the browser as well as to us: form controls, scrollbars and the
    # date picker follow `color-scheme`, and get this wrong and a light page
    # renders a black date picker.
    out["scheme"] = spec["scheme"]
    return out


# Backwards-compatible views of the default theme, for anything that still reads
# a group by name rather than asking for a palette.
SEMANTIC = {"up": COLORS["wood"], "down": COLORS["paddle"]}
TINTS = {name: rgba(COLORS[source], alpha) for name, source, alpha in TINT_RECIPE}
LINES = {name: rgba(COLORS["text"], alpha) for name, alpha in LINE_RECIPE}


def _block(selector, values):
    return selector + "{" + ";".join(f"--{k}:{v}" for k, v in values.items()) + "}"


def css_root():
    """Every token as a custom property: the default theme on `:root`, each
    other theme behind `[data-theme=…]`, and the measurements once.

    The default is the blue table rather than whatever the reader's system
    prefers, because a table is blue. A reader who prefers light gets Daylight —
    that choice is made in the one-line script in web/layout.py, before first
    paint, so nobody watches the page change colour after it has drawn.
    """
    out = [_block(":root", palette(DEFAULT_THEME))]
    for name in THEME_ORDER:
        if name != DEFAULT_THEME:
            out.append(_block(f':root[data-theme="{name}"]', palette(name)))
    fixed = {}
    for group in (SPACE, RADII):
        fixed.update(group)
    fixed["sans"], fixed["mono"] = FONTS["sans"], FONTS["mono"]
    out.append(_block(":root", fixed))
    # The page is painted in whatever the theme says, including the browser's
    # own furniture.
    out.append("html{color-scheme:var(--scheme)}")
    return "".join(out)


def avatar_tint(uid):
    """A stable tint slot for one player. Deterministic, so nobody's colour
    moves — and returned as a custom property rather than a hex, so the colour
    it resolves to follows the theme."""
    return f"var(--avatar-{sum(ord(c) for c in str(uid)) % len(AVATAR_TINTS)})"
