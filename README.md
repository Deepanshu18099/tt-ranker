# TT Ranker

A Slack bot that keeps an Elo ladder for office table tennis. Play a match, type
the scores, the other side presses **Confirm**, and everyone's rating moves.

Singles and doubles, one ladder, no spreadsheet.

```
you:       /tt log @bob 11-7 9-11 11-5

tt-ranker: 🏓 @you  2–1  @bob
           11-7   9-11   11-5
           Logged by @you · @bob — confirm to lock in the rating change.
           [ ✅ Confirm ]   [ ❌ That's wrong ]

…@bob presses Confirm

tt-ranker: 🏓 @you beat @bob — 2–1
           11-7   9-11   11-5

           @you  1000 → 1004  +4
           @bob  1000 →  996  -4
           Match #17 · confirmed by @bob
```

---

## Commands

Everything is one slash command, `/tt`.

| Command | What it does |
|---|---|
| `/tt log @bob 11-7 9-11 11-5` | Log a singles match — you against Bob |
| `/tt log @partner vs @dan @eve 11-7 11-9` | Doubles. `vs` splits the sides |
| `/tt log @ann @bob vs @cal @dee 11-7 11-9` | Record a match you weren't in |
| `/tt board` | The ladder |
| `/tt me` · `/tt me @bob` | One player's card — rating, record, streak, peak |
| `/tt history` · `/tt history @bob` | Recent results |
| `/tt pending` | Matches still waiting on confirmation |
| `/tt odds @bob` | Who's favoured, before you play |
| `/tt undo` | Roll back the last match *you* logged |
| `/tt register` | Join early (playing a match registers you anyway) |
| `/tt help` | All of the above, in Slack |

Scores are **the points in each game**, one per game: `11-7 9-11 11-5` is a
best-of-five won 2–1. Games to 21 work fine. `11 - 7`, `11:7` and `11–7` are all
read the same way. The word `log` is optional once you know the bot — `/tt @bob
11-7` works.

### Confirming

A logged match changes nothing until someone **on the other side** confirms it.
That's the whole integrity model: the only person who can wave a result through
is the person it costs.

- **Confirm** — rates the match and edits the message to show the new ratings.
- **That's wrong** — throws it out. Nothing is rated. Log it again properly.
- **Neither** — after 24 hours a daily sweep applies it anyway. Silence past the
  window counts as agreement; the losing side had a day and a button.

In doubles, either opponent can confirm. If a bystander logged the match, any of
the four players can.

---

## How your rating is calculated

Everyone starts at **1000**. After every match, each player's rating moves by:

```
change  =  K  ×  margin  ×  ( what you scored  −  what you were expected to score )
```

Four things go into that. Each one is boring on its own.

### 1. What you were expected to score

Standard Elo. The gap between the two ratings is the whole input:

| You're rated… | …your expected score |
|---|---|
| level | 50% |
| 50 above | 57% |
| 100 above | 64% |
| 200 above | 76% |
| 300 above | 85% |
| 400 above | 91% |

400 points is the classic 10-to-1 favourite. In doubles the pair's rating is the
**average** of the two partners, and that average is what goes into the table.

### 2. What you actually scored

The share of **games** you won.

| Result | Your score |
|---|---|
| 3–0 | 1.00 |
| 3–1 | 0.75 |
| 2–1 | 0.67 |
| 2–2 | 0.50 |
| 1–2 | 0.33 |
| 0–3 | 0.00 |

A 2–1 win is 0.67, not 1.00 — because winning two games out of three is genuinely
weak evidence that you're the better player. A coin does it 37% of the time.

### 3. How decisive it was — the margin multiplier

This is where the point scores earn their keep. Take the **whole match's** point
difference and divide by the number of games:

| Average margin | Multiplier |
|---|---|
| 1 point/game | ×0.60 |
| 2 points/game | ×0.68 |
| 3 points/game | ×0.86 |
| **4 points/game** | **×1.00** |
| 5 points/game | ×1.11 |
| 6 points/game | ×1.21 |
| 8 points/game | ×1.37 |
| 9+ points/game | ×1.40 (capped) |

