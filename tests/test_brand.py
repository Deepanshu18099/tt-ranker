"""Whose league this is: the VMock mark in the bar, and how it gets there."""
from unittest.mock import patch

import pytest

from api import index
from web import brand, layout


@pytest.fixture
def app():
    index.app.config["TESTING"] = True
    return index.app.test_client()


def test_the_bar_leads_with_the_mark_and_says_whose_it_is():
    html = layout.nav()
    assert 'aria-label="VMock Rally, table tennis league"' in html
    # The mark leads, then the wordmark it belongs to.
    assert html.index('src="/mark.png"') < html.index("</span>Rally</span>")
    assert "Table Tennis League" in html


def test_the_mark_is_decorative_inside_the_link():
    """The link is already named; a screen reader announcing the image too would
    read the same thing twice."""
    assert 'alt=""' in brand.mark()
    assert 'aria-label' not in brand.mark()


def test_the_mark_reserves_its_own_space():
    """Width and height on the tag, so the bar doesn't jump when it lands."""
    assert f'width="{brand.MARK_SIZE}" height="{brand.MARK_SIZE}"' in brand.mark()


def test_the_document_carries_a_path_and_not_the_bytes():
    """3 KB of base64 on every page would ride along on every request, and it
    would sit inside the document where several tests read — a blob of base64
    contains almost any short string you care to assert is absent."""
    html = layout.document("Test", "<p>hi</p>")
    assert "base64" not in html
    assert html.count("/mark.png") == 2      # the bar and the footer
    # Still no scheme anywhere, and still nothing for the browser to <link> to.
    assert "http://" not in html and "https://" not in html
    assert "<link" not in html


@pytest.mark.parametrize("path", ["/mark.png", "/api/index/mark.png"])
def test_the_mark_is_served_whichever_path_vercel_hands_us(app, path):
    response = app.get(path)
    assert response.status_code == 200
    assert response.headers["Content-Type"] == "image/png"
    assert response.data.startswith(b"\x89PNG\r\n")
    assert response.data == brand.MARK_PNG


def test_the_favicon_is_served_without_the_page_asking_for_it(app):
    """No <link rel=icon> anywhere — browsers ask for /favicon.ico by
    themselves, which is how the document stays free of <link> entirely."""
    response = app.get("/favicon.ico")
    assert response.status_code == 200
    assert response.data == brand.ICON_PNG
    assert "favicon" not in layout.document("Test", "")


def test_an_asset_never_waits_on_the_database(app):
    """No KV configured is a 503 for a page. An image is not a page."""
    with patch("kv.kv_available", return_value=False):
        assert app.get("/mark.png").status_code == 200
        assert app.get("/ladder").status_code == 503


def test_an_asset_is_cached_until_its_name_changes(app):
    assert "immutable" in app.get("/mark.png").headers["Cache-Control"]


def test_the_mark_stays_small_enough_to_be_worth_serving():
    """A logo is not a photograph. If this ever fails, the asset was replaced
    with something that needs looking at rather than committing."""
    assert len(brand.MARK_PNG) < 8 * 1024
    assert len(brand.ICON_PNG) < 4 * 1024
