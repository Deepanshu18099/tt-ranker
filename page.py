"""Where the ladder page used to live.

It moved to web/pages/ladder.py when the other pages arrived and it stopped
being *the* page. This shim keeps `import page` working — it is what the Vercel
entry point and a good deal of the test suite say.
"""
from web.pages.ladder import (  # noqa: F401
    DAY_CHIPS, FILTERED_SHOWN, NOTES, RECENT_SHOWN, REFRESH_SECONDS,
    SPINS_SHOWN, VIEWS, display_name, render,
)
