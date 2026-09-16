"""
Everything that outlives a request: players, matches, and the pending queue.

Shape of the data
-----------------
  tt:players            set    every registered uid
  tt:player:<uid>       hash   rating + the counters behind /tt me
  tt:seq                str    INCR — match and pending ids come from here
  tt:pending            set    ids awaiting confirmation (also the atomic claim)
  tt:pending:<id>       str    JSON of an unrated match, TTL'd
  tt:match:<id>         str    JSON of a rated match, including an undo snapshot
  tt:history            list   applied match ids, newest first
  tt:hist:<uid>         list   applied match ids that player was in
  tt:wk:<YYYY-Www>:*    hash   this week's rating movement, for the weekly post

Two rules the rest of the bot depends on:

1. **A match is rated when it is confirmed, never when it is typed.** Pending
   records hold players and scores only — no ratings. Two matches confirmed out
   of the order they were logged would otherwise apply stale numbers.

2. **Every applied match carries a full before-snapshot of each player.** Undo
   restores those records verbatim rather than trying to run the Elo backwards,
   which is not invertible once a floor clamp or a streak is involved.
"""
import json
from datetime import datetime, timedelta, timezone

import elo
import kv

IST = timezone(timedelta(hours=5, minutes=30))

PLAYERS_KEY = "tt:players"
SEQ_KEY = "tt:seq"
PENDING_KEY = "tt:pending"
HISTORY_KEY = "tt:history"

HISTORY_LIMIT = 500       # what /tt history and the weekly post ever look at
PLAYER_HISTORY_LIMIT = 50
# Comfortably longer than AUTO_CONFIRM_HOURS, so the sweep always finds a
# pending match before Redis expires it out from under us.
PENDING_TTL_SECONDS = 7 * 24 * 3600
AUTO_CONFIRM_HOURS = 24

INT_FIELDS = ("rating", "matches", "wins", "losses", "draws", "games_won",
              "games_lost", "points_won", "points_lost", "peak", "streak",
              "best_streak")


def player_key(uid):
    return f"tt:player:{uid}"


def pending_key(mid):
    return f"tt:pending:{mid}"


def match_key(mid):
    return f"tt:match:{mid}"


def player_history_key(uid):
    return f"tt:hist:{uid}"


def week_key(when=None):
    """ISO week in IST — the bucket the weekly standings post reports on."""
    when = (when or now_ist()).astimezone(IST)
    year, week, _ = when.isocalendar()
    return f"tt:wk:{year}-W{week:02d}"


def now_ist():
    return datetime.now(IST)


def stamp(when=None):
    return (when or now_ist()).astimezone(IST).isoformat(timespec="seconds")


# --- players ---------------------------------------------------------------

def new_player(now=None):
    """A player's opening record. Every field is present from the start so an
    undo snapshot can always be restored with a plain HSET."""
    return {"rating": elo.START_RATING, "matches": 0, "wins": 0, "losses": 0,
            "draws": 0, "games_won": 0, "games_lost": 0, "points_won": 0,
            "points_lost": 0, "peak": elo.START_RATING, "streak": 0,
            "best_streak": 0, "joined": stamp(now), "last_played": "",
            "last_match": ""}


def _coerce(raw):
    """Redis hands everything back as a string; put the numbers back."""
    out = dict(raw)
    for field in INT_FIELDS:
        try:
            out[field] = int(out.get(field, 0))
        except (TypeError, ValueError):
            out[field] = 0
    return out


def get_players(uids):
    """{uid: record} for those already registered — one round trip, missing
    players simply absent."""
    uids = list(dict.fromkeys(u for u in uids if u))
    if not uids:
        return {}
    results = kv.pipeline([["HGETALL", player_key(u)] for u in uids])
    out = {}
    for uid, res in zip(uids, results):
        raw = kv.unflatten(res)
        if raw:
            out[uid] = _coerce(raw)
    return out


def load_for_match(uids, now=None):
    """Like get_players, but a missing record reads as a fresh one.

    Self-healing: if a crash ever left a uid in tt:players with no hash behind
    it, that player rates as a newcomer instead of blowing up a confirmation.
    """
    found = get_players(uids)
    return {uid: found.get(uid) or new_player(now) for uid in dict.fromkeys(uids)}


