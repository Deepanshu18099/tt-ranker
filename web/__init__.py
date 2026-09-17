"""The RALLY web front end.

Split from page.py so the design system has somewhere to live that isn't the
ladder page: `tokens` is the palette and scale, `styles` the stylesheet built
from them, `icons` the inline SVG set, `components` the pieces every page
shares, and `derive` the pure maths that turns stored match blobs into form,
streaks and movement.

Nothing here touches the database or Slack. Every function takes data and
returns a string, which is what keeps the pages testable without either.
"""
