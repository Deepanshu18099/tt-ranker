"""
Replay every recorded match and rewrite the ladder from scratch.

For applying a scoring change to history rather than only to what comes next.
Edit the constants in elo.py, run this, and every rating, counter and stored
match becomes what it would have been had the new numbers always applied.

    python scripts/recompute.py            # dry run, the default
    python scripts/recompute.py --yes

What it rebuilds, from the stored matches alone:

  * every player's rating, record, games, points, peak and streaks
  * each match's before/after/deltas, so /tt history agrees with the board
  * each match's undo snapshot, so /tt undo stays exact afterwards
  * the weekly movement counters behind the standings post

Matches are replayed in the order they were *applied*, not the order they were
played — that is the order the original ratings were calculated in, and Elo is
not commutative, so any other order would produce different numbers.

Two things it cannot do. It only sees matches still in tt:history (capped at
store.HISTORY_LIMIT), so it is exact only while nothing has aged out; it says so
if any blob is missing. And a rating is not a wallet — nothing here touches
spins or settled bets, which stay as they were paid.

Behind a TLS-intercepting proxy, also set REQUESTS_CA_BUNDLE=vmock-ca.crt.
"""
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import elo
import kv
import parsing
import store


def load_history():
    """Every stored match, oldest application first, plus any ids we've lost."""
    ids = kv.lrange(store.HISTORY_KEY, 0, -1)
    blobs, missing = [], []
    for mid in ids:
        blob = store.get_match(mid)
        (blobs if blob else missing).append(blob or mid)
    blobs.sort(key=lambda b: (b.get("applied_at", ""), int(b.get("id", 0) or 0)))
    return blobs, missing


def replay(blobs):
    """(players, rewritten blobs, weekly counters) as if the current elo.py had
    always been in force. Pure — reads nothing and writes nothing."""
    state, weekly, rewritten = {}, {}, []

    for blob in blobs:
        # Re-read the scores under today's rules, which is the point of a replay.
        # A game logged 21-0 is a skunk typed as the number they play to; the
        # rating is identical either way, but the points totals shouldn't carry
        # ten points nobody played.
        blob = dict(blob, games=parsing.normalise_games(
            [tuple(g) for g in blob["games"]]))
        uids = blob["side_a"] + blob["side_b"]
        for uid in uids:
            state.setdefault(uid, store.new_player())

        def entries(side):
            return [{"uid": u, "rating": state[u]["rating"],
                     "games": elo.games_played(state[u])} for u in side]

        rated = elo.rate_match(entries(blob["side_a"]), entries(blob["side_b"]),
                               blob["games"])
        try:
            applied = datetime.fromisoformat(blob["applied_at"])
        except (KeyError, ValueError):
            applied = store.now_ist()

        # Each format carries its own Elo, so it is replayed on its own ratings
        # rather than derived from the overall pass.
        prefix = store.DOUBLES if rated["doubles"] else store.SINGLES

        def split_entries(side):
            return [{"uid": u,
                     "rating": store.split_view(state[u], prefix)["rating"],
                     "games": elo.games_played(store.split_view(state[u], prefix))}
                    for u in side]

        split = elo.rate_match(split_entries(blob["side_a"]),
                               split_entries(blob["side_b"]), blob["games"])

        snapshot = {uid: dict(state[uid]) for uid in uids}
        for side, mine, theirs in ((blob["side_a"], "a", "b"),
                                   (blob["side_b"], "b", "a")):
            for uid in side:
                advanced = store._advance(state[uid], rated, mine, theirs, uid,
                                          blob["id"], applied)
                advanced.update(store._advance_split(
                    state[uid], split, mine, theirs, uid, blob["id"], applied, prefix))
                state[uid] = advanced

        week = store.week_key(applied)
        bucket = weekly.setdefault(week, {"delta": {}, "played": {}})
        for uid in uids:
            bucket["delta"][uid] = bucket["delta"].get(uid, 0) + rated["deltas"][uid]
            bucket["played"][uid] = bucket["played"].get(uid, 0) + 1

        fresh = dict(blob)
        fresh.update(rated)
        fresh["split_rated"] = split
        fresh["split_prefix"] = prefix
        fresh["singles_rated"] = split if prefix == store.SINGLES else {}
        fresh["snapshot"] = snapshot
        fresh["week"] = week
        rewritten.append(fresh)

    return state, rewritten, weekly


def main(argv):
    if not kv.kv_available():
        sys.exit("No KV configured. Set KV_REST_API_URL and KV_REST_API_TOKEN.")

    blobs, missing = load_history()
    if not blobs:
        print("No matches recorded — nothing to replay.")
        return 0
    if missing:
        print(f"!! {len(missing)} match ids have no stored blob: {missing[:5]}")
        print("   The replay would be built on incomplete history. Stopping.")
        return 1

    doubles = sum(1 for b in blobs if b.get("doubles"))
    print(f"Replaying {len(blobs)} matches ({doubles} doubles) with:")
    print(f"  K {elo.K_PROVISIONAL}/{elo.K_ESTABLISHED} · doubles ×"
          f"{elo.DOUBLES_K_FACTOR} · mov gain {elo.MOV_GAIN} · "
          f"baseline {elo.MOV_BASELINE}\n")

    state, rewritten, weekly = replay(blobs)
    before = store.get_players(list(state))
    names = store.names()

    print(f"  {'player':<22}{'now':>7}{'after':>8}{'move':>7}{'singles':>9}{'doubles':>9}")
    for uid, player in sorted(state.items(), key=lambda i: -i[1]["rating"]):
        was = (before.get(uid) or {}).get("rating", elo.START_RATING)
        shift = player["rating"] - was
        name = names.get(uid) or f"@{uid[-4:]}"
        cols = []
        for view in (store.singles_view(player), store.doubles_view(player)):
            cols.append(f"{view['rating']}" if elo.games_played(view) else "—")
        print(f"  {name:<22}{was:>7}{player['rating']:>8}{shift:>+7}"
              f"{cols[0]:>9}{cols[1]:>9}")

    changed = sum(1 for uid, p in state.items()
                  if p["rating"] != (before.get(uid) or {}).get("rating", elo.START_RATING))
    print(f"\n  {changed} of {len(state)} ratings change.")
    print("  Wallets, spins and settled bets are untouched.")

    if "--yes" not in argv:
        print("\nDry run. Nothing written. Re-run with --yes.")
        return 0

    writes = []
    for uid, player in state.items():
        # Keep the day they joined; everything else is derived from the replay.
        player["joined"] = (before.get(uid) or {}).get("joined") or player["joined"]
        writes.append(["HSET", store.player_key(uid)] + store._flatten(player))
    for blob in rewritten:
        writes.append(["SET", store.match_key(blob["id"]), json.dumps(blob)])

    # Weekly counters are rebuilt, not adjusted: clearing first is the only way
    # to be sure a stale week isn't left behind to be added to.
    for key in kv.scan("tt:wk:*"):
        writes.append(["DEL", key])
    for week, bucket in weekly.items():
        for field, values in (("delta", bucket["delta"]), ("played", bucket["played"])):
            args = []
            for uid, value in values.items():
                args += [uid, value]
            if args:
                writes.append(["HSET", f"{week}:{field}"] + args)

    for i in range(0, len(writes), 50):
        kv.pipeline(writes[i:i + 50])
    print(f"\nRewrote {len(state)} players, {len(rewritten)} matches and "
          f"{len(weekly)} weeks of counters.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
