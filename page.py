"""
The live ladder as a web page — one self-contained HTML document.

Linked from the Slack channel and opened mostly on phones, usually seconds after
a game, to answer one question: *did I move?* Everything here serves that. The
rating is the loudest thing on the page, this week's change sits right beside it,
and the person reading can find their own row without scrolling past a hero.

Design notes, so later edits don't drift:

  The ground is the table: a deep blue-green with one white centre line. Colour
  beyond that is spent only on the two things a reader is looking for — green
  for a rating that went up, red for one that went down. That is convention
  rather than invention, and convention is right here: nobody glancing at their
  own row should have to decode a palette. The triangles say the same thing, so
  colour is never the only signal.

  The structure is the ladder. Rungs are hairlines, not cards, and the rank
  numbers sit on a vertical line that runs the length of the list the way the
  centre line runs the length of the table. No shadows, no rounded panels.

  The numerals are the scoreboard. Mono, tabular, large — used for figures that
  line up in columns, never for labels.

No external requests: the page renders inside a Vercel function and a strict
network is assumed, so every style is inline and there are no web fonts.
"""
import html
from datetime import datetime
from urllib.parse import urlencode

import elo

REFRESH_SECONDS = 60

CSS = """
*,*::before,*::after{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{
  margin:0;background:#0E3A46;color:#EAF2F1;
  font:400 17px/1.5 ui-sans-serif,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  -webkit-font-smoothing:antialiased;
}
.num{
  font-family:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,monospace;
  font-variant-numeric:tabular-nums;letter-spacing:-.02em;
}
main{max-width:46rem;margin:0 auto;padding:2.5rem 1.25rem 4rem}
a{color:#F6903A}
a:focus-visible,button:focus-visible{outline:2px solid #F6903A;outline-offset:3px}

h1{margin:0;font-size:1.95rem;font-weight:650;letter-spacing:-.022em;line-height:1.15}
.sub{margin:.5rem 0 0;max-width:34rem;color:#9FBEC6;font-size:1rem}

/* the lead: whoever is top, at scoreboard size */
.lead{margin:2.25rem 0 0;padding:1.5rem 0 1.75rem;border-top:2px solid #EAF2F1;
      border-bottom:1px solid rgba(234,242,241,.16)}
.lead-rating{display:block;font-size:4.6rem;line-height:.9;font-weight:600}
.lead-name{margin:.65rem 0 0;font-size:1.3rem;font-weight:600;letter-spacing:-.01em}
.lead-form{margin:.3rem 0 0;color:#9FBEC6;font-size:.95rem}

/* the ladder: rungs, with a centre line the ranks sit on */
ol.ladder{list-style:none;margin:2rem 0 0;padding:0;position:relative}
ol.ladder::before{content:"";position:absolute;left:1.05rem;top:0;bottom:0;
  width:1px;background:rgba(234,242,241,.2)}
.rung{display:grid;grid-template-columns:2.1rem 1fr auto;align-items:baseline;
  gap:.85rem;padding:.85rem 0;border-bottom:1px solid rgba(234,242,241,.12)}
.rank{grid-column:1;justify-self:center;position:relative;z-index:1;
  background:#0E3A46;padding:.15rem 0;color:#9FBEC6;font-size:.95rem;font-weight:600}
.rank.top{color:#EAF2F1}
.who{grid-column:2;min-width:0}
.name{display:block;font-weight:600;letter-spacing:-.008em;overflow-wrap:anywhere}
.form{display:block;margin-top:.15rem;color:#9FBEC6;font-size:.85rem}
.score{grid-column:3;text-align:right;white-space:nowrap}
.rating{font-size:1.5rem;font-weight:600}
.move{display:block;margin-top:.1rem;font-size:.82rem;color:#9FBEC6}
/* Green up, red down — the convention people read without thinking. The
   triangles carry the same meaning, so colour is never the only signal. */
.up{color:#3FCB86}
.down{color:#FF7A70}

/* Tabs: links, not buttons — each view is its own URL, so one can be pasted
   into the channel and it works with no script. */
.tabs{display:flex;gap:.35rem;margin:1.75rem 0 0;border-bottom:1px solid rgba(234,242,241,.16)}
.tabs a{display:inline-block;padding:.5rem .85rem;color:#9FBEC6;text-decoration:none;
  font-size:.95rem;font-weight:600;border-bottom:2px solid transparent;margin-bottom:-1px}
.tabs a:hover{color:#EAF2F1}
.tabs a.on{color:#EAF2F1;border-bottom-color:#EAF2F1}

h2{margin:2.75rem 0 .35rem;font-size:1.05rem;font-weight:650;letter-spacing:-.01em}
.note{margin:0 0 .9rem;color:#9FBEC6;font-size:.9rem;max-width:34rem}

.placing{margin:0;padding:0;list-style:none;display:flex;flex-wrap:wrap;gap:.45rem}
.placing li{border:1px solid rgba(234,242,241,.2);padding:.3rem .6rem;
  color:#C8DCE1;font-size:.88rem}
.placing .need{color:#9FBEC6}

/* spins: same rungs as the ladder, so it reads as a second table rather than
   a different page. Gold only on the rank of the leader; gain/loss reuse the
   ladder's green and red so nobody learns a second convention. */
ol.spins{list-style:none;margin:1rem 0 0;padding:0;position:relative}
ol.spins::before{content:"";position:absolute;left:1.05rem;top:0;bottom:0;
  width:1px;background:rgba(234,242,241,.2)}
.spins .rung{padding:.6rem 0}
.spins .rating{font-size:1.2rem}
.spins .move{margin-top:0}
/* filters: chips in the same hairline style as the placing list, so they read
   as controls on this table rather than a toolbar from another app. The
   active chip is filled; nothing else on the page is, so it can't be missed. */
.filters{display:flex;flex-wrap:wrap;align-items:center;gap:.45rem;margin:0 0 .9rem}
.filters a,.filters select,.filters input,.filters button{
  font:inherit;font-size:.88rem;color:#C8DCE1;background:transparent;
  border:1px solid rgba(234,242,241,.2);padding:.3rem .6rem;text-decoration:none}
.filters a.on{background:#EAF2F1;color:#0E3A46;border-color:#EAF2F1;font-weight:600}
.filters select{max-width:12rem}
.filters input{color-scheme:dark}
.filters .sep{width:1px;height:1.2rem;background:rgba(234,242,241,.2);margin:0 .2rem}
.count{margin:0 0 .5rem;color:#9FBEC6;font-size:.85rem}
.session .when{color:#9FBEC6;font-weight:400;font-size:.85rem;margin-left:auto}

.session{padding:.9rem 0;border-bottom:1px solid rgba(234,242,241,.12)}
.session:last-of-type{border-bottom:none}
.sides{display:flex;flex-wrap:wrap;align-items:baseline;gap:.5rem;font-weight:600}
.sides .beat{color:#9FBEC6;font-weight:400}
.games{margin:.35rem 0 0;display:flex;flex-wrap:wrap;gap:.3rem}
.games span{border:1px solid rgba(234,242,241,.22);padding:.1rem .4rem;font-size:.8rem;
  color:#C8DCE1}
.deltas{margin:.4rem 0 0;color:#9FBEC6;font-size:.85rem}

footer{margin-top:3rem;padding-top:1.25rem;border-top:1px solid rgba(234,242,241,.16);
  color:#9FBEC6;font-size:.88rem}
footer p{margin:.4rem 0}
.empty{margin:2.25rem 0 0;padding:1.5rem 0;border-top:2px solid #EAF2F1;
       border-bottom:1px solid rgba(234,242,241,.16);font-size:1.15rem}

@media (min-width:40rem){
  main{padding:3.5rem 2rem 5rem}
  h1{font-size:2.6rem}
  .lead-rating{font-size:6rem}
  .rating{font-size:1.75rem}
}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
"""