def get_player(uid):
    return get_players([uid]).get(uid)


def all_players():
    """{uid: record} for the whole ladder — what the leaderboard ranks."""
    uids = kv.smembers(PLAYERS_KEY)
    return get_players(uids)


def ensure_players(uids, now=None):
    """Register anyone new; returns the uids that were actually added.

    SADD's per-member return is the claim — exactly one caller sees 1 for a
    given uid, so two people logging a newcomer's first match at the same moment
    cannot both create them.
    """
    uids = list(dict.fromkeys(u for u in uids if u))
    if not uids:
        return []
    claimed = kv.pipeline([["SADD", PLAYERS_KEY, u] for u in uids])
    fresh = [u for u, added in zip(uids, claimed) if added == 1]
    if fresh:
        record = new_player(now)
        kv.pipeline([["HSET", player_key(u)] + _flatten(record) for u in fresh])
    return fresh


def _flatten(mapping):
    args = []
    for k, v in mapping.items():
        args += [k, v]
    return args


# --- pending matches -------------------------------------------------------

def next_id():
    return str(kv.incr(SEQ_KEY))


def create_pending(side_a, side_b, games, logged_by, channel=None, now=None):
    """Park an unrated match and return its record. No ratings are read here —
    see the module docstring."""
    record = {
        "id": next_id(),
        "side_a": list(side_a), "side_b": list(side_b),
        "games": [[int(a), int(b)] for a, b in games],
        "logged_by": logged_by,
        "logged_at": stamp(now),
        "channel": channel or "",
        "ts": "",
        "dms": {},   # uid -> [channel, ts] of that person's verdict prompt
    }
    kv.set_(pending_key(record["id"]), json.dumps(record), ex=PENDING_TTL_SECONDS)
    kv.sadd(PENDING_KEY, record["id"])
    return record


def get_pending(mid):
    raw = kv.get(pending_key(mid))
    return json.loads(raw) if raw else None


def attach_messages(mid, channel, ts, dms=None):
    """Remember every place this session was announced — the channel post and
    each verdict DM — so settling it can update all of them.

    Without the DM locations, confirming would leave live buttons sitting in
    other people's DMs for a session that is already decided.
    """
    record = get_pending(mid)
    if not record:
        return None
    record["channel"], record["ts"] = channel or "", ts or ""
    record["dms"] = dms or {}
    kv.set_(pending_key(mid), json.dumps(record), ex=PENDING_TTL_SECONDS)
    return record


def claim_pending(mid):
    """Take exclusive ownership of a pending match. True for exactly one caller —
    SREM reports what it actually removed — so two people hitting Confirm at the
    same instant can't rate the match twice."""
    return kv.srem(PENDING_KEY, mid) == 1


def release_pending(mid):
    """Put a claimed match back, for when applying it failed part-way."""
    return kv.sadd(PENDING_KEY, mid)


def drop_pending(mid):
    kv.srem(PENDING_KEY, mid)
    kv.delete(pending_key(mid))


def list_pending():
    """Every outstanding match, newest last. Ids whose JSON has expired are
    swept out of the index on the way past."""
    ids = sorted(kv.smembers(PENDING_KEY), key=_as_int)
    if not ids:
        return []
    raws = kv.pipeline([["GET", pending_key(i)] for i in ids])
    records, stale = [], []
    for mid, raw in zip(ids, raws):
        if raw:
            records.append(json.loads(raw))
        else:
            stale.append(mid)
    if stale:
        kv.srem(PENDING_KEY, *stale)
    return records


def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def is_expired(record, now=None, hours=AUTO_CONFIRM_HOURS):
    """Has this sat unconfirmed long enough to apply on its own?"""
    try:
        logged = datetime.fromisoformat(record.get("logged_at", ""))
    except ValueError:
        return False
    return (now or now_ist()) - logged >= timedelta(hours=hours)


# --- applying a match ------------------------------------------------------

