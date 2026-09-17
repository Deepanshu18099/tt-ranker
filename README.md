# TT Ranker

A Slack bot that keeps an Elo ladder for office table tennis. Play as many games
as you have time for, type the scores, the other side presses **Confirm**, and
everyone's rating moves.

Singles and doubles, one ladder, no spreadsheet.

```
you:       /tt log @bob 11-7 9-11 11-5

in #table-tennis                    in @bob's DM ─────────────────┐
  🏓 @you  2–1  @bob                  🏓 @you  2–1  @bob          │
  11-7   9-11   11-5                  11-7   9-11   11-5          │
  Logged by @you · Sent to @bob       @you logged this. Is it     │
  to confirm.                         right? Nothing moves until  │
                                      you say so.                 │
  (no buttons — the channel           [ ✅ Confirm ] [ ❌ Wrong ]  │
   can read it, not rule on it)      ───────────────────────────── ┘

…@bob presses Confirm, and both messages become:

  🏓 @you beat @bob — 2–1
  11-7   9-11   11-5

  @you  1000 → 1010  +10
  @bob  1000 →  990  -10
  Match #17 · confirmed by @bob
```

Every game is rated on its own, so a ten-game session counts for more than a
three-game one, and margins are read relative to the game — 21-19 is a squeaker,
11-9 slightly less so. [How the rating works](#how-your-rating-is-calculated).

---

## Commands

Everything is one slash command, `/tt`.

| Command | What it does |
|---|---|
| **`/tt log`** · shortcuts menu → *Log a table tennis session* | **Opens a form — pick the players, type the scores** |
| `/tt log @bob 11-7 9-11 11-5` | Log singles — you against Bob, any number of games |
| `/tt log @partner vs @dan @eve 11-7 11-9` | Doubles. `vs` splits the sides |
| `/tt log @ann @bob vs @cal @dee 11-7 11-9` | Record a session you weren't in |
| `/tt board` · `/tt board singles` · `/tt board doubles` | The ladder · one format only |
| `/tt me` · `/tt me @bob` | One player's card — rating, record, streak, peak |
| `/tt history` · `/tt history @bob` | Recent results |
| `/tt pending` | Sessions still waiting on confirmation |
| `/tt odds @bob` | Who's favoured, before you play |
| `/tt undo` | Roll back the last session *you* logged |
| `/tt register` | Join early (playing registers you anyway) |
| `/tt sync` | Put everyone already in this channel on the ladder |
| `/tt name Your Name` | How you appear on the web ladder |
| `/tt name @bob Bob Smith` | Admins only — set it for someone else |
| `/tt who ChumChum` · `/tt who @bob` | Who is that? · what are they called? |
| `/tt intro` · `/tt intro clear` | Post the how-it-works message · take it down |
| **`/tt schedule`** · shortcuts menu → *Schedule a table tennis match* | **Opens a form — pick the players and a start time** |
| `/tt schedule @bob 6pm` | Or type it — `in 30m`, `6pm`, `6:30pm` and `18:30` all work |
| `/tt book` · `/tt book 6` | Open fixtures · one in full, with every stake |
| `/tt wallet` | Your spins and recent moves |
| `/tt transfer @bob 500` | Admins only — move spins between wallets |
| `/tt help` | All of the above, in Slack |

### The form

Two ways in, same form:

- **`/tt log`** on its own
- the **shortcuts menu** → *Log a table tennis session*. That's the `/` button at
  the right of the message toolbar, or just type `/` in the message box and
  search. (Not the `+` button — that one is files and workflows.)

A people picker for your side (you're pre-selected), one for your opponents, and
a box for the scores. Opened from the shortcuts menu it also asks which channel
to post the result in, since a global shortcut carries no channel context;
started from `/tt log` it already knows.

```
┌─ Log a session ───────────────────────────┐
│  Your side        [ @you            ▾ ]   │
│  Add a partner for doubles.               │
│                                           │
│  Opponents        [ @bob            ▾ ]   │
│                                           │
│  Game scores                              │
│  [ 11-7  9-11  11-5                   ]   │
│  The points in each game, your side       │
│  first. Log as many as you played.        │
│                                           │
│  Post the result in   [ #table-tennis ▾ ] │  ← shortcuts menu only
│                                           │
│                    [ Cancel ]  [ Log it ] │
└───────────────────────────────────────────┘
```

There's no singles/doubles switch — one name a side is singles, two is doubles,
and each goes to its own board as well as the overall one.
Mistakes come back attached to the field that's wrong, so a typo is one
correction rather than retyping the whole thing. Both routes run the same
validation and end at the same confirmation prompt.

Scores are **the points in each game**, one per game: `11-7 9-11 11-5` is three
games won 2–1. There's no fixed session length — log two games or twenty, up to
25. Games to 11, to 21 and first-to-7 all work, and you can mix them in one
session. `11 - 7`, `11:7` and `11–7` are all read the same way. The word `log`
is optional once you know the bot — `/tt @bob 11-7` works.

**Skunked?** The house rule ends a game at 11-0, so log it as `11-0`. It scores
as the most decisive result there is — a single skunk is worth about double a
normal win, because its winning score marks it as a *finished* game-to-11
whitewash rather than a half-played game to 21.

Log it as `21-0` — the number you play to rather than the number on the table
when it stopped — and it's **recorded as `11-0`**. The rating is identical
either way, because the margin is read relative to the game being played and
`21-0` and `11-0` both rescale to the same 11. What the fold-in protects is the
*record*: without it, a skunk would put ten points into your points total that
nobody ever played. Any `X-0` past 11 folds the same way; `21-1` doesn't — the
opponent scored, so the game ran its length.

### Confirming

A logged session changes nothing until someone **on the other side** confirms
it. That's the whole integrity model: the only person who can wave a result
through is the person it costs.

**The verdict goes out by DM, not to the channel.** The channel sees the claim
and who it's waiting on — read-only. The buttons go privately to the people
whose rating is at stake:

| Who | Gets | Can |
|---|---|---|
| each opponent | a DM | **✅ Confirm** · **❌ That's wrong** |
| whoever logged it | a DM | **🗑 Cancel this** — their mistake to take back, not their result to wave through |
| everyone else | the channel post | read it |

Buttons sitting in a channel invite everyone who can see them to press, and the
ones who shouldn't only find out after clicking. Keeping them in DMs means the
question reaches exactly the people entitled to answer it.

- **Confirm** — rates the session, and rewrites the channel post *and* every DM
  so no live button is left anywhere for something already decided.
- **That's wrong** — throws it out. Nothing is rated. Log it again properly.
- **Neither** — after 24 hours a daily sweep applies it anyway. Silence past the
  window counts as agreement; the losing side had a day and a button.

In doubles both opponents are asked and either can settle it. If a bystander
logged the session, all the players are asked. If nobody could be DM'd — app DMs
switched off — whoever logged it is told, and the sweep still applies it.

**Admins skip it.** Anyone listed in `TT_ADMINS` has their sessions rated the
moment they log them, and can confirm or throw out anybody else's pending
session — the only way to clear one whose players have gone quiet, short of
waiting for the daily sweep. The result still says *recorded by @them* 🛡, so
skipping the confirmation is visible to the channel rather than silent.

### Three ladders

| Board | Slack | Web |
|---|---|---|
| Singles | `/tt board singles` | the tab it opens on |
| Doubles | `/tt board doubles` | `?view=doubles` |
| Overall | `/tt board` | `?view=overall` |

**Singles is the one it opens on.** (Links pasted before that flip,
`?view=singles`, still work.)

Each board has its **own Elo**, not the overall rating with the other format
filtered out — the history that produced the overall number still has the other
format in it. They are updated side by side: every result moves the overall
rating and exactly one of the two format ratings, and each is rated off its own
ratings, so a singles result is judged against your singles standing and a
doubles result against your doubles one.

**Doubles is a narrower claim than singles, and the tab says so.** A doubles
result is **one number split between two people**. Both partners move by the
same amount, so what the maths actually pins down is the *pair's* combined
rating; the split between the two is never separately measured. Simulated
against the real `elo.py`, a true-700 player who always partners a 1300 settles
around **910**, while their partner is dragged down to **1210** — not points
from nowhere, a transfer from the stronger player. Play with varied partners and
it settles close to the truth; always partner the same person and the two of you
drift together, high or low, with nothing able to separate you.

So read the doubles board as *how the teams you play on do*. Singles is the
board that can tell two people apart, which is why it's the one that opens.

Both format boards qualify at **4 games** rather than 6. Each format's games are
a subset of all games, so the same bar would leave them empty while the overall
one is full — `SINGLES_PLACEMENT_GAMES` and `DOUBLES_PLACEMENT_GAMES` in
[bot.py](bot.py), to raise once volume catches up.

### Joining

**Anyone who joins `TT_CHANNEL` is put on the ladder automatically** and gets a
DM explaining how to log a match. Nobody has to know the bot exists to end up on
it.

Deliberately scoped to that one channel rather than every channel the bot sits
in — being invited somewhere busy for a single match shouldn't enrol that
channel's entire membership.

Two things it doesn't cover, both handled by **`/tt sync`**:

- people who were already in the channel before the bot arrived
- any *other* channel where matches get played

`/tt sync` acts on the channel you run it in, which is why the one command that
enrols people in bulk always names its target explicitly. It's idempotent and
doesn't DM anyone — run it as often as you like.

You can still `/tt register` yourself, and simply playing a match registers
everyone in it.

---

## How your rating is calculated

Everyone starts at **1000**.

**Every game is rated on its own, and they add up.** A session runs as long as
you have time for — two games at lunch, fifteen on a Friday. That length is
information, not noise: winning 8 of 10 is a far stronger claim than winning 2
of 3, so the longer session moves ratings further.

Each game contributes:

```
K  ×  margin  ×  upset  ×  ( did you win it?  −  what you were expected to score )
```

Four inputs. Each one is boring on its own.

### 1 · What you were expected to score

Standard Elo. The gap between the two ratings is the whole input:

| You're rated… | …your expected score per game |
|---|---|
| level | 50% |
| 50 above | 57% |
| 100 above | 64% |
| 200 above | 76% |
| 300 above | 85% |
| 400 above | 91% |
| 600 above | 97% |

400 points is the classic 10-to-1 favourite. In doubles the pair's rating is the
**average** of the two partners, and that average goes into the table.

This expectation is worked out once from the ratings you both walked in with,
and held for the whole session — so the result can't depend on the order the
games happened to be typed in.

### 2 · Did you win the game

1 or 0. That's it. No fractions, because each game is rated separately rather
than the session being averaged into a single result.

Losses inside a session cancel wins, so the whole thing collapses to *how much
better did you do than expected*.

### 3 · How decisively you won it — the margin

This is where the point scores earn their keep. The margin is read **relative to
the game being played**, so the same curve serves games to 11, games to 21 and
first-to-7 without three sets of numbers:

| Won by | in a game to 11 | in a game to 21 |
|---|---|---|
| the minimum 2 | ×0.56 | ×0.45 (floor) |
| a close win | `11-8` ×0.80 | `21-16` ×0.71 |
| **a par win** | `11-7` **×1.00** | `21-13` **×1.04** |
| comfortable | `11-5` ×1.33 | `21-10` ×1.32 |
| a whitewash | `11-2` ×1.71 | `21-4` ×1.70 |

Two points is 18% of a game to 11 but under 10% of a game to 21, so `21-19` is
the tighter result and counts as one. Read raw, every margin in a 21-point game
would come out about twice as decisive as it really was.

An 11-2 is worth roughly **three times** an 11-9. The curve is log-damped and
clamped at both ends, because point margins are noisy — one 11-0 shouldn't
rewrite the ladder, and a single deuce shouldn't erase a win.

### 4 · How much one game may move you — K

| Situation | K |
|---|---|
| Your first 50 **games** (provisional) | 16 |
| After that | 11 |
| Doubles | ×0.5 of the above |

Counted in games rather than sessions, because a session can be any length. New
players move fast so they reach roughly the right level in a few sessions rather
than a season. Doubles counts half, because half of every doubles result is your
partner's play and none of it is yours.

### Plus one correction: the favourite's blowout counts for less

A strong player is *expected* to win by a lot, so their 11-2 says less about
them than the same 11-2 would say about an underdog. Without correcting for
this, margin-of-victory quietly inflates the already-strong — a well-known flaw
in naive MOV systems.

So the margin multiplier is scaled by the rating gap **of that game's winner over
its loser**: a 400-point favourite winning gets ×0.85, a 400-point underdog
winning gets ×1.22. It applies identically to both sides, so the books still
balance.

---

### What this looks like in practice

**Three games against an equal player:**

| Result | Change |
|---|---|
| 3–0 whitewash `11-2 11-4 11-3` | **+26** |
| 3–0 normal `11-7 11-9 11-8` | **+13** |
| 3–0 every game a deuce `12-10 11-9 13-11` | **+9** |
| 2–1 `11-7 9-11 11-5` | **+10** |

Yes — a 2–1 of comfortable wins (+10) edges out a 3–0 of three deuces (+9). A
3–0 where every game went to deuce genuinely *is* a closer session than winning
two games easily and dropping one, and the model is allowed to say so.

**Session length matters** (winning every game 11-7, against an equal):

| Games | Change |
|---|---|
| 1 | +6 |
| 3 | +17 |
| 5 | +28 |
| 10 | +55 |
| 20 | +110 |

**A 10-game session against an equal:**

| You won | Change |
|---|---|
| 10 of 10 | +55 |
| 8 of 10 | +33 |
| 7 of 10 | +22 |
| **5 of 10** | **0** |
| 3 of 10 | −22 |
| 0 of 10 | −55 |

**The same 3–0 `11-7 11-9 11-8`, against different opposition:**

| Opponent | You win | You lose 0–3 |
|---|---|---|
| 400 above you | **+29** | −2 |
| 200 above you | **+22** | −6 |
| level | **+13** | −13 |
| 200 below you | **+6** | −22 |
| 400 below you | **+2** | **−29** |

**The big upset** — a 1000 beating a 1400:

| | |
|---|---|
| 3–0 whitewash | **+58** |
| 3–0 normal | **+29** |
| 2–1 | **+28** |
| 7 of 10 games | **+83** |

### Doubles

The pair is rated at the **average** of the two partners, both partners take the
**same** change, at **half** the usual K — half of any doubles result is your
partner's doing, so it says half as much about you.

> Alice (1200) and Ben (900) — a 1050 pair on paper.

| They beat | Each of them gets |
|---|---|
| two 1050s (par — exactly what's expected) | a little |
| two 1200s (an upset) | a lot |

Carrying a weaker partner past a pair you should beat is worth little; doing it
against a pair you shouldn't is worth plenty. Neither partner is punished for
who they were drawn with.

---

### Questions people ask

**I won and my rating went DOWN. Is that broken?**
No, and this is the one that surprises people. If you're rated 1400 and beat a
1000 by 2–1, you lose **5 points** — you were expected to take about 9 games in
10, and 2–1 is well short of that. Beating them 3–0 normally gains +2. Against
someone far below you, only a convincing win is worth anything, and a scrappy
one is evidence the gap isn't as wide as your rating claims.

**Can I farm a weak player to climb?**
Not really. Rated 1400 beating a 1000 3–0 gains **+2**. Then less. Then less
again — each win narrows the gap you have left to prove, and once you're ~750
ahead a win gains literally nothing. Grinding the ceiling out takes over a
thousand games, and every one of them drags your victim's rating down toward
you, closing the gap from the other side too. Meanwhile a single loss to them
costs you −29. And `/tt history` shows everyone the same two names over and over.

**Does playing more games get me more rating?**
Only if you keep winning them. More games means more movement in *whichever*
direction you earned — a 20-game session you lose 6–14 costs far more than a
3-game one. It cuts exactly as hard both ways.

**Is the total rating in the system conserved?**
Between two established players, exactly — the winner gains precisely what the
loser drops, at any session length, and a doubles result nets to zero across all
four. The one exception is deliberate: a provisional player carries a bigger K
than their established opponent, so a newcomer's early games add a few points to
the pool. Converging newcomers quickly is worth more than a perfectly closed
system.

**Why is a nail-biting 3–0 worth less than a comfortable 2–1?**
Because the points say the first session was closer. See the table above.

**What stops someone logging a result that never happened?**
They can't confirm their own session — only the other side can, and either
player can throw it out with one button. Ratings only move on a result someone
it *costs* has signed off on.

**Someone confirmed a typo. Now what?**
Whoever logged it runs `/tt undo`. That restores a snapshot of every player
taken just before the session, so it's exact. It's refused once any player in it
has played again — rewinding them would silently erase the later result too. At
that point, just play a correcting session.

**Can my rating go below zero?**
It floors at 100.

**Why don't I appear on the board?**
Six games to qualify. Before that you're in the *Still placing* line — your
rating exists and moves, it just isn't ranked yet.

### Changing the numbers

Every constant above is a named value at the top of [elo.py](elo.py) —
`START_RATING`, `K_ESTABLISHED`, `K_PROVISIONAL`, `PROVISIONAL_GAMES`,
`DOUBLES_K_FACTOR`, `MOV_BASELINE`, `MOV_GAIN`, `MOV_MIN`/`MOV_MAX`,
`UPSET_SCALE`, `RATING_FLOOR` — plus `PLACEMENT_GAMES` in [bot.py](bot.py).
Change one, run `pytest`, redeploy.

To apply a change to **matches already played**, run
`python scripts/recompute.py` — it replays every stored match in the order they
were applied and rewrites ratings, counters, undo snapshots and the weekly
figures as if the new numbers had always been in force. Dry run by default, and
it refuses outright if any match has aged out of history, since a replay on
partial history would be wrong rather than merely incomplete. It never touches
spins or settled bets.

Two knobs do most of the tuning:

- **`MOV_GAIN`** — how much the scoreline matters. At 1.0 a whitewash is worth
  2× a deuce-fest; at the current 1.5 it's ~2.9×; at 2.0, ~4.3×.
- **`K_ESTABLISHED`** — overall volatility. Everything scales with it.

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
| [bot.py](bot.py) | Slack handlers, the log form, message blocks, who may confirm. |
| [betting.py](betting.py) | Spins, fixtures, pools and settlement. No I/O beyond the store. |
| [page.py](page.py) | The public ladder page — pure rendering, no database. |
| [standings.py](standings.py) | Weekly standings post, payday, and the daily sweeps. |
| [kv.py](kv.py) | Minimal Upstash Redis REST client, with pipelining. |
| [api/index.py](api/index.py) | Vercel entry point; also serves `/debug` and `/cron/*`. |
| [socket_mode.py](socket_mode.py) | Socket Mode entry point for local dev (no public URL). |
| [manifest.yaml](manifest.yaml) | Slack app manifest (scopes, command, events, interactivity). |

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
| `tt:wallet` | hash | uid → spins |
| `tt:sched:<id>` | string | JSON of a fixture |
| `tt:sched:live` | set | fixtures not yet settled (and the settlement claim) |
| `tt:bets:<id>` | hash | uid → `side:amount` |
| `tt:ledger:<uid>` | list | recent wallet movements, for `/tt wallet` |
| `tt:stipend:paid` | set | weeks payday has run |

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
| `TT_CHANNEL` | the ladder's home channel — weekly standings land here, and joining it registers you |
| `CRON_SECRET` | authenticates `/cron/*`; Vercel sends it automatically once set |
| `TT_ADMINS` | optional — ids who can record a result without confirmation |
| `TT_PUBLIC_URL` | optional — your deployment URL, so the bot can link the ladder page |
| `TT_CHANNEL_NAME` | optional — e.g. `#table-tennis`, shown on the ladder page |

Deploy. `vercel.json` rewrites every path to `api/index.py` and registers both
cron jobs. **Environment variable changes need a redeploy to take effect.**

### 4. Point Slack at it

Back in the Slack app, replace the three placeholder URLs with your deployment:

- **Slash Commands** → `/tt` → `https://<your-app>.vercel.app/slack/events`
- **Interactivity & Shortcuts** → on → same URL
  (required — the Confirm buttons and the log form don't work without it)
- **Event Subscriptions** → on → same URL, and subscribe the bot to
  **`member_joined_channel`**
  (required for auto-registration; Slack verifies the URL when you save)

Then invite the bot wherever people will log matches: `/invite @tt-ranker`. With
`chat:write.public` it can post in public channels uninvited, but inviting it is
tidier and it's required in private channels.

Finally, run **`/tt sync`** in the channel to put everyone already there on the
ladder — auto-registration only catches people who join from now on.

> **Upgrading an existing install?** `channels:read`, `groups:read` and the
> `member_joined_channel` subscription were added after the first release.
> Slack does not grant new scopes to an app that's already installed — go to
> **OAuth & Permissions → Reinstall to Workspace**. Until you do, `/tt sync`
> reports a missing scope and nobody is auto-registered; everything else keeps
> working.

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

Behind a TLS-intercepting corporate proxy, local runs also need
`REQUESTS_CA_BUNDLE=vmock-ca.crt` — the proxy's CA is committed here for that.
(Vercel isn't behind it, so production needs nothing.)

**Tests.** 259 of them, no network, no database.

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

---

## The ladder page

`https://<your-app>.vercel.app/ladder` — a live, public, read-only page. Put it in
the channel topic so people can check where they stand without running a command.

It answers one question, in this order: **did I move?** The rating is the loudest
thing on the page, this week's change sits beside it, and your row is reachable
without scrolling past a hero. Before anyone has qualified it counts down to the
first ranked player instead of showing an empty table.

No login and no secrets — it shows names and ratings, which everyone in the
channel can already see. It refreshes itself every minute, but only while the tab
is actually being looked at.

**Sessions.** Under the ladder, the recent results — and a filter bar to answer
"what did Bob play today?" Pick a player, tap *Today*, *Yesterday* or *This
week*, or choose a date; the two combine. The filters live in the address bar
(`/ladder?player=<uid>&day=today`), so a view can be pasted into the channel,
and they are plain links and a form — no script needed for them to work. The
same filters are in Slack: `/tt history @bob today`, `/tt history week`,
`/tt history 2026-09-16`. Days are read in IST, like everything else here.

**Names.** The page can't render a Slack mention, so it needs something to call
people. Three tiers, best first:

1. what they set with `/tt name Sagnik`
2. the Slack handle their slash commands revealed
3. the tail of their user id — a stub, and a visible prompt to set one

`/tt nudge` (admins only) DMs everyone still on tier 2 or 3. New players are
asked when they join.

Most people never get round to setting their own, so an admin can do it for
them: `/tt name @bob Bob Smith`. The player is DM'd that it happened and how to
change it — a name is how you're shown to the whole office, and a leaderboard is
no way to find out it changed.

**`/tt who`** goes the other way. The page can't render a Slack mention, so it
shows chosen names and a reader has no way back from *ChumChum* to a person:

```
/tt who ChumChum   →  ChumChum is @bob
/tt who chum       →  same — case-insensitive, partial matches count
/tt who @bob       →  @bob is ChumChum on the ladder
/tt who            →  everyone, names first
```

Matching is tiered — exact, then prefix, then substring — so *Ram* doesn't lose
to *Ramesh*, which is precisely when you need the lookup.


---

## Betting

Fixtures can be scheduled, and the channel bets on them in **spins** — play
money, no real stakes.

```
/tt schedule                   →  a form: players, and a start time
/tt schedule @bob 6pm          →  or type it
/tt book                       →  what's open
/tt wallet                     →  your balance and recent moves
/tt bet 12 a 50                →  the typed route; the buttons are the usual one
```

The form uses a native **date-and-time picker** rather than a text box. `6pm` has
to be parsed, guessed at across midnight and echoed back to be checked; a picker
is unambiguous the moment it's set. It defaults to an hour out, rounded up to
the next quarter.

```
┌─ Schedule a match ────────────────────────┐
│  Your side        [ @you            ▾ ]   │
│  Add a partner for doubles.               │
│                                           │
│  Opponents        [ @bob            ▾ ]   │
│                                           │
│  First serve      [ 17 Sep  18:00     ]   │
│  Betting shuts at this moment — until     │
│  then anyone in the channel can back      │
│  either side.                             │
│                                           │
│  Put the fixture in   [ #table-tennis ▾ ] │  ← shortcuts menu only
│                                           │
│                   [ Cancel ]  [ Put it up]│
└───────────────────────────────────────────┘
```

The fixture message carries a **Back _____** button for each side. Unlike a
match verdict, those buttons belong in the channel: anyone may bet, and only the
players may rule on a result.

### How a pot pays

**Pari-mutuel** — every stake goes into one pot, and whoever backed the winner
splits it in proportion to what they staked.

```
💰 11,120 spins in the pot
danger — 1,120 spins · pays 9.93×
   Deepanshu 1,020 · Praneat 50 · danger 50
ChumChum — 10,000 spins · pays 1.11×
   KK 5,000 · Akchansh 4,000 · Shashank 900 · ChumChum 100
```

Backers are **named, not counted**. On a ladder this size who backed you is most
of the point, and it's also what turns an odd-looking stake into something the
room notices rather than something only the database knows.

`/tt book 6` gives one fixture in full — every stake and what it would return —
for once the message has scrolled away.

Nobody is the bookmaker, so **no spin is ever created or destroyed by betting**.
Everything paid out came from someone else's stake. That's asserted directly:
the test suite runs whole fixtures across every split, winner and rounding case
and checks the total supply is unchanged to the last spin. Floored shares would
quietly burn a few, so the rounding remainder goes to the largest winning stake.

The consequence worth knowing: backing the obvious favourite pays least,
because everyone else did too.

| Situation | What happens |
|---|---|
| Draw | Every stake refunded |
| Nobody backed the winner | Every stake refunded |
| Everyone backed the winner | Everyone gets their own stake back |
| Nobody logs the result within 48h | Fixture voided, every stake refunded |
| Called off (players, organiser or an admin) | Every stake refunded |

### The window

It shuts the moment the match is due to start. That's enforced when a bet is
placed, not by the cron — crons run daily, so a window left open because nothing
had swept yet would let people bet on a match already under way. The daily sweep
only tidies the message afterwards.

The resolved start time is always echoed back (`today 18:00`, `tomorrow 09:00`),
so `/tt schedule @bob 9am` typed in the evening visibly means tomorrow morning
rather than silently meaning it.

### Spins

| | |
|---|---|
| Everyone starts with | **5,000** |
| Top-ups | **none** — `WEEKLY_STIPEND = 0` |
| Smallest stake | **5** |

A wallet can never go negative — stakes leave when the bet is placed and
settlement only ever credits.

**Nothing mints spins.** The supply is fixed at what everyone opened with, so a
spin won is a spin somebody else lost and the currency is worth something.
Betting and transfers are both zero-sum, and there's a test that says so.

Which also makes a wallet balance a real standing. **`/tt rich`** ranks every
wallet, richest first, with how far each has moved from the 5,000 it opened
with, and the same table sits on the ladder page under *Spins* once anyone has
moved. Players who never placed a bet are ranked at 5,000 rather than left off
— that is what their wallet would hold the moment it opened.

The trade is that busting out is permanent until an admin moves some across with
`/tt transfer`. A weekly stipend is one constant away if that turns out to be
too harsh — set `WEEKLY_STIPEND` above zero in [betting.py](betting.py) and both
cron jobs start paying it, claimed once a week so it can't be paid twice.

### Moving spins

`/tt transfer @bob 500` moves spins out of your own wallet;
`/tt transfer @alice @bob 500` moves them between two other people. **Admins
only** — a wallet you didn't agree to empty isn't something any player should be
able to reach.

Both forms are **zero-sum**: a debit and a credit of the same size, so the
Monday stipend is still the only thing in the system that mints. An admin
handing out a prize is giving away their own spins, not printing new ones.

Everyone whose balance moved is DM'd, and a move made by a third party says so
in both ledgers — `/tt wallet` can always answer *where did that come from*.

### Betting on your own match

Allowed, including against yourself. That's a deliberate house rule, so the only
guard is daylight: if a player backs the side they aren't playing for, the
fixture message names them and the amount.

Worth being aware of what that permits — the result is self-reported, so
someone can profit from a game whose score they also type in. The office is
expected to police that, which is exactly what the visibility is for.