So a 3–0 of `11-2 11-4 11-3` moves ratings about twice as hard as a 3–0 of
`12-10 11-9 13-11`, even though both are 3–0.

Two deliberate choices here:

- **It's measured on the match total, not game by game.** A `11-1 / 1-11 / 11-1`
  thriller averages out to a close match — which is what it was — instead of
  reading as three blowouts.
- **It's capped at ×0.6 and ×1.4.** Point margins are noisy. One 11-0 shouldn't
  be able to rewrite the ladder, and a single deuce shouldn't erase a win.

### 4. How much one match is allowed to move you — K

| Situation | K |
|---|---|
| Your first 20 matches (provisional) | 48 |
| After that | 32 |
| Doubles | ×0.75 of the above |

New players move fast so they reach roughly the right level in a few nights
rather than a season. Doubles counts for 75% because you only control half of a
doubles match.

### Putting it together — a full worked example

> **Alice (1000)** beats **Bob (1150)** 3–1: `11-8  9-11  11-6  11-7`.
> Both have played plenty of matches.

| Step | Working | Value |
|---|---|---|
| Games | Alice 3, Bob 1 | **S = 0.75** |
| Expected | Bob is 150 above, so Alice is expected to take ~30% | **E = 0.297** |
| Points | 42–32 over 4 games = 2.5 a game | **margin = ×0.778** |
| K | established, singles | **K = 32** |

```
change = 32 × 0.778 × (0.75 − 0.297) = +11.3  →  +11
```

**Alice 1000 → 1011. Bob 1150 → 1139.** Alice gains exactly what Bob loses.

### What that looks like in practice

Real numbers from the code, for two **equally rated** established players:

| Result | Change |
|---|---|
| 3–0 whitewash `11-2 11-4 11-3` | **+22** |
| 3–0 normal `11-7 11-9 11-8` | **+14** |
| 3–0 nail-biter `12-10 11-9 13-11` | **+11** |
| 2–1 win `11-7 9-11 11-5` | **+4** |
| 1–1 split | **0** |
| 0–2 loss `7-11 5-11` | **−18** |

And the same 3–0 `11-7 11-9 11-8`, against different opposition:

| Opponent | Change |
|---|---|
| 400 above you | **+25** |
| 200 above you | **+21** |
| level with you | **+14** |
| 200 below you | **+7** |
| 400 below you | **+3** |

Losing is the mirror image: losing to someone 400 above you costs **−3**; losing
to someone 400 below costs **−25**.

### Doubles

The pair is rated at the **average** of the two partners, both partners take the
**same** change, at 75% of the usual K.

> Alice (1200) and Ben (900) — a 1050 pair on paper.