SCRIPT = f"""
(function(){{
  var f = document.getElementById('filters');
  if (f) f.addEventListener('change', function(){{ f.submit(); }});
  var since = 0, el = document.getElementById('freshness');
  setInterval(function(){{
    since += 5;
    if (el) el.textContent = since < 60 ? 'updated just now'
      : 'updated ' + Math.floor(since/60) + ' min ago';
    if (since >= {REFRESH_SECONDS} && document.visibilityState === 'visible') {{
      location.reload();
    }}
  }}, 5000);
}})();
"""


def _e(text):
    return html.escape(str(text), quote=True)


def display_name(uid, names):
    """What to call someone. Falls back to the tail of their Slack id, which is
    at least stable and short, rather than an empty row."""
    return names.get(uid) or f"@{uid[-4:]}"


def _record(player):
    wins, losses, draws = player["wins"], player["losses"], player["draws"]
    out = f"{wins}-{losses}" + (f"-{draws}" if draws else "")
    games = elo.games_played(player)
    return f"{out} · {player['games_won']} of {games} games"


def _movement(delta, played=0):
    """"Level" and "didn't play" are different facts that used to look
    identical. Saying which in words beats a coloured dot competing with red."""
    if not played and not delta:
        return '<span class="move">no games this week</span>'
    if not delta:
        return '<span class="move">level this week</span>'
    if delta > 0:
        return f'<span class="move up">&#9650; {delta} this week</span>'
    return f'<span class="move down">&#9660; {abs(delta)} this week</span>'