def apply_match(record, confirmed_by=None, auto=False, admin=False, now=None):
    """Rate a pending match against *current* ratings and write everything down.

    Returns the stored match blob. The caller must have won claim_pending()
    first; this does not claim on its own, because the claim has to happen
    before any of the slow work.
    """
    now = now or now_ist()
    side_a, side_b = record["side_a"], record["side_b"]
    uids = side_a + side_b
    ensure_players(uids, now)
    players = load_for_match(uids, now)

    def entries(side):
        # K is measured in games played, not sessions — a session is any length.
        return [{"uid": u, "rating": players[u]["rating"],
                 "games": elo.games_played(players[u])} for u in side]

    rated = elo.rate_match(entries(side_a), entries(side_b), record["games"])
    mid = record["id"]
    wk = week_key(now)

    writes = []
    for side, mine, theirs in ((side_a, "a", "b"), (side_b, "b", "a")):
        for uid in side:
            updated = _advance(players[uid], rated, mine, theirs, uid, mid, now)
            writes.append(["HSET", player_key(uid)] + _flatten(updated))
            writes.append(["LPUSH", player_history_key(uid), mid])
            writes.append(["LTRIM", player_history_key(uid), 0, PLAYER_HISTORY_LIMIT - 1])
            writes.append(["HINCRBY", f"{wk}:delta", uid, rated["deltas"][uid]])
            writes.append(["HINCRBY", f"{wk}:played", uid, 1])

    blob = dict(record)
    blob.update(rated)
    blob.update({
        "confirmed_by": confirmed_by or "", "auto_confirmed": bool(auto),
        # Recorded so the message can say a confirmation was skipped, rather
        # than an admin result being indistinguishable from an agreed one.
        "admin": bool(admin),
        "applied_at": stamp(now), "week": wk,
        # The undo snapshot: exactly what each player looked like beforehand.
        "snapshot": {uid: players[uid] for uid in uids},
    })

    writes.append(["SET", match_key(mid), json.dumps(blob)])
    writes.append(["LPUSH", HISTORY_KEY, mid])
    writes.append(["LTRIM", HISTORY_KEY, 0, HISTORY_LIMIT - 1])
    kv.pipeline(writes)
    kv.delete(pending_key(mid))
    return blob


def _advance(player, rated, mine, theirs, uid, mid, now):
    """One player's record after the match — pure, so the maths is testable."""
    games_for, games_against = rated[f"games_{mine}"], rated[f"games_{theirs}"]
    points_for, points_against = rated[f"points_{mine}"], rated[f"points_{theirs}"]
    won, lost = games_for > games_against, games_for < games_against
    streak = player["streak"]
    if won:
        streak = streak + 1 if streak > 0 else 1
    elif lost:
        streak = streak - 1 if streak < 0 else -1
    else:
        streak = 0

    rating = rated["after"][uid]
    return {
        **player,
        "rating": rating,
        "matches": player["matches"] + 1,
        "wins": player["wins"] + (1 if won else 0),
        "losses": player["losses"] + (1 if lost else 0),
        "draws": player["draws"] + (0 if won or lost else 1),
        "games_won": player["games_won"] + games_for,
        "games_lost": player["games_lost"] + games_against,
        "points_won": player["points_won"] + points_for,
        "points_lost": player["points_lost"] + points_against,
        "peak": max(player["peak"], rating),
        "streak": streak,
        "best_streak": max(player["best_streak"], streak),
        "last_played": stamp(now),
        "last_match": mid,
    }


# --- history and undo ------------------------------------------------------

def get_match(mid):
    raw = kv.get(match_key(mid))
    return json.loads(raw) if raw else None


def recent_matches(limit=10, uid=None):
    """The last `limit` applied matches, newest first — the whole ladder's, or
    one player's."""
    key = player_history_key(uid) if uid else HISTORY_KEY
    ids = kv.lrange(key, 0, max(0, limit - 1))
    if not ids:
        return []
    raws = kv.pipeline([["GET", match_key(i)] for i in ids])
    return [json.loads(r) for r in raws if r]


def last_match_by(uid):
    """The most recent match `uid` logged — what /tt undo acts on. Only their own
    submissions, so undo can't be used to erase someone else's result."""
    for blob in recent_matches(limit=HISTORY_LIMIT, uid=uid):
        if blob.get("logged_by") == uid:
            return blob
    return None


