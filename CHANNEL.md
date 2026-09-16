# Setting up the channel

Copy-paste for the Slack channel that hosts the ladder. Whatever channel id you
put in `TT_CHANNEL` is the one people get auto-registered by joining.

## Name

`#table-tennis` — or `#ping-pong`, `#tt-ladder`. Short and obvious; people have
to find it to join it.

## Topic

Shows in the channel header. Keep it to one line.

```
🏓 Office table tennis ladder — `/tt log @opponent 11-7 9-11 11-5` · `/tt board` for standings
```

## Description

Shows in the channel browser, which is where people decide whether to join.

```
Where the office table tennis ladder lives. Play however many games you have time for, log them with /tt log, your opponent confirms, ratings move. Everyone who joins is added automatically. /tt help to get started.
```

Both strings live in [bot.py](bot.py) as `CHANNEL_TOPIC` and
`CHANNEL_DESCRIPTION` so they stay next to the behaviour they describe.

## The pinned message

Don't paste this one — run it, so the thresholds in it are always the constants
the bot is actually running on:

```
/tt intro
```

Then hover the message it posts → **⋯** → **Pin to channel**. New joiners get
the same information as a DM automatically, but a pin is what people scroll back
to when they forget the syntax.

Re-run `/tt intro` and re-pin after any scoring change — the message is
generated from the live constants, so it updates itself.

## Order of operations

1. Create the channel, set the topic and description
2. `/invite @tt-ranker`
3. Put the channel id in `TT_CHANNEL` on Vercel, redeploy
4. `/tt sync` — puts everyone already in the channel on the ladder
5. `/tt intro` → pin it
6. Play something and `/tt log` it, so the first thing people see is a real result

Steps 3 and 4 are the ones that are easy to forget. Without `TT_CHANNEL` set,
joining the channel registers nobody and the weekly standings post has nowhere
to go — `GET /debug` will show `TT_CHANNEL: false`.