def _streak(player):
    streak = player["streak"]
    if streak >= 3:
        return f" · {streak} in a row"
    if streak <= -3:
        return f" · {abs(streak)} lost in a row"
    return ""


# Singles first, and first means default: it is the honest ladder, since a
# doubles result is one number split between two people and can't say who did
# what. "" is singles; ?view=overall is everything. The old ?view=singles links
# still resolve here — the route folds them onto "".
VIEWS = (("", "Singles"), ("overall", "Overall"))
SPINS_SHOWN = 10
RECENT_SHOWN = 8       # the default glance
FILTERED_SHOWN = 50    # once someone has asked for a day or a player, show it


def _tabs(view):
    """One URL per view, so a tab can be pasted into the channel."""
    links = []
    for value, label in VIEWS:
        on = ' class="on"' if (view or "") == value else ""
        href = f"?view={value}" if value else "?"
        links.append(f'<a{on} href="{_e(href)}">{label}</a>')
    return f'<nav class="tabs">{"".join(links)}</nav>'


def render(players, names, recent, week_delta, week_played, placement_games,
           channel_hint="", updated="", view="", spins=None, start_spins=0,
           circulating=None, filters=None):
    """The whole page. Pure — every input is passed in, so it renders in a test
    without a database or a Slack client.

    `players` is whichever record set the view wants: pass singles views in for
    the singles tab. The ranking and rendering below don't know the difference,
    which is the point of shaping a singles record like an ordinary one.
    """
    singles = view != "overall"
    ranked = sorted(((u, p) for u, p in players.items()
                     if elo.games_played(p) >= placement_games),
                    key=lambda i: (-i[1]["rating"], -elo.games_played(i[1]), i[0]))
    placing = sorted(((u, p) for u, p in players.items()
                      if elo.games_played(p) < placement_games),
                     key=lambda i: (-elo.games_played(i[1]), i[0]))

    parts = ['<h1>Table tennis ladder</h1>']
    parts.append(f'<p class="sub">{_headline(players, ranked, placing, names, placement_games)}</p>')
    parts.append(_tabs(view))
    if singles:
        parts.append('<p class="note">Singles only, on its own rating — no '
                     'doubles result has ever touched these numbers. A doubles '
                     'result is one figure split between two people, so it can '
                     "say how a pair did but not who did what.</p>")
    parts.append(_lead(ranked, placing, names, week_delta, placement_games))
    parts.append(_rungs(ranked, names, None if singles else week_delta, week_played))
    parts.append(_placing(placing, names, placement_games))
    # Overall tab only: a spins table is neither singles nor doubles, and the
    # singles view is there to be one thing.
    if not singles:
        parts.append(_spins(spins or [], names, start_spins, circulating))
    parts.append(_recent(recent, names, players, filters or {}))
    parts.append(_footer(placement_games, channel_hint, updated))

    body = "\n".join(p for p in parts if p)
    return (
        "<!doctype html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="color-scheme" content="dark">'
        '<meta name="theme-color" content="#0E3A46">'
        "<title>Table tennis ladder</title>"
        f"<style>{CSS}</style></head>"
        f"<body><main>{body}</main><script>{SCRIPT}</script></body></html>"
    )


def _headline(players, ranked, placing, names, placement_games):
    if not players:
        return ("Nobody has joined yet. Play a game, log it in Slack with "
                "<code>/tt log</code>, and the first rating appears here.")
    people = f"{len(players)} player{'s' if len(players) != 1 else ''}"
    if not ranked:
        closest = placing[0] if placing else None
        if closest and elo.games_played(closest[1]):
            need = placement_games - elo.games_played(closest[1])
            return (f"{people} so far. Nobody has played {placement_games} games yet — "
                    f"{_e(display_name(closest[0], names))} is {need} away, and "
                    "everyone starts at 1000.")
        return (f"{people} signed up, no games played yet. "
                f"{placement_games} games each and this fills up.")
    return f"{people}, {len(ranked)} of them ranked. Every game counts; ratings move as you play."


