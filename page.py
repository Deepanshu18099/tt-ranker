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


VIEWS = (("", "Overall"), ("singles", "Singles"))


def _tabs(view):
    """One URL per view, so a tab can be pasted into the channel."""
    links = []
    for value, label in VIEWS:
        on = ' class="on"' if (view or "") == value else ""
        href = f"?view={value}" if value else "?"
        links.append(f'<a{on} href="{_e(href)}">{label}</a>')
    return f'<nav class="tabs">{"".join(links)}</nav>'


def render(players, names, recent, week_delta, week_played, placement_games,
           channel_hint="", updated="", view=""):
    """The whole page. Pure — every input is passed in, so it renders in a test
    without a database or a Slack client.

    `players` is whichever record set the view wants: pass singles views in for
    the singles tab. The ranking and rendering below don't know the difference,
    which is the point of shaping a singles record like an ordinary one.
    """
    singles = view == "singles"
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
    parts.append(_recent(recent, names))
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


def _recent(recent, names):
    if not recent:
        return ""
    rows = []
    for blob in recent[:8]:
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
        games = "".join(f"<span class='num'>{g[0]}&#8211;{g[1]}</span>"
                        for g in blob["games"])
        deltas = " · ".join(
            f"{_e(display_name(u, names))} "
            f"<span class='num'>{blob['deltas'][u]:+d}</span>"
            for u in blob["side_a"] + blob["side_b"])
        rows.append(f'<div class="session"><div class="sides">{head}{score}</div>'
                    f'<div class="games">{games}</div>'
                    f'<p class="deltas">{deltas}</p></div>')
    return "<h2>Recent sessions</h2>" + "".join(rows)


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
