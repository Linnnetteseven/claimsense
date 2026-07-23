"""
Tamper-evident audit trail for claim validations.

Each validation result is hashed and linked to the previous record's hash,
forming an append-only chain. Altering any past record breaks every hash
computed after it in the chain — that's what verify_chain() checks.

Storage: Upstash Redis via REST API. Chosen because Vercel serverless
functions don't have a persistent filesystem across invocations, and
Upstash's REST API works over plain HTTPS (no persistent TCP connection
needed, which fits serverless well). Uses httpx, already a dependency.
"""

import hashlib
import json
import os
import time
from typing import Optional

import httpx

UPSTASH_URL = os.environ.get("UPSTASH_REDIS_REST_URL")
UPSTASH_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN")

LEDGER_KEY = "hakiki:audit:ledger"
LATEST_HASH_KEY = "hakiki:audit:latest_hash"

_GENESIS_HASH = "0" * 16


def _audit_enabled() -> bool:
    return bool(UPSTASH_URL and UPSTASH_TOKEN)


def _redis(*command: str):
    """Minimal Upstash REST client — one HTTPS call per Redis command."""
    resp = httpx.post(
        UPSTASH_URL,
        headers={"Authorization": f"Bearer {UPSTASH_TOKEN}"},
        json=list(command),
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json().get("result")


def _hash_record(prev_hash: str, payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256((prev_hash + canonical).encode()).hexdigest()[:16]


def record_validation(claim_id: str, validation_result: dict) -> Optional[dict]:
    """
    Call this right after engine.validate() runs. Appends a new block to the
    ledger, linked to the previous block's hash.

    Returns None if Upstash isn't configured — the rest of the app should
    keep working without the audit trail rather than break claim validation
    over a missing optional feature.
    """
    if not _audit_enabled():
        return None

    prev_hash = _redis("GET", LATEST_HASH_KEY) or _GENESIS_HASH

    payload = {
        "claim_id": claim_id,
        "score": validation_result["score"],
        "status": validation_result["status"],
        "error_count": validation_result["error_count"],
        "warning_count": validation_result["warning_count"],
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    new_hash = _hash_record(prev_hash, payload)
    record = {**payload, "prev_hash": prev_hash, "hash": new_hash}

    _redis("RPUSH", LEDGER_KEY, json.dumps(record))
    _redis("SET", LATEST_HASH_KEY, new_hash)

    return record


def get_chain_for_claim(claim_id: str) -> list[dict]:
    """All ledger entries for one claim, oldest first."""
    if not _audit_enabled():
        return []

    raw_entries = _redis("LRANGE", LEDGER_KEY, "0", "-1") or []
    all_records = [json.loads(r) for r in raw_entries]
    return [r for r in all_records if r["claim_id"] == claim_id]


def verify_chain() -> dict:
    """
    Recomputes every hash in the full ledger and checks it against what's
    stored. Returns whether the whole chain is intact, and the index where
    it first breaks if not.
    """
    if not _audit_enabled():
        return {"verified": None, "total": 0, "broken_at": None, "note": "Audit trail not configured"}

    raw_entries = _redis("LRANGE", LEDGER_KEY, "0", "-1") or []
    records = [json.loads(r) for r in raw_entries]

    prev_hash = _GENESIS_HASH
    for i, record in enumerate(records):
        payload = {k: v for k, v in record.items() if k not in ("prev_hash", "hash")}
        expected = _hash_record(prev_hash, payload)
        if expected != record["hash"] or record["prev_hash"] != prev_hash:
            return {"verified": False, "total": len(records), "broken_at": i}
        prev_hash = record["hash"]

    return {"verified": True, "total": len(records), "broken_at": None}