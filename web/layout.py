"""The shell every RALLY page sits in: the document, the top bar, the footer.

Navigation is deliberately honest about what exists. Matches, Players and Stats
are the planned pages and they appear in the bar so the shape of the product is
legible, marked `soon` and not linked, rather than linked to a 404.
"""
from . import brand as vmock
from . import components as c
from . import icons, styles

REFRESH_SECONDS = 60

NAV_ITEMS = (
    ("Ladder", "/ladder", True),
    ("Matches", "/matches", True),
    ("Players", "/players", True),
    ("Stats", "/stats", True),
)

SCRIPT = f"""
(function(){{
  var main = document.querySelector('main');
  var soft = !!(window.history && history.pushState && window.fetch
                && window.DOMParser);

  /* --- freshness ------------------------------------------------------ */
  var since = 0;
  setInterval(function(){{
    since += 5;
    var el = document.getElementById('freshness');
    if (el) el.textContent = since < 60 ? 'Updated just now'
      : 'Updated ' + Math.floor(since/60) + ' min ago';
    if (since >= {REFRESH_SECONDS} && document.visibilityState === 'visible') {{
      since = 0;
      /* A live page refreshes itself, but it no longer throws the reader back
         to the top of it: the same swap a click does, in place. */
      if (soft) load(location.href, {{keep: true, push: false}});
      else location.reload();
    }}
  }}, 5000);

  /* --- swapping the page ---------------------------------------------- */
  function busy(on){{ document.body.classList.toggle('is-busy', on); }}

  function load(url, opts){{
    opts = opts || {{}};
    busy(true);
    fetch(url, {{credentials: 'same-origin'}})
      .then(function(r){{ if (!r.ok && r.status !== 404) throw 0; return r.text(); }})
      .then(function(html){{
        var doc = new DOMParser().parseFromString(html, 'text/html');
        var next = doc.querySelector('main');
        if (!next) throw 0;
        main.replaceWith(next);
        main = document.querySelector('main');
        document.title = doc.title;
        syncNav(doc);
        if (opts.push !== false) history.pushState({{}}, '', url);
        if (!opts.keep) {{
          window.scrollTo(0, 0);
          /* Tell a screen reader the page changed, without stealing focus
             from a filter the reader is still working through. */
          main.setAttribute('tabindex', '-1');
          main.focus({{preventScroll: true}});
        }}
        busy(false);
      }})
      .catch(function(){{ location.href = url; }});
  }}

  function syncNav(doc){{
    var from = doc.querySelectorAll('.nav-links .nav-link, .menu-panel .nav-link');
    var to = document.querySelectorAll('.nav-links .nav-link, .menu-panel .nav-link');
    for (var i = 0; i < to.length && i < from.length; i++) {{
      to[i].className = from[i].className;
      if (from[i].hasAttribute('aria-current')) to[i].setAttribute('aria-current', 'page');
      else to[i].removeAttribute('aria-current');
    }}
  }}

  function sameOrigin(link){{
    return link.host === location.host && link.protocol === location.protocol;
  }}

  document.addEventListener('click', function(ev){{
    var menu = document.getElementById('menu');
    var link = ev.target.closest && ev.target.closest('a[href]');
    /* Close the mobile menu on a click outside it, so it never traps a tap. */
    if (menu && menu.open && !menu.contains(ev.target)) menu.open = false;
    if (!link || !soft) return;
    if (link.target || link.hasAttribute('download') || ev.defaultPrevented) return;
    if (ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey || ev.button !== 0) return;
    if (!sameOrigin(link) || link.getAttribute('href').charAt(0) === '#') return;
    ev.preventDefault();
    if (menu) menu.open = false;
    /* A tab or a filter chip changes what is on the page, not which page it
       is, so the reader stays where they were looking. */
    load(link.href, {{keep: link.hasAttribute('data-keep')}});
  }});

  document.addEventListener('submit', function(ev){{
    var form = ev.target;
    if (!soft || form.method.toLowerCase() !== 'get') return;
    ev.preventDefault();
    var query = new URLSearchParams(new FormData(form));
    var url = form.getAttribute('action') || location.pathname;
    if (url === '') url = location.pathname;
    var text = query.toString();
    load(url.split('?')[0] + (text ? '?' + text : ''), {{keep: true}});
  }});

  document.addEventListener('change', function(ev){{
    var form = ev.target.form;
    if (form && form.id === 'filters') {{
      if (soft) form.dispatchEvent(new Event('submit', {{cancelable: true, bubbles: true}}));
      else form.submit();
    }}
  }});

  /* --- instant search -------------------------------------------------- */
  document.addEventListener('input', function(ev){{
    var field = ev.target;
    if (!field.hasAttribute || !field.hasAttribute('data-filter')) return;
    var box = document.querySelector(field.getAttribute('data-filter'));
    if (!box) return;
    var want = field.value.trim().toLowerCase();
    var items = box.querySelectorAll(field.getAttribute('data-filter-item'));
    var shown = 0;
    items.forEach(function(item){{
      var hay = item.getAttribute('data-search') || item.textContent.toLowerCase();
      var hit = !want || hay.indexOf(want) !== -1;
      item.hidden = !hit;
      if (hit) shown++;
    }});
    /* A day whose every match is filtered out takes its heading with it. */
    box.querySelectorAll('.day').forEach(function(day){{
      var left = day.querySelectorAll(field.getAttribute('data-filter-item')
                                      + ':not([hidden])');
      day.hidden = left.length === 0;
    }});
    var empty = field.closest('.search').querySelector('.search-empty');
    if (empty) empty.hidden = !!shown || !want;
  }});

  /* --- comparing ------------------------------------------------------- */
  function picks(){{ return Array.prototype.slice.call(
      document.querySelectorAll('.cmp-pick')); }}

  function syncCards(){{
    var chosen = picks().map(function(p){{ return p.value; }}).filter(Boolean);
    document.querySelectorAll('.pc-pick').forEach(function(card){{
      var on = chosen.indexOf(card.getAttribute('data-uid')) !== -1;
      card.classList.toggle('is-picked', on);
      card.setAttribute('aria-pressed', on ? 'true' : 'false');
    }});
    var full = document.querySelector('[data-dialog-open]');
    if (full) full.href = '/compare?' + chosen.map(function(uid){{
      return 'p=' + encodeURIComponent(uid); }}).join('&');
  }}

  document.addEventListener('click', function(ev){{
    /* The + reveals the next picker rather than asking the server for one. */
    if (ev.target.closest && ev.target.closest('[data-add-slot]')) {{
      var next = picks().filter(function(p){{ return p.hidden; }})[0];
      if (next) {{ next.hidden = false; next.disabled = false; next.focus(); }}
      var left = picks().filter(function(p){{ return p.hidden; }}).length;
      if (!left) ev.target.closest('[data-add-slot]').hidden = true;
      return;
    }}
    /* A card is a pick while comparing: into the first free slot, or out of
       the one it is in. */
    var card = ev.target.closest && ev.target.closest('.pc-pick');
    if (card) {{
      ev.preventDefault();
      var uid = card.getAttribute('data-uid');
      var all = picks(), mine = all.filter(function(p){{ return p.value === uid; }})[0];
      if (mine) {{ mine.value = ''; }}
      else {{
        var free = all.filter(function(p){{ return !p.value; }})[0];
        if (!free) return;                    /* full: the ceiling is the ceiling */
        free.hidden = false; free.disabled = false; free.value = uid;
      }}
      syncCards();
    }}
  }});
  document.addEventListener('change', function(ev){{
    if (ev.target.classList && ev.target.classList.contains('cmp-pick')) syncCards();
  }});

  /* A comparison opens where you asked for it, rather than taking the page. */
  var dialog = document.getElementById('compare-dialog');
  document.addEventListener('submit', function(ev){{
    var form = ev.target;
    if (!soft || !dialog || !form.hasAttribute('data-dialog')) return;
    if (!dialog.showModal) return;            /* older browser: let it navigate */
    var chosen = picks().map(function(p){{ return p.value; }}).filter(Boolean);
    if (chosen.length < 2) return;            /* the page says what is missing */
    ev.preventDefault();
    ev.stopImmediatePropagation();
    var url = '/compare?bare=1&' + chosen.map(function(uid){{
      return 'p=' + encodeURIComponent(uid); }}).join('&');
    var body = dialog.querySelector('.dialog-body');
    busy(true);
    fetch(url, {{credentials: 'same-origin'}})
      .then(function(r){{ return r.text(); }})
      .then(function(html){{
        body.innerHTML = html;
        busy(false);
        if (!dialog.open) dialog.showModal();
        body.focus();
      }})
      .catch(function(){{ busy(false); location.href = url.replace('bare=1&', ''); }});
  }}, true);
  document.addEventListener('click', function(ev){{
    if (!dialog) return;
    if (ev.target.closest && ev.target.closest('[data-dialog-close]')) dialog.close();
    else if (ev.target === dialog) dialog.close();   /* the backdrop */
  }});

  window.addEventListener('popstate', function(){{
    if (soft) load(location.href, {{push: false}});
  }});
  window.addEventListener('pageshow', function(){{ busy(false); }});
}})();
"""


