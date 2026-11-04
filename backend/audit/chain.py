"""Optional Redis-backed hash-chained audit ledger with sequence-numbered entries."""
import hashlib
import json
import os
import time
from threading import Lock
from typing import Optional
import httpx

UPSTASH_URL = os.environ.get("UPSTASH_REDIS_REST_URL")
UPSTASH_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN")
LEDGER_KEY = "hakiki:audit:ledger"
LATEST_HASH_KEY = "hakiki:audit:latest_hash"
_GENESIS_HASH = "0" * 16
_MEMORY_RECORDS: list[dict] = []
_MEMORY_LOCK = Lock()

def _audit_enabled() -> bool:
    return bool(UPSTASH_URL and UPSTASH_TOKEN)

def _redis(*command: str):
    resp = httpx.post(UPSTASH_URL, headers={"Authorization": f"Bearer {UPSTASH_TOKEN}"}, json=list(command), timeout=10)
    resp.raise_for_status()
    return resp.json().get("result")

def _canonical(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))

def _hash_record(prev_hash: str, payload: dict) -> str:
    return hashlib.sha256((prev_hash + _canonical(payload)).encode()).hexdigest()

def _hash_record_v1(prev_hash: str, payload: dict) -> str:
    return hashlib.sha256((prev_hash + _canonical(payload)).encode()).hexdigest()[:16]

def _redis_all_records() -> list[dict]:
    if not _audit_enabled():
        # Keep the demo auditable without Redis. This fallback is process-local;
        # configure Upstash for persistence across restarts and server instances.
        with _MEMORY_LOCK:
            return list(_MEMORY_RECORDS)
    raw = _redis("LRANGE", LEDGER_KEY, "0", "-1") or []
    return [json.loads(item) for item in raw]

def _redis_append(payload: dict) -> Optional[dict]:
    if not _audit_enabled():
        with _MEMORY_LOCK:
            prev_hash = _MEMORY_RECORDS[-1]["hash"] if _MEMORY_RECORDS else _GENESIS_HASH
            payload = {**payload, "seq": len(_MEMORY_RECORDS) + 1, "hash_version": 2}
            digest = _hash_record(prev_hash, payload)
            record = {**payload, "prev_hash": prev_hash, "hash": digest}
            _MEMORY_RECORDS.append(record)
            return record
    records = _redis_all_records()
    prev_hash = records[-1]["hash"] if records else (_redis("GET", LATEST_HASH_KEY) or _GENESIS_HASH)
    payload = {**payload, "seq": len(records) + 1, "hash_version": 2}
    digest = _hash_record(prev_hash, payload)
    record = {**payload, "prev_hash": prev_hash, "hash": digest}
    _redis("RPUSH", LEDGER_KEY, json.dumps(record, separators=(",", ":")))
    _redis("SET", LATEST_HASH_KEY, digest)
    return record

def _redis_append_many(payloads: list[dict], existing: Optional[list[dict]] = None) -> list[dict]:
    """Append a group of events after one ledger read and one batched Redis write."""
    if not payloads:
        return []
    if not _audit_enabled():
        with _MEMORY_LOCK:
            previous = _MEMORY_RECORDS[-1]["hash"] if _MEMORY_RECORDS else _GENESIS_HASH
            records = []
            for payload in payloads:
                body = {**payload, "seq": len(_MEMORY_RECORDS) + 1, "hash_version": 2}
                digest = _hash_record(previous, body)
                record = {**body, "prev_hash": previous, "hash": digest}
                _MEMORY_RECORDS.append(record)
                records.append(record)
                previous = digest
            return records

    existing = _redis_all_records() if existing is None else existing
    previous = existing[-1]["hash"] if existing else (_redis("GET", LATEST_HASH_KEY) or _GENESIS_HASH)
    records = []
    for payload in payloads:
        body = {**payload, "seq": len(existing) + len(records) + 1, "hash_version": 2}
        digest = _hash_record(previous, body)
        records.append({**body, "prev_hash": previous, "hash": digest})
        previous = digest
    serialized = [json.dumps(record, separators=(",", ":")) for record in records]
    _redis("RPUSH", LEDGER_KEY, *serialized)
    _redis("SET", LATEST_HASH_KEY, previous)
    return records