def _lead(ranked, placing, names, week_delta, placement_games):
    if ranked:
        uid, player = ranked[0]
        return (
            '<section class="lead">'
            f'<span class="lead-rating num">{player["rating"]}</span>'
            f'<p class="lead-name">{_e(display_name(uid, names))}</p>'
            f'<p class="lead-form">Top of the ladder · {_e(_record(player))}'
            f'{_e(_streak(player))}</p>'
            "</section>")
    if placing and elo.games_played(placing[0][1]):
        uid, player = placing[0]
        need = placement_games - elo.games_played(player)
        return (
            '<section class="lead">'
            f'<span class="lead-rating num">{need}</span>'
            f'<p class="lead-name">'
            f'{"game" if need == 1 else "games"} until the ladder has a leader</p>'
            f'<p class="lead-form">{_e(display_name(uid, names))} is closest, on '
            f'{elo.games_played(player)}.</p>'
            "</section>")
    return ('<section class="empty">Log the first session in Slack and this becomes '
            "a ladder.</section>")


def _rungs(ranked, names, week_delta, week_played):
    """week_delta of None means "don't show movement" — the weekly figures count
    every game, so they would be a lie next to a singles-only rating."""
    if not ranked:
        return ""
    rows = []
    for i, (uid, player) in enumerate(ranked, start=1):
        rows.append(
            '<li class="rung">'
            f'<span class="rank num{" top" if i == 1 else ""}">{i}</span>'
            f'<span class="who"><span class="name">{_e(display_name(uid, names))}</span>'
            f'<span class="form">{_e(_record(player))}{_e(_streak(player))}</span></span>'
            f'<span class="score"><span class="rating num">{player["rating"]}</span>'
            f'{_movement(week_delta.get(uid, 0), week_played.get(uid, 0)) if week_delta is not None else ""}</span>'
            "</li>")
    return '<ol class="ladder">' + "".join(rows) + "</ol>"


def _placing(placing, names, placement_games):
    if not placing:
        return ""
    chips = []
    for uid, player in placing[:24]:
        need = placement_games - elo.games_played(player)
        chips.append(f'<li>{_e(display_name(uid, names))} '
                     f'<span class="need num">{need} to go</span></li>')
    return (f"<h2>Still placing</h2>"
            f'<p class="note">{placement_games} games and you join the ladder above. '
            "Ratings are already moving.</p>"
            f'<ul class="placing">{"".join(chips)}</ul>')


def _spins(spins, names, start_spins, circulating=None):
    """The spins leaderboard. `spins` is [(uid, held, net)], richest first —
    what betting.standings() returns. Only shown once somebody has actually
    moved: a table of identical opening balances tells nobody anything."""
    if not spins or not any(net for _, _, net in spins):
        return ""
    rows = []
    for i, (uid, held, net) in enumerate(spins[:SPINS_SHOWN], start=1):
        if net > 0:
            move = f'<span class="move up">&#9650; {net:,} up</span>'
        elif net < 0:
            move = f'<span class="move down">&#9660; {abs(net):,} down</span>'
        else:
            move = '<span class="move">where they started</span>'
        rows.append(
            '<li class="rung">'
            f'<span class="rank num{" top" if i == 1 else ""}">{i}</span>'
            f'<span class="who"><span class="name">{_e(display_name(uid, names))}</span></span>'
            f'<span class="score"><span class="rating num">{held:,}</span>{move}</span>'
            "</li>")
    # Passed in from betting.circulating(), which counts open stakes; summing
    # this table would drop anything currently riding on a fixture.
    total = circulating if circulating is not None else sum(h for _, h, _ in spins)
    more = (f" Showing the top {SPINS_SHOWN} of {len(spins)}." if len(spins) > SPINS_SHOWN
            else "")
    return ("<h2>Spins</h2>"
            f'<p class="note">Play money, bet on fixtures in Slack. Everyone opened with '
            f'{start_spins:,} and nothing mints more, so a spin won is a spin somebody '
            f'else lost. {total:,} in circulation, open bets included.{more}</p>'
            '<ol class="spins">' + "".join(rows) + "</ol>")


DAY_CHIPS = (("", "All"), ("today", "Today"), ("yesterday", "Yesterday"),
             ("week", "This week"))


