"""The VMock mark: the one image on the site.

Kept apart from web/icons.py on purpose. The icon set there is one style —
geometric, hairline, `currentColor`, recoloured by whatever theme is on. The
company mark is none of those: it is a fixed asset with a textured gradient
inside it, and redrawing it in the house style would make it a different mark.

**Why not an inline SVG, like everything else here.** The official SVG is 100 KB,
because the badge inside it is itself an embedded raster — a true vector of that
texture is not something we have. A 56px PNG shown at 28 is smaller and honest.

**Why a route and not a data URI.** Both keep the page off the network in the
sense the README means — no CDN, no font, nothing third-party, nothing that
blocks first paint. But 3 KB of base64 would ride along on *every* page, on
every request, and it would sit inside the document where the test suite reads:
several tests ask whether a short string is absent from the whole page, and a
blob of base64 answers yes to almost anything. So the bytes are served once from
/mark.png, cached immutably, and the document carries a nine-character path.

The favicon is served the same way, at /favicon.ico, which browsers ask for on
their own — so the document still contains no <link> at all.

Source: the official logo, cropped to the badge and quantised. The wordmark
beside it on the site is RALLY's own, not VMock's, so the two never get
confused.
"""
import base64

_MARK_56 = (
    "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"
)

_ICON_32 = (
    "iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAMAAABEpIrGAAAAwFBMVEXjUCtaUJqiM2Q6abBoO4RRlcxTWZ/QLC3d"
    "XFqHRYjJN1jf4u5oL3Pwp51Fgb56cX1VXqGYpc7xXWH/AADLMzXcTiZSkbS1NzOZNlbFNU4A//+kMFnbRjVOkMZO"
    "O4ajTFtPZaeqVaq7yuOFRYT/AP/3w6t+MWhVqv8/fr3CQGN/f/8/H1+APIUzTJlUjL/URD91Qn8+g8MAAP87PJNO"
    "icN/AH/euMAAAAD9/PzVNjNHh8PMNlFFV6REeLnaRS1zNXgnZi6vAAAAQHRSTlP9+/3+/PgW+v/5/f/6//4JnP8J"
    "AaYcHi8eawGhnpctDmgD/5gB/6sDjZ8CCP8KZGxo/wH/YgL/AP/+/P7+/v3+7+09DwAAAipJREFUeNpVk+d2nDAQ"
    "RmckoQUWY7Z5ncTdTu9VSBS9/1v5Gwk7yfzgcPiurgYVcrnOnLNfLosQJtbdzZVzt7scUHqeguhCUYTvrdYjqrPp"
    "4xNg3cd3GBtC0FqzAMzdFp8XwDrLQU88tQBGAGxYVY1NBIAP7gzDJz1NoGQCNpWKxpgrIQhT2SAAiNC2MgNy06DM"
    "KUJ6aS16D0VSIEdFZWKUF7a/H+ituyzQfhHyHIz+ookq1yt3DQPyog0CaAE0x0bVC3GOHjoBptRmkBY1N6qsM1G+"
    "d5QEkmUB8xjVIFWjyvqafqFFXazv7grdCjCOzTCU5bDUC+rkF0Lf9+skWI+s6tXJyUpSaZMKMegNiEKPPzf9BoK5"
    "74d68F4YmrD8WKW1KJjxVMPqpO+hUIMQJHk7JQVrAIg8gJ68r8VBbTtJaVGMwq2JKHOrWgBOm8v/KoheZ8Ww8gLI"
    "v2N91jBw8+c/BYq6lGtRMPagzArpYvZoY083ckBwQgxvTIPGk/1ZgYWySLG7EVuIPfREZVkSeTxLGPw5ufvKxCay"
    "HAGlZso1g5R8j920jKFpDqzsUz7PifJH7KbrqgopQxBhSJGnBNDebenh9DNytFGZZBBgzgDRYbdLh7aCoMJRjBmY"
    "fY7ng9vKsZdrIYABIEMxde7kiPz54iwGvwgE2Ur+dPXsvQDKAJjnJLg4T/nfy2s7AJ8G9IAZ5ouDy/kCuB+3oL69"
    "MQqC1f7r0bnDcv0fAT/ceaSTR3ctAAAAAElFTkSuQmCC"
)

MARK_PNG = base64.b64decode(_MARK_56)
ICON_PNG = base64.b64decode(_ICON_32)

MARK_PATH = "/mark.png"
ICON_PATH = "/favicon.ico"

# Shown at 28 CSS pixels from a 56px source, so it stays crisp on a 2x screen.
MARK_SIZE = 28

# It never changes without its filename changing, so it is never revalidated.
CACHE = "public, max-age=31536000, immutable"


def mark(classes="vmock"):
    """The badge.

    `alt=""` and not a word of description: it is always inside the brand link,
    which already names the place in its aria-label, and a screen reader reading
    "VMock logo, VMock Rally, table tennis league" serves nobody. Width and
    height are on the tag so the bar does not reflow when it arrives.
    """
    return (f'<img class="{classes}" src="{MARK_PATH}" width="{MARK_SIZE}" '
            f'height="{MARK_SIZE}" alt="" decoding="async">')


def asset(path):
    """(bytes, content type) for one of the two asset paths, or None."""
    if path.endswith(MARK_PATH):
        return MARK_PNG, "image/png"
    if path.endswith(ICON_PATH):
        return ICON_PNG, "image/png"
    return None
