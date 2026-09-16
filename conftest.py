"""Test bootstrap: set dummy env vars before app modules import.

bot.build_app() reads SLACK_BOT_TOKEN at call time and api/index imports it at
module load, so these must exist before collection imports anything. The KV pair
is set because kv.kv_available() reads the environment directly — the fake in
tests/fake_kv.py replaces the HTTP transport, not the configuration check.

setdefault means a real .env (loaded by bot via python-dotenv, override=False)
never clobbers these, and tests stay hermetic — nothing reaches the network.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ.setdefault("SLACK_BOT_TOKEN", "xoxb-test-token")
os.environ.setdefault("SLACK_SIGNING_SECRET", "test-signing-secret")
os.environ["KV_REST_API_URL"] = "https://fake.upstash.io"
os.environ["KV_REST_API_TOKEN"] = "fake-token"