def can_undo(blob):
    """(ok, reason). Undo restores a snapshot, so it is only sound while that
    snapshot is still the whole story — the moment any player in the match has
    played again, rewinding them would also erase the later result."""
    uids = blob["side_a"] + blob["side_b"]
    current = get_players(uids)
    moved_on = [u for u in uids if (current.get(u) or {}).get("last_match") != blob["id"]]
    if moved_on:
        who = ", ".join(f"<@{u}>" for u in moved_on)
        return False, (f"{who} already played another match since this one, so undoing it "
                       "would wipe that result too. Log a correcting match instead.")
    return True, ""


def undo_match(blob):
    """Put every player back exactly as they were and forget the match."""
    mid, uids = blob["id"], blob["side_a"] + blob["side_b"]
    wk = blob.get("week") or week_key()
    cmds = []
    for uid in uids:
        snap = blob["snapshot"].get(uid)
        if snap:
            cmds.append(["HSET", player_key(uid)] + _flatten(snap))
        cmds.append(["LREM", player_history_key(uid), 0, mid])
        cmds.append(["HINCRBY", f"{wk}:delta", uid, -int(blob["deltas"].get(uid, 0))])
        cmds.append(["HINCRBY", f"{wk}:played", uid, -1])
    cmds.append(["LREM", HISTORY_KEY, 0, mid])
    cmds.append(["DEL", match_key(mid)])
    kv.pipeline(cmds)
    return blob


# --- weekly counters -------------------------------------------------------

# --- display names ---------------------------------------------------------

# Two tiers, because they mean different things. A handle is what Slack happened
# to tell us; a name is what the player asked to be called. The player wins.
NAMES_KEY = "tt:names"        # chosen with /tt name
HANDLES_KEY = "tt:handles"    # picked up from whatever payload carried one
NAMES_FETCHED_KEY = "tt:names:fetched"
NAMES_TTL_SECONDS = 6 * 3600
MAX_NAME = 32


def set_name(uid, name):
    """What this player asked to be called on the ladder. Returns the stored
    value, or None if it was blank."""
    name = " ".join((name or "").split())[:MAX_NAME]
    if not (uid and name):
        return None
    kv.hset(NAMES_KEY, uid, name)
    return name


def clear_name(uid):
    kv.hdel(NAMES_KEY, uid)


def remember_handle(uid, handle):
    """Note a name Slack volunteered. Never raises — it's a nicety, and must not
    take down the command that happened to carry it."""
    if not (uid and handle):
        return
    try:
        kv.hset(HANDLES_KEY, uid, handle, nx=True)  # never overwrite a real one
    except Exception:
        pass


def remember_names(mapping):
    if mapping:
        kv.hset_many(HANDLES_KEY, mapping)


def chosen_names():
    """Only the names people set themselves."""
    try:
        return kv.hgetall(NAMES_KEY) or {}
    except Exception:
        return {}


def names():
    """uid → best available name: what they chose, else what Slack offered."""
    try:
        merged = kv.hgetall(HANDLES_KEY) or {}
    except Exception:
        merged = {}
    merged.update(chosen_names())
    return merged


def names_are_stale(now=None):
    """True when the bulk name list is old enough to be worth refetching."""
    try:
        last = kv.get(NAMES_FETCHED_KEY)
    except Exception:
        return False
    if not last:
        return True
    try:
        return (now or now_ist()) - datetime.fromisoformat(last) > \
            timedelta(seconds=NAMES_TTL_SECONDS)
    except ValueError:
        return True


def mark_names_fetched(now=None):
    try:
        kv.set_(NAMES_FETCHED_KEY, stamp(now))
    except Exception:
        pass


def week_movement(key=None, when=None):
    """({uid: rating delta}, {uid: matches played}) for a week, named either by
    its key or by any datetime inside it.

    Incremented as matches are confirmed, the way pr-raiser counts PRs — a
    weekly scan over history would grow without bound and eventually outlive the
    serverless timeout.
    """
    wk = key or week_key(when)
    delta, played = kv.pipeline([["HGETALL", f"{wk}:delta"], ["HGETALL", f"{wk}:played"]])
    return _ints(kv.unflatten(delta)), _ints(kv.unflatten(played))


def _ints(raw):
    out = {}
    for k, v in (raw or {}).items():
        try:
            out[k] = int(v)
        except (TypeError, ValueError):
            continue
    return out
