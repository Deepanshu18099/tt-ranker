"""
Replay every recorded match and rewrite the ladder from scratch.

The replay itself lives in rerate.py, shared with `/tt edit`.

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
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import elo
import kv
import rerate
import store
from rerate import load_history, replay


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

    rerate.write(state, rewritten, weekly, before=before)
    print(f"\nRewrote {len(state)} players, {len(rewritten)} matches and "
          f"{len(weekly)} weeks of counters.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