| They beat | Each of them gets |
|---|---|
| two 1050s (par — exactly what's expected) | **+10** |
| two 1200s (an upset) | **+15** |

Carrying a weaker partner past a pair you should beat is worth little; doing it
against a pair you shouldn't is worth a lot. Neither partner is punished for who
they were drawn with.

### Questions people ask

**I won — why did I only get 3 points?**
You were expected to win. Beating someone 400 below you is what the ladder
already predicted, so it barely updates. The flip side is that losing that match
costs you 25.

**Can I farm a weak player to climb?**
No. Rated 1400 and beating a 1000 over and over gives +3, then +2, +2, +2, +2…
Each win narrows the gap you have left to prove, and it converges to nothing.
Meanwhile one loss to them costs you 25 — several nights' farming, gone.

**Does a best-of-five count for more than a best-of-three?**
No. Elo rates the *share* of games won, not how many you played. Playing more
games doesn't mean you've earned more rating. Winning them more convincingly
does — that's what the margin multiplier is for.

**Is the total rating in the system conserved?**
Between two established players, yes exactly — the winner gains precisely what
the loser drops, and a doubles result nets to zero across all four. The one
exception is deliberate: a provisional player carries a bigger K than their
established opponent, so a newcomer's early matches add a few points to the pool.
Converging newcomers quickly is worth more than a perfectly closed system.

**What stops someone logging a result that never happened?**
They can't confirm their own match — only the other side can, and either player
can throw it out with one button. Ratings only move on a result someone it
*costs* has signed off on.

**Someone confirmed a typo. Now what?**
Whoever logged it runs `/tt undo`. That restores a snapshot of every player taken
just before the match, so it's exact. It's refused once any player in that match
has played again — rewinding them would silently erase the later result too. At
that point, just play a correcting match.

**Can my rating go below zero?**
It floors at 100.

**Why don't I appear on the board?**
Five matches to qualify. Before that you're in the *Still placing* line — your
rating exists and moves, it just isn't ranked yet.

### Changing the numbers

Every constant above is a named value at the top of [elo.py](elo.py) —
`START_RATING`, `K_ESTABLISHED`, `K_PROVISIONAL`, `PROVISIONAL_MATCHES`,
`DOUBLES_K_FACTOR`, `MOV_BASELINE`, `MOV_MIN`/`MOV_MAX`, `RATING_FLOOR` — plus
`PLACEMENT_MATCHES` in [bot.py](bot.py). Change one, run `pytest`, redeploy.
Ratings already recorded are not recalculated.

---

## How it works

```
Slack ──▶ /slack/events ──▶ api/index.py (Flask on Vercel)
                                 │
                                 ├─▶ bot.py        /tt, the buttons, all the Slack text
                                 ├─▶ parsing.py    what someone typed → a match
                                 ├─▶ elo.py        the rating maths, pure functions
                                 ├─▶ store.py      players, pending queue, apply & undo
                                 ├─▶ kv.py         Upstash Redis REST — no SDK
                                 └─▶ standings.py  weekly post + the auto-confirm sweep
                                          ▲
                                   Vercel Cron ──┘
```

| File | Purpose |
|---|---|
| [elo.py](elo.py) | The rating maths. Pure functions, no I/O — everything above is here. |
| [parsing.py](parsing.py) | `/tt` grammar: mentions, the `vs` separator, scores, validation. |
| [store.py](store.py) | Persistence: players, the pending queue, applying a match, undo. |
| [bot.py](bot.py) | Slack handlers, message blocks, who is allowed to confirm. |
| [standings.py](standings.py) | Weekly standings post and the daily auto-confirm sweep. |
| [kv.py](kv.py) | Minimal Upstash Redis REST client, with pipelining. |
| [api/index.py](api/index.py) | Vercel entry point; also serves `/debug` and `/cron/*`. |
| [socket_mode.py](socket_mode.py) | Socket Mode entry point for local dev (no public URL). |
| [manifest.yaml](manifest.yaml) | Slack app manifest (scopes, command, interactivity). |

**Two rules the rest of the code depends on**

1. **A match is rated when it's confirmed, never when it's typed.** Pending
   records hold players and scores only. Two matches confirmed out of the order
   they were logged would otherwise apply stale ratings.
2. **Every applied match stores a full before-snapshot of each player.** Undo
   restores those records verbatim rather than running the Elo backwards, which
   isn't invertible once a floor clamp or a streak is involved.

**Storage**

| Key | Type | Holds |
|---|---|---|
| `tt:players` | set | every registered uid |
| `tt:player:<uid>` | hash | rating + the counters behind `/tt me` |
| `tt:seq` | string | `INCR` — match and pending ids |
| `tt:pending` | set | ids awaiting confirmation (and the atomic claim) |
| `tt:pending:<id>` | string | JSON of an unrated match, 7-day TTL |
| `tt:match:<id>` | string | JSON of a rated match, including the undo snapshot |
| `tt:history` | list | applied match ids, newest first |
| `tt:hist:<uid>` | list | applied match ids that player was in |
| `tt:wk:<YYYY-Www>:delta` / `:played` | hash | this week's movement, for the weekly post |
| `tt:standings:posted` | set | weeks already announced |

Races are handled with atomic claims rather than locks: `SADD` returning 1
registers a player exactly once, and `SREM` returning 1 means exactly one of two
people hitting **Confirm** at the same instant gets to rate the match.

---

## Setup

### 1. Slack app

1. <https://api.slack.com/apps> → **Create New App** → **From a manifest** → pick
   the workspace → paste [manifest.yaml](manifest.yaml).
   Leave the placeholder URLs for now; you'll come back once Vercel is live.
2. **Install to Workspace**, then copy:
   - **OAuth & Permissions** → *Bot User OAuth Token* → `SLACK_BOT_TOKEN` (`xoxb-…`)
   - **Basic Information** → *Signing Secret* → `SLACK_SIGNING_SECRET`
3. Get the channel id for the weekly post: open the channel in Slack → click its
   name → the id (`C…`) is at the bottom of the About tab. That's `TT_CHANNEL`.

### 2. Database

Vercel project → **Storage** → **Upstash for Redis** → Create. It sets
`KV_REST_API_URL` and `KV_REST_API_TOKEN` on the project for you. Using Upstash
directly instead, the `UPSTASH_REDIS_REST_URL` / `UPSTASH_REDIS_REST_TOKEN` pair
works too. The free tier is far more than an office ladder needs.

### 3. Vercel

Import the repo, then set under **Settings → Environment Variables**:

| Variable | Needed for |
|---|---|
| `SLACK_BOT_TOKEN` | always |
| `SLACK_SIGNING_SECRET` | always — verifies requests really came from Slack |
| `KV_REST_API_URL` / `KV_REST_API_TOKEN` | always — set by the Upstash integration |
| `TT_CHANNEL` | the weekly standings post |
| `CRON_SECRET` | authenticates `/cron/*`; Vercel sends it automatically once set |

Deploy. `vercel.json` rewrites every path to `api/index.py` and registers both
cron jobs. **Environment variable changes need a redeploy to take effect.**

### 4. Point Slack at it

Back in the Slack app, replace the three placeholder URLs with your deployment:

- **Slash Commands** → `/tt` → `https://<your-app>.vercel.app/slack/events`
- **Interactivity & Shortcuts** → on → same URL
  (this one is required — the Confirm buttons don't work without it)

Then invite the bot wherever people will log matches: `/invite @tt-ranker`. With
`chat:write.public` it can post in public channels uninvited, but inviting it is
tidier and it's required in private channels.

### 5. Check it

```
GET  https://<your-app>.vercel.app/               → "TT Ranker is running."
GET  https://<your-app>.vercel.app/debug          → what's configured, init status
GET  https://<your-app>.vercel.app/debug?ladder=1 → players, pending, cron history
```

Then in Slack: `/tt help`, `/tt register`, and log a match against a colleague.

---

## Running

**Vercel (production).** Push to the default branch. Two cron jobs are registered:

| Job | Schedule (UTC) | What |
|---|---|---|
| `/cron/sweep` | `30 3 * * *` daily | applies matches nobody confirmed in 24h |
| `/cron/standings` | `0 4 * * 1` Mondays | posts last week's ladder to `TT_CHANNEL` |

Both are safe to call by hand — the weekly post claims its week and the sweep
claims each match, so a retry can't double-post or double-rate. Add `?dry=1` to
either to see what it *would* do without doing it.

**Local (Socket Mode).** No public URL needed; enable Socket Mode on the app and
add an app-level token with `connections:write`.

```sh
python -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env     # fill it in
.venv/bin/python socket_mode.py
```

**Tests.** 150 of them, no network, no database.

```sh
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```

`tests/fake_kv.py` fakes only the HTTP transport, so every test exercises the
real command construction, the real hash unflattening and the real pipelining.

## Notes

- `socket_mode.py` must **not** be renamed to `app.py` / `main.py` / `index.py` /
  `server.py` — Vercel's zero-config Python detection would serve it instead of
  `api/index.py`.
- The corporate TLS proxy re-signs certificates without an Authority Key
  Identifier, which Python 3.13+ rejects; `bot.build_app()` keeps full
  verification but clears `VERIFY_X509_STRICT`.
- The match message is posted with `chat_postMessage`, not the slash command's
  response URL, because a confirmation can arrive hours later and a response URL
  expires after 30 minutes.
- The sweep's real wait is between 24 and 48 hours, since cron runs daily. The
  message promises "auto-confirms in 24h", which is the half that matters — it
  will never apply *sooner* than the window.
