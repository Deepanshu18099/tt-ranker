"""
Wipe the ladder — every rating, session and pending result — and nothing else.

For clearing out test data before onboarding real players, or starting a fresh
season. It is NOT an emergency tool: there is no undo, and `tt:match:*` holds
the only record of what anyone ever played.

**Why this exists instead of FLUSHDB.** This Redis is shared with pr-raiser,
whose keys (`prwatch:*`, `prnotif:*`, `prlb:*`) live right next to the ladder's.
FLUSHDB would take its PR watchers and leaderboard totals with it. This deletes
by prefix and refuses to touch a key that isn't the ladder's.

Usage — dry run first, it is the default:

    python scripts/reset_ladder.py              # lists what would go
    python scripts/reset_ladder.py --yes        # actually deletes

Reads KV_REST_API_URL / KV_REST_API_TOKEN from the environment or .env, so point
it at the same credentials Vercel uses.
"""
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import kv

PREFIX = "tt:"
BATCH = 100


def summarise(keys):
    """Group keys by their shape, so the report reads as 'what' not 'how many'."""
    kinds = Counter()
    for key in keys:
        parts = key.split(":")
        kinds[":".join(parts[:2]) + (":*" if len(parts) > 2 else "")] += 1
    return kinds


def main(argv):
    if not kv.kv_available():
        sys.exit("No KV configured. Set KV_REST_API_URL and KV_REST_API_TOKEN "
                 "(copy them from the Vercel project, or a .env alongside this repo).")

    keys = kv.scan(f"{PREFIX}*")
    # Belt and braces: scan's MATCH already filtered, but a typo in PREFIX must
    # never be able to reach another bot's data.
    strays = [k for k in keys if not k.startswith(PREFIX)]
    if strays:
        sys.exit(f"Refusing to run — SCAN returned keys outside {PREFIX!r}: {strays[:5]}")

    if not keys:
        print(f"Nothing to do: no {PREFIX}* keys in this database.")
        return 0

    print(f"Found {len(keys)} ladder keys:\n")
    for kind, n in sorted(summarise(keys).items()):
        print(f"  {kind:<28}{n:>6}")

    others = len(kv.scan("*")) - len(keys)
    print(f"\n  {others} other keys in this database will NOT be touched.")

    if "--yes" not in argv:
        print("\nDry run. Nothing deleted. Re-run with --yes to go through with it.")
        return 0

    deleted = 0
    for i in range(0, len(keys), BATCH):
        deleted += kv.delete(*keys[i:i + BATCH]) or 0
    print(f"\nDeleted {deleted} keys. The ladder is empty — every rating, session "
          f"and pending result is gone.\nRun `/tt sync` in the channel to put "
          f"everyone back on at the starting rating.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
