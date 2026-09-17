"""RALLY's design tokens — the only place a colour or a measurement is chosen.

Every value is emitted as a CSS custom property, so components reference
`var(--ball)` and never a hex code. Changing the brand is changing this file.

The palette is the table itself, read off a blue tournament top: a deep blue
ground, white lines and a white ball, one red paddle and the wood of its
handle. Nothing else. That rations the accents for us —

  ball white    the thing in play: the primary action, the live dot, the
                lines that divide the page the way they divide the table.
  wood          earned: a rating that rose, a win, a streak, the leader's rank.
  paddle red    a rating that fell, a loss, and the marks that flag a panel
                as the one to look at.

The majority of every page stays blue and quiet, so the three that aren't get
noticed. Colour is never the only signal — a glyph and a word carry the same
meaning, because a colour is the one signal a reader may not receive.
"""

COLORS = {
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
}

# What "up" and "down" are made of. Named apart from the palette so a page can
# say what it means rather than what colour it wants.
SEMANTIC = {"up": COLORS["wood"], "down": COLORS["paddle"]}

# Tints of those three, for the backgrounds of small chips. Kept here so a
# component never hard-codes an rgba() and drifts from the palette.
TINTS = {
    "up-bg": "rgba(232,179,107,.15)", "up-line": "rgba(232,179,107,.42)",
    "down-bg": "rgba(255,97,82,.14)", "down-line": "rgba(255,97,82,.40)",
    "ball-bg": "rgba(255,255,255,.10)", "ball-line": "rgba(255,255,255,.45)",
}

# Hairlines, not shadows: the structure is drawn with 1px white lines at three
# strengths, the way a table is marked out, so panels separate without a single
# box-shadow on the page.
LINES = {
    "line": "rgba(244,247,255,.10)",
    "line-mid": "rgba(244,247,255,.18)",
    "line-strong": "rgba(244,247,255,.32)",
}

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

# Avatar tints, all drawn from the table: chalk, wood, paddle and the pale blue
# of the far half. Assigned by a hash of the uid so a player keeps the same one
# forever, and kept at one saturation so the leaderboard reads as one system.
AVATAR_TINTS = ("#F4F7FF", "#E8B36B", "#FF8A7A", "#93B9FF")


def css_root():
    """Every token as a custom property on :root."""
    pairs = []
    for group in (COLORS, SEMANTIC, TINTS, LINES, SPACE, RADII):
        pairs += [f"--{name}:{value}" for name, value in group.items()]
    pairs.append(f"--sans:{FONTS['sans']}")
    pairs.append(f"--mono:{FONTS['mono']}")
    return ":root{" + ";".join(pairs) + "}"


def avatar_tint(uid):
    """A stable tint for one player. Deterministic, so nobody's colour moves."""
    return AVATAR_TINTS[sum(ord(c) for c in str(uid)) % len(AVATAR_TINTS)]
