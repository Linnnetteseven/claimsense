"""
One-off check: confirms your Upstash credentials actually work, before
wiring audit/chain.py into the rest of the app. Run this from the backend
folder once your .env has UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN set.

Usage:
    python test_upstash_connection.py
"""

import os
import sys
from dotenv import load_dotenv, find_dotenv

load_dotenv()

import httpx

URL = os.environ.get("UPSTASH_REDIS_REST_URL")
TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN")

if not URL or not TOKEN:
    print("❌ UPSTASH_REDIS_REST_URL or UPSTASH_REDIS_REST_TOKEN not found in .env")
    sys.exit(1)

print(f"Connecting to: {URL}")

try:
    # SET a test key
    resp = httpx.post(
        URL,
        headers={"Authorization": f"Bearer {TOKEN}"},
        json=["SET", "hakiki:connection_test", "it_works"],
        timeout=10,
    )
    resp.raise_for_status()
    print("✅ SET succeeded:", resp.json())

    # GET it back
    resp = httpx.post(
        URL,
        headers={"Authorization": f"Bearer {TOKEN}"},
        json=["GET", "hakiki:connection_test"],
        timeout=10,
    )
    resp.raise_for_status()
    result = resp.json().get("result")

    if result == "it_works":
        print("✅ GET succeeded — Upstash is fully working:", result)
    else:
        print("⚠️  GET returned unexpected value:", result)

    # Clean up the test key
    httpx.post(
        URL,
        headers={"Authorization": f"Bearer {TOKEN}"},
        json=["DEL", "hakiki:connection_test"],
        timeout=10,
    )
    print("✅ Cleanup done — you're ready to wire in audit/chain.py")

except Exception as exc:
    print(f"❌ Connection failed: {exc}")
    print("Double check the URL/token were copied from the REST API section, not the Redis CLI section.")
    sys.exit(1)