"""
Tiny Upstash-Redis REST client — the whole database for tt-ranker.

No SDK, no deps beyond requests: Upstash takes one command as a JSON array over
HTTP, which suits Vercel's serverless runtime, where a pooled DB connection has
nowhere to live between invocations.

`pipeline()` matters more here than it did in pr-raiser: confirming a doubles
match reads four player records and writes four more, and at ~30ms a round trip
that is the difference between a snappy button and a spinner.

Config (set in Vercel + .env, then redeploy):
  KV_REST_API_URL / KV_REST_API_TOKEN                 (Upstash via the Vercel
                                                       Marketplace integration), or
  UPSTASH_REDIS_REST_URL / UPSTASH_REDIS_REST_TOKEN   (Upstash direct)

Unlike pr-raiser there is no degraded fallback mode — ratings have to live
somewhere — so callers check kv_available() and say so plainly instead.
"""
import os

import requests


def _config():
    url = os.environ.get("KV_REST_API_URL") or os.environ.get("UPSTASH_REDIS_REST_URL")
    token = os.environ.get("KV_REST_API_TOKEN") or os.environ.get("UPSTASH_REDIS_REST_TOKEN")
    return url, token


def kv_available():
    url, token = _config()
    return bool(url and token)


def _post(path, payload, timeout):
    url, token = _config()
    if not (url and token):
        raise RuntimeError("KV not configured")
    r = requests.post(url.rstrip("/") + path, json=payload, timeout=timeout,
                      headers={"Authorization": f"Bearer {token}"})
    r.raise_for_status()
    return r.json()


def _command(cmd, timeout=10):
    """Run one Redis command (a list like ["HSET", key, field, val]) and return
    its `result`. Raises requests.RequestException on transport/HTTP error."""
    return _post("", [str(c) for c in cmd], timeout).get("result")


def pipeline(cmds, timeout=15):
    """Run several commands in one HTTP round trip; returns a list of results in
    order. Not a transaction — Upstash runs them sequentially and a failure
    surfaces as an {"error": …} entry, so this is for batching reads and
    independent writes, never for anything needing atomicity across commands."""
    if not cmds:
        return []
    body = _post("/pipeline", [[str(c) for c in cmd] for cmd in cmds], timeout)
    return [entry.get("result") for entry in body]


# --- strings ---------------------------------------------------------------

def get(key):
    return _command(["GET", key])


def set_(key, value, ex=None, nx=False):
    """SET with optional TTL and NX. Returns None when NX loses the race, which
    is how a caller can claim a key exactly once."""
    cmd = ["SET", key, value]
    if ex:
        cmd += ["EX", int(ex)]
    if nx:
        cmd += ["NX"]
    return _command(cmd)


def incr(key):
    return _command(["INCR", key])


def delete(*keys):
    if not keys:
        return 0
    return _command(["DEL", *keys])


# --- hashes ----------------------------------------------------------------

def hset(key, field, value, nx=False):
    return _command(["HSETNX" if nx else "HSET", key, field, value])


def hget(key, field):
    return _command(["HGET", key, field])


def hgetall(key):
    """The hash as a dict (Upstash returns a flat [f1, v1, f2, v2, …])."""
    return unflatten(_command(["HGETALL", key]))


def unflatten(res):
    """Flat [f1, v1, f2, v2, …] → dict. Exposed because pipelined HGETALLs come
    back in the same shape and need the same treatment."""
    res = res or []
    return {res[i]: res[i + 1] for i in range(0, len(res) - 1, 2)}


def hset_many(key, mapping):
    """Set several hash fields in one round trip."""
    args = []
    for k, v in mapping.items():
        args += [k, v]
    return _command(["HSET", key, *args]) if args else 0


def hincrby(key, field, amount=1):
    """Add to a hash field (creating it at 0 first). Atomic, so concurrent
    confirmations can't lose a count the way read-modify-write would."""
    return _command(["HINCRBY", key, field, amount])


def hdel(key, *fields):
    if not fields:
        return 0
    return _command(["HDEL", key, *fields])


# --- sets ------------------------------------------------------------------

def sadd(key, *members):
    """Add members to a set; returns how many were NEW. That count is what makes
    an atomic claim possible — exactly one racing caller sees 1 for a member."""
    if not members:
        return 0
    return _command(["SADD", key, *members])


def srem(key, *members):
    """Remove members; returns how many were actually there. Like sadd, exactly
    one racing caller sees 1 — which is how a pending match is claimed."""
    if not members:
        return 0
    return _command(["SREM", key, *members])


def smembers(key):
    return _command(["SMEMBERS", key]) or []


def sismember(key, member):
    return bool(_command(["SISMEMBER", key, member]))


# --- lists -----------------------------------------------------------------

def lpush(key, *values):
    if not values:
        return 0
    return _command(["LPUSH", key, *values])


def lrange(key, start=0, stop=-1):
    return _command(["LRANGE", key, start, stop]) or []


def ltrim(key, start, stop):
    return _command(["LTRIM", key, start, stop])


def lrem(key, value, count=0):
    """Remove `value` from a list — how an undone match leaves the history."""
    return _command(["LREM", key, count, value])


# --- keys ------------------------------------------------------------------

def expire(key, seconds):
    """Give a key a TTL so it cleans itself up instead of living forever."""
    return _command(["EXPIRE", key, int(seconds)])


def scan(match="*", count=200):
    """Every key matching a pattern, following the cursor to the end.

    Only used by the admin reset script. Note this database may be shared with
    another bot, which is exactly why that script matches a prefix instead of
    reaching for FLUSHDB.
    """
    keys, cursor = [], "0"
    while True:
        cursor, batch = _command(["SCAN", cursor, "MATCH", match, "COUNT", count])
        keys += batch or []
        if str(cursor) == "0":
            return sorted(set(keys))
