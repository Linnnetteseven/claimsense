"""
Explanation cache keyed by hash(rule_id, message).

Many claims fail the same way, so an explanation is reused across claims.
Uses Upstash Redis (REST) when UPSTASH_REDIS_REST_URL/TOKEN are set, else an
in-process dict (per serverless instance). Cache failures never block validation.
"""

import hashlib
import json
import logging
import os
import time

import httpx

logger = logging.getLogger(__name__)

TTL_SECONDS = 7 * 24 * 3600
_PREFIX = "hakiki:explain:v1:"
_memory: dict[str, tuple[float, dict]] = {}


def key_for(rule_id: str, message: str) -> str:
    return _PREFIX + hashlib.sha256(f"{rule_id}\n{message}".encode()).hexdigest()[:32]


def _upstash() -> tuple[str, str] | None:
    url, token = os.environ.get("UPSTASH_REDIS_REST_URL"), os.environ.get("UPSTASH_REDIS_REST_TOKEN")
    return (url, token) if url and token else None


def _redis(url: str, token: str, *command: str):
    resp = httpx.post(url, headers={"Authorization": f"Bearer {token}"}, json=list(command), timeout=2)
    resp.raise_for_status()
    return resp.json().get("result")


def get(key: str) -> dict | None:
    hit = _memory.get(key)
    if hit and hit[0] > time.time():
        return hit[1]
    upstash = _upstash()
    if upstash:
        try:
            raw = _redis(*upstash, "GET", key)
            if raw:
                value = json.loads(raw)
                _memory[key] = (time.time() + TTL_SECONDS, value)
                return value
        except Exception as exc:
            logger.warning("Explanation cache read failed: %s", exc)
    return None


def put(key: str, value: dict) -> None:
    _memory[key] = (time.time() + TTL_SECONDS, value)
    upstash = _upstash()
    if upstash:
        try:
            _redis(*upstash, "SET", key, json.dumps(value), "EX", str(TTL_SECONDS))
        except Exception as exc:
            logger.warning("Explanation cache write failed: %s", exc)
