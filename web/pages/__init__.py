"""One module per page.

Each exposes a `render(...)` that takes data and returns a whole HTML document.
None of them read the database: `api/index.py` gathers what a page needs and
hands it over, which is what keeps every page renderable inside a test.
"""
