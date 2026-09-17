"""When there is nothing to show: the page says which of the three it is.

A missing player, a database that isn't configured and a server that broke are
different problems with different fixes, and a reader who is told which one it
is can act on it. None of them is a blank page.
"""
from .. import components as c
from .. import layout


def _page(title, heading, body, cta_text="", cta_href="", detail=""):
    inner = ('<section class="wrap rise error-page">'
             + c.empty_state(heading, body, cta_text, cta_href, cta_icon=False)
             + (f'<pre class="error-detail">{c.e(detail)}</pre>' if detail else "")
             + "</section>")
    return layout.document(title, inner, current="")


def not_found(what="page"):
    return _page("Not found — RALLY", "Nothing here",
                 f"That {what} isn't on the ladder. It may have been a typo, or "
                 "a link from before.", "Back to the ladder", "/ladder")


def no_database():
    return _page("Not configured — RALLY", "No database yet",
                 "The ladder has nowhere to keep ratings. Set KV_REST_API_URL "
                 "and KV_REST_API_TOKEN, redeploy, and this fills in.")


def broken(detail=""):
    return _page("Something broke — RALLY", "That didn't work",
                 "The page failed to build. The ladder itself is fine — nothing "
                 "is lost, and a refresh often does it.",
                 "Back to the ladder", "/ladder", detail=detail)
