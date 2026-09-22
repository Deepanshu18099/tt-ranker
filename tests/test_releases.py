"""The release notes, and the version line that sends people to them."""
from unittest.mock import patch

import pytest

import releases
from api import index
from web import layout
from web.pages import releases as page


@pytest.fixture
def app():
    index.app.config["TESTING"] = True
    return index.app.test_client()


def body(html):
    """The document without its stylesheet — the sheet carries section comments
    and a page's content is what these assertions are about."""
    return html[html.index("<body>"):]


# --- the notes themselves --------------------------------------------------

def test_the_notes_run_newest_first():
    dates = [r.date for r in releases.RELEASES]
    assert dates == sorted(dates, reverse=True)


def test_the_current_release_is_the_newest_one():
    """The footer prints CURRENT. If it could drift from the top of the list,
    the site would advertise a version that isn't on the page."""
    assert releases.CURRENT is releases.RELEASES[0]
    assert releases.CURRENT.date in releases.current_label()
    assert releases.CURRENT.name in releases.current_label()


def test_every_entry_says_something():
    for r in releases.RELEASES:
        assert r.date and r.name and r.summary
        assert r.changes, f"{r.name} has no notes"
        assert all(note.strip() for note in r.changes)


def test_a_date_is_a_date():
    from datetime import datetime
    for r in releases.RELEASES:
        datetime.strptime(r.date, "%Y-%m-%d")


def test_the_pull_requests_are_numbers_where_they_are_given():
    """A note traces back to the change that made it. Two entries predate the
    fork's PRs and carry none, which is honest rather than invented."""
    for r in releases.RELEASES:
        assert all(isinstance(n, int) and n > 0 for n in r.prs)


# --- the page --------------------------------------------------------------

def test_the_page_lists_every_release():
    from web import components as c
    html = body(page.render())
    for r in releases.RELEASES:
        # Through the same escaping the page uses — a summary with an
        # apostrophe in it is still the same summary.
        assert c.e(r.name) in html and page._prose(r.summary) in html


def test_the_newest_one_is_marked_as_current():
    html = body(page.render())
    assert html.count("Current</span>") == 1
    assert html.index("Current</span>") < html.index(releases.RELEASES[1].name)


def test_a_command_in_a_note_is_set_as_code():
    assert page._prose("run `/tt log`") == "run <code>/tt log</code>"


def test_a_note_cannot_smuggle_markup_in():
    """Escaped first, then the backticks become tags — so only the marks we put
    there mean anything."""
    said = page._prose("<script>alert(1)</script> `ok`")
    assert "<script>" not in said
    assert "&lt;script&gt;" in said and "<code>ok</code>" in said


def test_the_page_asks_the_network_for_nothing():
    html = page.render()
    assert "http://" not in html and "https://" not in html
    assert "<link" not in html and "@import" not in html


def test_it_is_not_in_the_top_bar():
    """A page you read once when you notice something changed, not one you
    check. The ladder is the product."""
    assert "/releases" not in layout.nav()
    assert all(href != "/releases" for _, href, _ in layout.NAV_ITEMS)


def test_the_version_line_is_in_the_footer_of_every_page():
    html = layout.document("Anything", "<p>hi</p>")
    assert releases.current_label() in html
    assert 'href="/releases"' in html


# --- the route -------------------------------------------------------------

@pytest.mark.parametrize("path", ["/releases", "/api/index/releases"])
def test_the_page_is_served_whichever_path_vercel_hands_us(app, path):
    with patch("bot.refresh_names"):
        response = app.get(path)
    assert response.status_code == 200
    assert b"Releases" in response.data


def test_the_notes_do_not_need_a_database(app):
    """They ship with the code. A page with nothing to look up has no business
    503-ing because the KV credentials are missing."""
    with patch("kv.kv_available", return_value=False):
        assert app.get("/releases").status_code == 200
        assert app.get("/ladder").status_code == 503