def brand(href="/ladder"):
    """Whose league this is, then what it is.

    The VMock badge leads and RALLY's own wordmark follows it, because a
    stranger opening the link in the channel should be able to tell in one look
    that this is ours. One link, one label: the mark is decorative inside it.
    """
    return (f'<a class="brand" href="{c.e(href)}" '
            'aria-label="VMock Rally, table tennis league">'
            + vmock.mark() +
            '<span class="brand-words">'
            '<span class="brand-mark"><span class="ball"></span>Rally</span>'
            '<span class="brand-sub">Table Tennis League</span></span></a>')


def _links(current, in_menu=False):
    out = []
    for label, href, live in NAV_ITEMS:
        on = " on" if label.lower() == current.lower() else ""
        if live:
            aria = ' aria-current="page"' if on else ""
            out.append(f'<a class="nav-link{on}" href="{c.e(href)}"{aria}>{label}</a>')
        else:
            out.append(f'<span class="nav-link soon" aria-disabled="true">{label}'
                       f'<span class="soon-tag">Soon</span></span>')
    return "".join(out)


def nav(current="Ladder", log_href=""):
    """The top bar. The one action worth taking is the only filled thing in it.
    `current` is the nav item to light, or "" on a page that is none of them."""
    href = log_href or "/log"
    cta = (f'<a class="btn btn-primary" href="{c.e(href)}">{icons.plus()}'
           '<span class="btn-wide-only">Log match</span>'
           '<span class="sr-only">Log a match</span></a>')
    return (
        '<header class="nav"><div class="wrap nav-in">'
        + brand()
        + f'<nav class="nav-links" aria-label="Sections">{_links(current)}</nav>'
        + f'<div class="nav-cta">{cta}'
        + '<details class="menu" id="menu"><summary aria-label="Menu">'
        + icons.menu() + "</summary>"
        + f'<div class="menu-panel">{_links(current, in_menu=True)}</div></details>'
        + "</div></div></header>")