def _recent(recent, names, players, filters):
    """The match list, with the player and day filters above it.

    `filters` is {"player": uid, "day": what was asked for, "label": how to say
    it} — already validated by the caller, so anything here is safe to echo.
    The filters are plain links and a GET form: they work with no script, and
    the one line of script merely saves the tap on a Go button.
    """
    player = filters.get("player") or ""
    day = filters.get("day") or ""
    label = filters.get("label") or ""
    filtered = bool(player or day)
    if not recent and not filtered and not players:
        return ""

    heading = "Recent sessions"
    if filtered:
        bits = [_e(display_name(player, names))] if player else []
        if label:
            bits.append(_e(label))
        heading = "Sessions · " + " · ".join(bits)

    rows = []
    for blob in recent[:FILTERED_SHOWN if filtered else RECENT_SHOWN]:
        a = " & ".join(_e(display_name(u, names)) for u in blob["side_a"])
        b = " & ".join(_e(display_name(u, names)) for u in blob["side_b"])
        ga, gb = blob["games_a"], blob["games_b"]
        if ga == gb:
            head = f'<span>{a}</span><span class="beat">drew with</span><span>{b}</span>'
        elif ga > gb:
            head = f'<span>{a}</span><span class="beat">beat</span><span>{b}</span>'
        else:
            head = f'<span>{b}</span><span class="beat">beat</span><span>{a}</span>'
        score = f'<span class="beat num">{max(ga, gb)}&#8211;{min(ga, gb)}</span>'
        when = _when(blob.get("applied_at", ""))
        games = "".join(f"<span class='num'>{g[0]}&#8211;{g[1]}</span>"
                        for g in blob["games"])
        deltas = " · ".join(
            f"{_e(display_name(u, names))} "
            f"<span class='num'>{blob['deltas'][u]:+d}</span>"
            for u in blob["side_a"] + blob["side_b"])
        rows.append(f'<div class="session"><div class="sides">{head}{score}{when}</div>'
                    f'<div class="games">{games}</div>'
                    f'<p class="deltas">{deltas}</p></div>')

    if filtered:
        shown = len(rows)
        if not recent:
            count = '<p class="count">No sessions match. Try another day, or clear the filters.</p>'
        elif len(recent) > shown:
            count = f'<p class="count">{len(recent)} sessions, showing the latest {shown}.</p>'
        else:
            count = f'<p class="count">{shown} session{"s" if shown != 1 else ""}.</p>'
    else:
        count = ""

    return (f"<h2>{heading}</h2>" + _filter_bar(players, names, player, day, filters.get("iso", ""))
            + count + "".join(rows))


def _when(iso):
    """`Tue 16:42` — the day and the clock, enough to place a session without
    reading a full timestamp. Blank for records too old to carry one."""
    if not iso:
        return ""
    try:
        when = datetime.fromisoformat(iso)
    except ValueError:
        return ""
    # Day number written by hand: %-d is glibc-only and local dev may be anywhere.
    return (f'<span class="when num">{when.strftime("%a")} {when.day} '
            f'{when.strftime("%b, %H:%M")}</span>')


def _filter_bar(players, names, player, day, iso=""):
    def href(**changes):
        params = {"player": player, "day": day}
        params.update(changes)
        query = urlencode({k: v for k, v in params.items() if v})
        return "?" + query if query else "?"

    chips = []
    for value, text in DAY_CHIPS:
        on = ' class="on"' if (day or "") == value else ""
        chips.append(f'<a{on} href="{_e(href(day=value))}">{text}</a>')

    options = ['<option value="">Everyone</option>']
    for uid, _ in sorted(players.items(), key=lambda i: display_name(i[0], names).lower()):
        sel = " selected" if uid == player else ""
        options.append(f'<option value="{_e(uid)}"{sel}>{_e(display_name(uid, names))}</option>')

    # A specific date keeps the chips honest: none lights up, the picker does.
    # `iso` is the normalised form, resolved by the caller — parse_day accepts
    # `16/9`, which <input type="date"> silently drops, leaving the picker blank
    # on a view that is in fact filtered. Resolved there rather than here so this
    # module keeps depending on nothing but elo.
    picked = iso if day and day not in dict(DAY_CHIPS) else ""
    return (
        '<form id="filters" class="filters" method="get" action="">'
        f'<select name="player" aria-label="Player">{"".join(options)}</select>'
        f'<input type="date" name="day" aria-label="Day" value="{_e(picked)}">'
        '<span class="sep"></span>'
        + "".join(chips)
        + '<noscript><button type="submit">Go</button></noscript>'
        "</form>")


def _footer(placement_games, channel_hint, updated):
    where = f" in {_e(channel_hint)}" if channel_hint else " in Slack"
    return (
        "<footer>"
        f'<p>Log a session{where} with <code>/tt log</code>. Your opponent confirms '
        "it, then both ratings move.</p>"
        "<p>Every game is rated on its own, so a longer session counts for more, "
        "and beating someone above you is worth more than beating someone below.</p>"
        f'<p><span id="freshness">updated just now</span>'
        f'{" · " + _e(updated) if updated else ""}</p>'
        "</footer>")