def _repository():
    from db.factory import get_repository
    return get_repository()


def _oracle_active(repository=None) -> bool:
    repository = repository or _repository()
    return repository.backend_name == "oracle" or (
        repository.backend_name == "oracle_with_fallback"
        and repository.active_backend == "oracle"
    )


def all_records() -> list[dict]:
    return _repository().all_ledger_records()


def _append(payload: dict) -> Optional[dict]:
    return _repository().append_ledger_event(payload)


def _append_many(payloads: list[dict], existing: Optional[list[dict]] = None) -> list[dict]:
    return _repository().append_ledger_events(payloads, existing)

def claim_fingerprint(claim: dict) -> str:
    """Fingerprint a complete claim version without storing its contents in the ledger."""
    claim_data = {key: value for key, value in claim.items() if not str(key).startswith("_")}
    return hashlib.sha256(_canonical(claim_data).encode("utf-8")).hexdigest()


def _claim_events(claim_id: str) -> list[dict]:
    return [record for record in all_records() if record.get("claim_id") == claim_id]


def _record_claim_received_legacy(claim: dict) -> Optional[dict]:
    """Record the first version of a claim once, when Hakiki ingests it."""
    claim_id = str(claim.get("id") or "")
    if not claim_id:
        return None
    try:
        events = _claim_events(claim_id)
        existing = next((event for event in events if event.get("type") == "claim_received"), None)
        if existing:
            return existing
        return _append({
            "type": "claim_received", "claim_id": claim_id, "version": 1,
            "version_fingerprint": claim_fingerprint(claim),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })
    except Exception:
        return None

def _record_claims_received_legacy(claims: list[dict]) -> list[dict]:
    """Record newly ingested claims with one ledger scan for an entire queue load."""
    try:
        records = all_records()
        received_ids = {
            str(record.get("claim_id"))
            for record in records
            if record.get("type") == "claim_received"
        }
        payloads = []
        pending_ids = set()
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        for claim in claims:
            claim_id = str(claim.get("id") or "")
            if not claim_id or claim_id in received_ids or claim_id in pending_ids:
                continue
            pending_ids.add(claim_id)
            payloads.append({
                "type": "claim_received", "claim_id": claim_id, "version": 1,
                "version_fingerprint": claim_fingerprint(claim), "timestamp": timestamp,
            })
        return _append_many(payloads, existing=records)
    except Exception:
        # Audit storage remains optional; never block loading the claims queue.
        return []


def record_claim_received(claim: dict) -> Optional[dict]:
    repository = _repository()
    return repository.record_claim_received(claim)


def record_claims_received(claims: list[dict]) -> list[dict]:
    repository = _repository()
    return repository.record_claims_received(claims)


def _record_claim_correction_legacy(claim_id: str, previous: dict, updated: dict) -> Optional[dict]:
    """Record a new immutable version fingerprint and changed field names."""
    try:
        events = _claim_events(claim_id)
        versions = [event for event in events if event.get("type") in {"claim_received", "claim_corrected"}]
        prior = versions[-1] if versions else record_claim_received(previous)
        if prior and prior.get("version_fingerprint") == claim_fingerprint(updated):
            return None
        changed_fields = sorted(
            key for key in set(previous) | set(updated)
            if key != "id" and previous.get(key) != updated.get(key)
        )
        return _append({
            "type": "claim_corrected", "claim_id": claim_id,
            "from_version": int((prior or {}).get("version", 1)),
            "version": int((prior or {}).get("version", 1)) + 1,
            "previous_version_fingerprint": (prior or {}).get("version_fingerprint"),
            "version_fingerprint": claim_fingerprint(updated),
            "changed_fields": changed_fields,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })
    except Exception:
        return None


def record_claim_correction(claim_id: str, previous: dict, updated: dict) -> Optional[dict]:
    return _repository().record_claim_correction(claim_id, previous, updated)