def footer(log_href="", channel_hint="", updated=""):
    where = f"in {c.e(channel_hint)}" if channel_hint else "in Slack"
    links = "".join(
        f'<li><a href="{c.e(href)}">{label}</a></li>' if live else
        f'<li><span class="soon">{label}</span></li>'
        for label, href, live in NAV_ITEMS)
    return (
        '<footer class="footer" id="how"><div class="wrap footer-in">'
        f"<div>{brand()}"
        f'<ul class="footer-links">{links}</ul></div>'
        "<div>"
        f'<p class="footer-note">Log a session {where} with <code>/tt log</code>. '
        "Your opponent confirms it, then both ratings move.</p>"
        '<p class="footer-note">Every game is rated on its own, so a longer session '
        "counts for more, and beating someone above you is worth more than beating "
        "someone below.</p>"
        '<p class="footer-note"><span class="live"><span class="live-dot"></span>'
        '<span id="freshness">Updated just now</span></span>'
        f'{" &middot; " + c.e(updated) if updated else ""}</p>'
        "</div></div></footer>")


def document(title, body, current="Ladder", log_href="", channel_hint="", updated=""):
    """One self-contained page: no stylesheet request, no font request, no script
    request. Everything the browser needs arrives in this response."""
    return (
        "<!doctype html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="color-scheme" content="dark">'
        '<meta name="theme-color" content="#0C2559">'
        f"<title>{c.e(title)}</title>"
        f"<style>{styles.stylesheet()}</style></head>"
        "<body>"
        '<div class="loading" aria-hidden="true"></div>'
        + nav(current, log_href)
        + f"<main>{body}</main>"
        + footer(log_href, channel_hint, updated)
        + f"<script>{SCRIPT}</script>"
        "</body></html>")
