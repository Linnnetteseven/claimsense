"""Small in-memory repository for unit tests; never selected by the app factory."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json


class MemoryRepository:
    backend_name = "oracle"

    def __init__(self):
        self.records: list[dict] = []
        self.claims: dict[str, dict] = {}
        self.versions: dict[str, list[dict]] = {}
        self.reviews: dict[tuple[str, str], dict] = {}
        self.outcomes: list[dict] = []
        self.references: dict[str, str] = {}

    def health(self):
        return True

    @staticmethod
    def _canonical(value):
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    def append_ledger_event(self, payload):
        from audit.chain import _GENESIS_HASH, _hash_record_v3
        seq = len(self.records) + 1
        previous = self.records[-1]["hash"] if self.records else _GENESIS_HASH
        claim_id = str(payload.get("claim_id") or "")
        claim_ref = self.references.setdefault(claim_id, hashlib.sha256(claim_id.encode()).hexdigest()[:32]) if claim_id else None
        timestamp = payload.get("timestamp", "2026-01-01T00:00:00Z")
        payload_hash = hashlib.sha256(self._canonical(payload).encode()).hexdigest()
        record = {
            "seq": seq, "type": payload.get("type", "event"), "claim_ref": claim_ref,
            "payload_hash": payload_hash, "timestamp": timestamp,
            "prev_hash": previous, "hash_version": 3,
        }
        record["hash"] = _hash_record_v3(previous, record)
        self.records.append(record)
        return record

    def append_ledger_events(self, payloads, existing=None):
        return [self.append_ledger_event(payload) for payload in payloads]

    def all_ledger_records(self):
        return deepcopy(self.records)

    def get_ledger_for_claim(self, claim_id):
        ref = self.references.get(claim_id)
        return [dict(row, claim_id=claim_id) for row in self.records if row.get("claim_ref") == ref]

    def get_claim(self, claim_id):
        return deepcopy(self.claims.get(claim_id))

    def list_claims(self):
        return deepcopy(list(self.claims.values()))

    def sync_claims(self, claims):
        for claim in claims:
            if claim["id"] not in self.claims:
                self.create_claim(claim)
        return self.list_claims()

    def create_claim(self, claim):
        from audit.chain import claim_fingerprint
        cleaned = {key: value for key, value in claim.items() if not key.startswith("_")}
        claim_id = cleaned["id"]
        self.claims[claim_id] = deepcopy(cleaned)
        version = {"version": 1, "payload": deepcopy(cleaned), "fingerprint": claim_fingerprint(cleaned)}
        self.versions[claim_id] = [version]
        self.append_ledger_event({"type": "claim_received", "claim_id": claim_id,
                                  "version_fingerprint": version["fingerprint"]})
        return deepcopy(cleaned)

    def record_claim_received(self, claim):
        return self.create_claim(claim) if claim["id"] not in self.claims else None

    def record_claims_received(self, claims):
        return self.sync_claims(claims)

    def record_claim_correction(self, claim_id, previous, updated):
        from audit.chain import claim_fingerprint
        old = self.claims[claim_id]
        body = deepcopy(updated)
        fingerprint = claim_fingerprint(body)
        version = {"version": len(self.versions[claim_id]) + 1, "payload": body, "fingerprint": fingerprint}
        self.append_ledger_event({"type": "claim_corrected", "claim_id": claim_id,
                                  "version": version["version"], "version_fingerprint": fingerprint})
        self.claims[claim_id] = body
        self.versions[claim_id].append(version)
        return version

    def record_validation(self, claim_id, claim, result):
        return self.append_ledger_event({"type": "validation", "claim_id": claim_id,
                                         "score": result["score"], "status": result["status"]})

    def record_event(self, payload):
        return self.append_ledger_event(payload)

    def verify_current_claim_version(self, claim_id, claim):
        from audit.chain import claim_fingerprint
        latest = self.versions[claim_id][-1]
        return {"status": "matches" if claim_fingerprint(claim) == latest["fingerprint"] else "mismatch",
                "version": latest["version"], "version_fingerprint": latest["fingerprint"]}

    def get_department_review(self, claim_id, department):
        return deepcopy(self.reviews.get((claim_id, department)))

    def save_department_review(self, claim_id, department, review):
        self.reviews[(claim_id, department)] = deepcopy(review)
        return deepcopy(review)

    def list_outcomes(self, claim_id=None):
        return deepcopy([row for row in self.outcomes if claim_id is None or row["claimId"] == claim_id])

    def save_outcome(self, outcome):
        self.outcomes.append(deepcopy(outcome))
        self.append_ledger_event({"type": "claim_outcome_recorded", "claim_id": outcome["claimId"],
                                  "outcome": outcome["outcome"]})
        return deepcopy(outcome)