def verify_current_claim_version(claim_id: str, claim: dict) -> dict:
    """Compare the backend's current claim with the most recently recorded version fingerprint."""
    repository = _repository()
    if _oracle_active(repository):
        return repository.verify_current_claim_version(claim_id, claim)
    versions = [event for event in _claim_events(claim_id) if event.get("type") in {"claim_received", "claim_corrected"}]
    if not versions:
        return {"status": "not_recorded"}
    latest = versions[-1]
    current_fingerprint = claim_fingerprint(claim)
    return {
        "status": "matches" if current_fingerprint == latest.get("version_fingerprint") else "mismatch",
        "version": latest.get("version"),
        "event_seq": latest.get("seq"),
        "version_fingerprint": latest.get("version_fingerprint"),
    }


def _record_validation_legacy(claim_id: str, validation_result: dict, claim: Optional[dict] = None) -> Optional[dict]:
    """Append a validation record; unavailable Redis never blocks validation."""
    try:
        events = _claim_events(claim_id)
        fingerprint = claim_fingerprint(claim) if claim else None
        versions = [event for event in events if event.get("type") in {"claim_received", "claim_corrected"}]
        version = next((event.get("version") for event in reversed(versions) if event.get("version_fingerprint") == fingerprint), None)
        return _append({
            "type": "validation", "claim_id": claim_id,
            "version": version, "version_fingerprint": fingerprint,
            "score": validation_result["score"], "status": validation_result["status"],
            "error_count": validation_result["error_count"],
            "warning_count": validation_result["warning_count"],
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })
    except Exception:
        # Audit storage is optional and must not interrupt claim validation.
        return None


def record_validation(claim_id: str, validation_result: dict, claim: Optional[dict] = None) -> Optional[dict]:
    repository = _repository()
    if _oracle_active(repository):
        return repository.record_validation(claim_id, claim or {}, validation_result)
    return repository.record_validation(claim_id, claim or {}, validation_result)


def record_department_review(claim_id: str, department: str, review_event: dict, action: str, step_title: Optional[str] = None, claim: Optional[dict] = None) -> Optional[dict]:
    """Append a client-computed review fingerprint; raw evidence and notes stay in the browser."""
    repository = _repository()
    if _oracle_active(repository):
        return repository.record_event({
            "type": action, "claim_id": claim_id, "department": department,
            "version_fingerprint": claim_fingerprint(claim) if claim else None,
            "step_title": step_title,
            "completed_checks": sorted(review_event.get("completed_checks", [])),
            "review_fingerprint": review_event["review_fingerprint"],
            "signed_off": bool(review_event.get("signed_off")),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })
    try:
        claim_events = _claim_events(claim_id)
        versions = [event for event in claim_events if event.get("type") in {"claim_received", "claim_corrected"}]
        version_fingerprint = claim_fingerprint(claim) if claim else None
        version = next((event.get("version") for event in reversed(versions) if event.get("version_fingerprint") == version_fingerprint), None)
        return _append({
            "type": action, "claim_id": claim_id, "department": department,
            "version": version, "version_fingerprint": version_fingerprint,
            "step_title": step_title,
            "completed_checks": sorted(review_event.get("completed_checks", [])),
            "review_fingerprint": review_event["review_fingerprint"],
            "signed_off": bool(review_event.get("signed_off")),
            # This is a typed display name, not an authenticated identity.
            "actor_label": review_event.get("actor_label") or None,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })
    except Exception:
        return None


def record_staff_review(claim_id: str, claim: dict, reviewer_label: str, decision: str) -> Optional[dict]:
    """Record a claims officer's explicit review of the current saved version."""
    repository = _repository()
    if _oracle_active(repository):
        return repository.record_event({
            "type": "staff_review_completed", "claim_id": claim_id,
            "version_fingerprint": claim_fingerprint(claim),
            "decision": decision,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })
    try:
        fingerprint = claim_fingerprint(claim)
        versions = [event for event in _claim_events(claim_id) if event.get("type") in {"claim_received", "claim_corrected"}]
        version_event = next((event for event in reversed(versions) if event.get("version_fingerprint") == fingerprint), None)
        return _append({
            "type": "staff_review_completed", "claim_id": claim_id,
            "version": version_event.get("version") if version_event else None,
            "version_fingerprint": fingerprint,
            "decision": decision,
            "actor_label": reviewer_label[:120],
            "actor_verified": False,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })
    except Exception:
        return None


