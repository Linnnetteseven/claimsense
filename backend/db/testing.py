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
        self.validation_runs: list[dict] = []
        self.statuses: dict[str, str] = {}
        self.event_payloads: list[dict] = []
        self.anchors: list[dict] = []
        self.verification_checkpoint: dict | None = None

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
        self.event_payloads.append(deepcopy(payload))
        return record

    def append_ledger_events(self, payloads, existing=None):
        return [self.append_ledger_event(payload) for payload in payloads]

    def all_ledger_records(self):
        return deepcopy(self.records)

    def get_ledger_head(self):
        return {"seq": len(self.records), "hash": self.records[-1]["hash"] if self.records else "0" * 16}

    def get_ledger_record_hash(self, seq):
        record = next((row for row in self.records if int(row["seq"]) == int(seq)), None)
        return {"seq": int(record["seq"]), "hash": record["hash"], "prev_hash": record["prev_hash"]} if record else None

    def get_ledger_records_after(self, seq):
        return deepcopy([row for row in self.records if int(row["seq"]) > int(seq)])

    def has_non_anchor_events_after(self, seq, through_seq):
        return any(int(seq) < int(row["seq"]) <= int(through_seq) and row.get("type") != "anchor" for row in self.records)

    def get_verification_checkpoint(self):
        return deepcopy(self.verification_checkpoint)

    def save_verification_checkpoint(self, seq, digest):
        self.verification_checkpoint = {"seq": int(seq), "hash": digest, "verified_at": "test"}

    def get_anchor_by_root(self, root_hash):
        return deepcopy(next((row for row in self.anchors if row["root_hash"] == root_hash), None))

    def create_pending_anchor(self, from_seq, to_seq, root_hash, head_hash):
        existing = self.get_anchor_by_root(root_hash)
        if existing:
            existing["_created"] = False
            return existing
        anchor = {"id": len(self.anchors) + 1, "from_seq": int(from_seq), "to_seq": int(to_seq),
                  "root_hash": root_hash, "head_hash": head_hash, "tx_hash": None,
                  "status": "pending", "created_at": "test"}
        self.anchors.append(anchor)
        anchor["_created"] = True
        return deepcopy(anchor)

    def update_anchor_submission(self, root_hash, tx_hash):
        anchor = self.get_anchor_by_root(root_hash)
        if anchor:
            anchor.update(tx_hash=tx_hash)
            self._replace_anchor(anchor)
        return anchor

    def update_anchor_status(self, root_hash, status):
        anchor = self.get_anchor_by_root(root_hash)
        if anchor:
            anchor.update(status=status)
            self._replace_anchor(anchor)
        return anchor

    def backfill_anchor_head_hash(self, root_hash, head_hash):
        anchor = self.get_anchor_by_root(root_hash)
        if anchor and not anchor.get("head_hash"):
            anchor.update(head_hash=head_hash)
            self._replace_anchor(anchor)
        return anchor

    def finalize_anchor(self, root_hash, event_payload):
        anchor = self.get_anchor_by_root(root_hash)
        if not anchor:
            raise ValueError("Anchor row was not found")
        if anchor["status"] == "confirmed":
            return {"updated": False, "anchor": anchor}
        anchor.update(status="confirmed")
        self._replace_anchor(anchor)
        event = self.append_ledger_event(event_payload)
        return {"updated": True, "event": event, "anchor": anchor}

    def _replace_anchor(self, updated):
        self.anchors = [updated if row["root_hash"] == updated["root_hash"] else row for row in self.anchors]

    def list_anchor_records(self):
        return deepcopy(self.anchors)

    def get_ledger_for_claim(self, claim_id):
        ref = self.references.get(claim_id)
        return [dict(row, claim_id=claim_id) for row in self.records if row.get("claim_ref") == ref]

    def get_claim(self, claim_id):
        claim = deepcopy(self.claims.get(claim_id))
        if claim is not None:
            from audit.chain import claim_fingerprint
            latest = self.versions[claim_id][-1]
            outcomes = self.list_outcomes(claim_id)
            latest_outcome = outcomes[-1] if outcomes else None
            claim["_lifecycle"] = {
                "status": self.statuses.get(claim_id, "needs_revalidation"),
                "version": latest["version"],
                "version_fingerprint": latest["fingerprint"],
                "latest_outcome": latest_outcome.get("outcome") if latest_outcome else None,
                "latest_outcome_reason": latest_outcome.get("reasonCategory") if latest_outcome else None,
            }
        return claim

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
        self.statuses[claim_id] = "needs_revalidation"
        self.append_ledger_event({"type": "claim_received", "claim_id": claim_id,
                                  "version_fingerprint": version["fingerprint"]})
        return deepcopy(cleaned)

    def record_claim_received(self, claim):
        return self.create_claim(claim) if claim["id"] not in self.claims else None

    def record_claims_received(self, claims):
        return self.sync_claims(claims)

    def record_claim_correction(self, claim_id, previous, updated):
        from audit.chain import claim_fingerprint
        if self.statuses.get(claim_id) == "submitted":
            raise ValueError("Submitted claims are locked; create a correction version first")
        old = self.claims[claim_id]
        body = deepcopy(updated)
        fingerprint = claim_fingerprint(body)
        version = {"version": len(self.versions[claim_id]) + 1, "payload": body, "fingerprint": fingerprint}
        self.append_ledger_event({"type": "claim_corrected", "claim_id": claim_id,
                                  "version": version["version"], "version_fingerprint": fingerprint})
        self.claims[claim_id] = body
        self.versions[claim_id].append(version)
        self.statuses[claim_id] = "needs_revalidation"
        return version

    def record_validation(self, claim_id, claim, result, informational=False):
        from audit.chain import claim_fingerprint
        current = self.versions[claim_id][-1]
        if self.statuses.get(claim_id) == "submitted" and not informational:
            raise ValueError("Submitted claims are locked; use read-only re-check")
        fingerprint = claim_fingerprint(claim)
        version_number = current["version"] if informational else current["version"] + 1
        event = self.append_ledger_event({
            "type": "informational_validation" if informational else "validation",
            "claim_id": claim_id, "version": version_number,
            "version_fingerprint": fingerprint, "score": result["score"], "status": result["status"],
            "rules_version": result.get("rules_version"), "rules_date": result.get("rules_date"),
            "informational": bool(informational),
        })
        run = {"claim_id": claim_id, "version": version_number, "score": result["score"],
               "status": result["status"], "error_count": result["error_count"],
               "rules_version": result.get("rules_version"), "rules_date": result.get("rules_date"),
               "informational": bool(informational), "fingerprint": fingerprint}
        self.validation_runs.append(run)
        if not informational:
            snapshot = {key: value for key, value in claim.items() if not key.startswith("_")}
            self.versions[claim_id].append({"version": version_number, "payload": deepcopy(snapshot),
                                            "fingerprint": fingerprint, "created_by": "validation_run"})
            self.claims[claim_id] = snapshot
            self.statuses[claim_id] = "ready" if result["status"] == "Ready for Submission" else "needs_review" if result["status"] == "Needs Review" else "blocked"
        # Return decoded detail fields as Oracle's adapter does, without
        # decorating the hash-chain header stored in `records`.
        return {**event, "version": version_number, "version_fingerprint": fingerprint,
                "informational": bool(informational)}

    def get_claim_lifecycle(self, claim_id):
        claim = self.get_claim(claim_id)
        return claim.get("_lifecycle") if claim else None

    def get_claim_version(self, claim_id, version):
        item = next((item for item in self.versions.get(claim_id, []) if item["version"] == version), None)
        if not item:
            return None
        payload = item.get("payload", item.get("claim"))
        return {"claim": deepcopy(payload), "version": version, "version_fingerprint": item["fingerprint"]}

    def get_latest_validation(self, claim_id):
        run = next((row for row in reversed(self.validation_runs) if row["claim_id"] == claim_id and not row["informational"]), None)
        return deepcopy(run)

    def record_readonly_validation(self, claim_id, version, claim, result):
        return self.record_validation(claim_id, claim, result, informational=True)

    def mark_claim_stale(self, claim_id, reason):
        if self.statuses.get(claim_id) == "submitted":
            raise ValueError("Submitted claims are locked")
        self.statuses[claim_id] = "needs_revalidation"

    def create_correction_version(self, claim_id, reason=None):
        if self.statuses.get(claim_id) != "submitted":
            raise ValueError("A correction version can only be opened for a submitted claim")
        current = self.versions[claim_id][-1]
        payload = deepcopy(current.get("payload", current.get("claim")))
        version_number = current["version"] + 1
        event = self.append_ledger_event({"type": "claim_correction_started", "claim_id": claim_id,
                                          "from_version": current["version"], "version": version_number,
                                          "previous_version_fingerprint": current["fingerprint"],
                                          "version_fingerprint": current["fingerprint"]})
        self.versions[claim_id].append({"version": version_number, "payload": payload,
                                        "fingerprint": current["fingerprint"], "event_seq": event["seq"]})
        self.statuses[claim_id] = "needs_revalidation"
        return {"claim": payload, "version": version_number, "version_fingerprint": current["fingerprint"]}

    def record_submission(self, claim_id, claim, outcome, detail=None):
        from audit.chain import claim_fingerprint
        if self.statuses.get(claim_id) == "submitted":
            raise ValueError("Claim is already submitted and locked")
        current = self.versions[claim_id][-1]
        if claim_fingerprint(claim) != current["fingerprint"]:
            raise ValueError("Submission payload does not match the saved claim")
        if outcome in {"mocked", "accepted_by_openimis", "accepted", "paid"}:
            latest = self.get_latest_validation(claim_id)
            if not latest or latest["version"] != current["version"] or latest["error_count"] != 0:
                raise ValueError("The current claim version has not passed validation")
        event = self.append_ledger_event({"type": "submission", "claim_id": claim_id,
                                          "version": current["version"],
                                          "version_fingerprint": current["fingerprint"],
                                          "outcome": outcome, "detail": detail})
        if outcome in {"mocked", "accepted_by_openimis", "accepted", "paid"}:
            self.statuses[claim_id] = "submitted"
        return event

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
        if self.statuses.get(claim_id) == "submitted":
            raise ValueError("Submitted claims are locked")
        self.reviews[(claim_id, department)] = deepcopy(review)
        self.statuses[claim_id] = "needs_revalidation"
        return deepcopy(review)

    def list_outcomes(self, claim_id=None):
        return deepcopy([row for row in self.outcomes if claim_id is None or row["claimId"] == claim_id])

    def save_outcome(self, outcome):
        self.outcomes.append(deepcopy(outcome))
        self.append_ledger_event({"type": "claim_outcome_recorded", "claim_id": outcome["claimId"],
                                  "outcome": outcome["outcome"]})
        return deepcopy(outcome)