def record_submission(claim_id: str, claim: dict, outcome: str, detail: Optional[str] = None) -> Optional[dict]:
    repository = _repository()
    if _oracle_active(repository):
        return repository.record_event({
            "type": "submission", "claim_id": claim_id,
            "version_fingerprint": claim_fingerprint(claim), "outcome": outcome,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })
    try:
        events = _claim_events(claim_id)
        versions = [event for event in events if event.get("type") in {"claim_received", "claim_corrected"}]
        fingerprint = claim_fingerprint(claim)
        version = next((event.get("version") for event in reversed(versions) if event.get("version_fingerprint") == fingerprint), None)
        return _append({
            "type": "submission", "claim_id": claim_id, "version": version,
            "version_fingerprint": fingerprint, "outcome": outcome, "detail": detail,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })
    except Exception:
        return None

def append_anchor_event(event: dict) -> Optional[dict]:
    return _append({"type": "anchor", "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **event})

def get_chain_for_claim(claim_id: str) -> list[dict]:
    repository = _repository()
    if _oracle_active(repository):
        return repository.get_ledger_for_claim(claim_id)
    return [r for r in all_records() if r.get("claim_id") == claim_id]


def _hash_record_v3(prev_hash: str, record: dict) -> str:
    body = {
        "seq": record.get("seq"),
        "claim_ref": record.get("claim_ref"),
        "event_type": record.get("type"),
        "payload_hash": record.get("payload_hash"),
        "timestamp": record.get("timestamp"),
    }
    return hashlib.sha256((prev_hash + _canonical(body)).encode()).hexdigest()

def _hash_record_v4(prev_hash: str, record: dict) -> Optional[str]:
    """Use the exact hash input persisted alongside Oracle ledger records."""
    header = record.get("hash_input")
    expected_keys = {"seq", "claim_ref", "event_type", "payload_hash", "timestamp"}
    if not isinstance(header, dict) or set(header) != expected_keys:
        return None
    if (header.get("seq") != record.get("seq")
            or header.get("claim_ref") != record.get("claim_ref")
            or header.get("event_type") != record.get("type")
            or header.get("payload_hash") != record.get("payload_hash")
            or header.get("timestamp") != record.get("timestamp")):
        return None
    return hashlib.sha256((prev_hash + _canonical(header)).encode()).hexdigest()

def verify_records(records: list[dict]) -> dict:
    prev_hash = _GENESIS_HASH
    for i, record in enumerate(records):
        payload = {k: v for k, v in record.items() if k not in ("prev_hash", "hash")}
        if record.get("hash_version") == 3:
            expected = _hash_record_v3(prev_hash, record)
        elif record.get("hash_version") == 4:
            expected = _hash_record_v4(prev_hash, record)
        elif record.get("hash_version") == 2:
            expected = _hash_record(prev_hash, payload)
        else:
            expected = _hash_record_v1(prev_hash, payload)
        if expected != record.get("hash") or record.get("prev_hash") != prev_hash:
            return {"verified": False, "total": len(records), "broken_at": i}
        if record.get("seq") is not None and record["seq"] != i + 1:
            return {"verified": False, "total": len(records), "broken_at": i, "reason": "sequence_mismatch"}
        prev_hash = record["hash"]
    repository = _repository()
    if not _oracle_active(repository) and _audit_enabled():
        latest = _redis("GET", LATEST_HASH_KEY)
        if latest and latest != (records[-1]["hash"] if records else _GENESIS_HASH):
            return {"verified": False, "total": len(records), "broken_at": len(records), "reason": "tail_mismatch"}
    return {"verified": True, "total": len(records), "broken_at": None}

def verify_chain() -> dict:
    if not _audit_enabled():
        records = all_records()
        if not records:
            return {"verified": None, "total": 0, "broken_at": None, "note": "Audit trail not configured"}
        return {**verify_records(records), "note": "Process-local audit history; configure Upstash for persistence"}
    return verify_records(all_records())
