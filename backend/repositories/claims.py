"""Supabase data access for Hakiki claims.

This module deliberately returns the pre-existing internal claim dictionaries.
Validation and FHIR layers therefore remain independent of Supabase.
"""

from datetime import datetime, timezone
from typing import Any

import httpx
from supabase import Client, create_client
from supabase.lib.client_options import SyncClientOptions

from config import config
from data.mock_claims import resolve_date_tokens


def _read(query):
    """Run a read query, retrying once if the connection times out (safe: reads change nothing)."""
    try:
        return query.execute()
    except (httpx.ConnectTimeout, httpx.ConnectError):
        return query.execute()


class ClaimsRepository:
    _TABLE = "claims"

    def __init__(self, client: Client | None = None) -> None:
        if client is not None:
            self._client = client
            return
        if not config.supabase_configured:
            raise RuntimeError(
                "Supabase is not configured. Set SUPABASE_URL and "
                "SUPABASE_SERVICE_ROLE_KEY in backend/.env."
            )
        # Short timeout: a stalled connection must not hold a request for minutes.
        self._client = create_client(
            config.SUPABASE_URL,
            config.SUPABASE_SERVICE_ROLE_KEY,
            options=SyncClientOptions(postgrest_client_timeout=10),
        )

    _HANDOFFS = "claim_handoffs"
    _RUNS = "validation_runs"
    _CORRECTIONS = "corrections"
    _HISTORY_TABLES = (_HANDOFFS, _RUNS, _CORRECTIONS)

    @staticmethod
    def _claim_from_row(row: dict[str, Any] | None) -> dict | None:
        if not row:
            return None
        claim = row.get("claim_data")
        if not isinstance(claim, dict):
            raise RuntimeError("Supabase claim row has invalid claim_data")
        if row.get("status"):
            # Workflow status for the UI; validation ignores underscore fields.
            claim = {**claim, "_status": row["status"]}
        if row.get("sha_state"):
            claim = {**claim, "_sha_state": row["sha_state"]}
        return claim

    def list_claims(self) -> list[dict]:
        response = _read(self._client.table(self._TABLE).select("claim_data, status, sha_state").order(
            "claim_number"
        ))
        return [claim for row in response.data or [] if (claim := self._claim_from_row(row))]

    def get_claim_by_id(self, claim_id: str) -> dict | None:
        response = self._client.table(self._TABLE).select("claim_data").eq(
            "id", claim_id
        ).limit(1).execute()
        return self._claim_from_row((response.data or [None])[0])

    def get_claim_by_number(self, claim_number: str) -> dict | None:
        response = _read(self._client.table(self._TABLE).select("claim_data, status, sha_state").eq(
            "claim_number", claim_number
        ).limit(1))
        return self._claim_from_row((response.data or [None])[0])

    def insert_claims(self, claims: list[dict]) -> list[dict]:
        """Insert new claims. Fails on a duplicate claim number rather than overwriting."""
        claims = [{k: v for k, v in c.items() if not k.startswith("_")} for c in claims]
        rows = [
            {
                "claim_number": claim["id"],
                "status": "draft",
                "claim_data": claim,
                # A reset returns a UI-created claim to the state it was created in.
                "seed_template": claim,
                "is_seed": False,
            }
            for claim in claims
        ]
        if not rows:
            return []
        response = self._client.table(self._TABLE).insert(rows).execute()
        return [claim for row in response.data or [] if (claim := self._claim_from_row(row))]

    def update_claim(self, claim_number: str, claim: dict) -> dict | None:
        """Save claim data. Any edit puts a handed-off claim back to draft."""
        if claim.get("id") != claim_number:
            raise ValueError("Claim id must match the claim number being updated")
        claim = {k: v for k, v in claim.items() if not k.startswith("_")}
        # A new edit starts a new cycle: SHA's previous answer no longer applies.
        response = self._client.table(self._TABLE).update(
            {"claim_data": claim, "status": "draft", "sha_state": None}
        ).eq("claim_number", claim_number).execute()
        return self._claim_from_row((response.data or [None])[0])

    def reset_claim(self, claim_number: str) -> dict | None:
        """Restore one claim from its seed template, with date tokens resolved to today."""
        response = self._client.table(self._TABLE).select("seed_template").eq(
            "claim_number", claim_number
        ).limit(1).execute()
        row = (response.data or [None])[0]
        if not row or not isinstance(row.get("seed_template"), dict):
            return None
        for table in self._HISTORY_TABLES:
            self._client.table(table).delete().eq("claim_number", claim_number).execute()
        return self.update_claim(claim_number, resolve_date_tokens(row["seed_template"]))

    def reset_demo(self) -> dict[str, int]:
        """Delete UI-created claims and restore every seeded claim from its template."""
        for table in self._HISTORY_TABLES:
            self._client.table(table).delete().neq("claim_number", "").execute()
        removed = self._client.table(self._TABLE).delete().eq("is_seed", False).execute()
        seeded = self._client.table(self._TABLE).select(
            "claim_number, seed_template"
        ).eq("is_seed", True).execute()
        rows = [
            {
                "claim_number": row["claim_number"],
                "status": "draft",
                "claim_data": resolve_date_tokens(row["seed_template"]),
            }
            for row in seeded.data or []
            if isinstance(row.get("seed_template"), dict)
        ]
        for start in range(0, len(rows), 100):
            self._client.table(self._TABLE).upsert(
                rows[start:start + 100], on_conflict="claim_number"
            ).execute()
        return {"restored": len(rows), "removed": len(removed.data or [])}

    def record_handoff(self, row: dict) -> dict:
        """Store the certified bundle and mark the claim handed off."""
        saved = self._client.table(self._HANDOFFS).insert(row).execute().data[0]
        self._client.table(self._TABLE).update({"status": "handed_off"}).eq(
            "claim_number", row["claim_number"]
        ).execute()
        return saved

    def record_sha_response(self, claim_number: str, state: dict, claim_response: dict) -> bool:
        """Attach SHA's answer to the latest hand-off and show its state on the claim."""
        latest = self.latest_handoff(claim_number)
        if latest is None:
            return False
        self._client.table(self._HANDOFFS).update(
            {"sha_response": claim_response, "sha_response_at": datetime.now(timezone.utc).isoformat()}
        ).eq("id", latest["id"]).execute()
        self._client.table(self._TABLE).update({"sha_state": state}).eq("claim_number", claim_number).execute()
        return True

    def latest_handoff(self, claim_number: str) -> dict | None:
        response = self._client.table(self._HANDOFFS).select("*").eq(
            "claim_number", claim_number
        ).order("created_at", desc=True).limit(1).execute()
        return (response.data or [None])[0]

    def record_validation_run(self, claim_number: str, result: dict) -> None:
        self._client.table(self._RUNS).insert({
            "claim_number": claim_number,
            "score": result["score"],
            "rule_version": result["ruleset_version"],
            "error_count": result["error_count"],
            "warning_count": result["warning_count"],
            "ai_explanations_used": bool(result.get("ai_explanations_used")),
            "results": [
                {k: r.get(k) for k in ("rule_id", "passed", "severity", "rule_version", "message")}
                for r in result["results"]
            ],
        }).execute()

    def record_corrections(self, claim_number: str, before: dict, after: dict, source: str = "manual") -> int:
        """One row per field whose value changed. Returns the number recorded."""
        rows = [
            {"claim_number": claim_number, "field": field, "old_value": before.get(field),
             "new_value": after.get(field), "source": source[:200]}
            for field in sorted(set(before) | set(after))
            if not field.startswith("_") and field != "id" and before.get(field) != after.get(field)
        ]
        if rows:
            self._client.table(self._CORRECTIONS).insert(rows).execute()
        return len(rows)

    def history(self, claim_number: str, limit: int = 50) -> dict:
        runs = self._client.table(self._RUNS).select(
            "score, rule_version, error_count, warning_count, ai_explanations_used, created_at"
        ).eq("claim_number", claim_number).order("created_at", desc=True).limit(limit).execute()
        corrections = self._client.table(self._CORRECTIONS).select(
            "field, old_value, new_value, source, created_at"
        ).eq("claim_number", claim_number).order("created_at", desc=True).limit(limit).execute()
        return {"validation_runs": runs.data or [], "corrections": corrections.data or []}

    def ping(self) -> None:
        """Cheap query to confirm Supabase is reachable."""
        self._client.table(self._TABLE).select("claim_number").limit(1).execute()

    def find_patient_ids(self, name: str, dob: str, exclude: str = "") -> list[dict]:
        """SHA numbers on other claims for the same patient name and date of birth."""
        if not name or not dob:
            return []
        response = self._client.table(self._TABLE).select("claim_number, claim_data").ilike(
            "claim_data->>patient_name", name.strip()
        ).eq("claim_data->>dob", dob.strip()).limit(20).execute()
        found = {}
        for row in response.data or []:
            data = row.get("claim_data") or {}
            pid = str(data.get("patient_id") or "").strip()
            if pid and row["claim_number"] != exclude:
                found.setdefault(pid, {"patient_id": pid, "claim_number": row["claim_number"],
                                       "facility_name": data.get("facility_name", "")})
        return list(found.values())

    def facility_practitioners(self, facility_code: str) -> list[dict]:
        """Practitioners (registry number and name) seen on claims from this facility."""
        if not facility_code:
            return []
        response = self._client.table(self._TABLE).select("claim_data").eq(
            "claim_data->>facility_code", facility_code.strip()
        ).limit(500).execute()
        roster = {}
        for row in response.data or []:
            data = row.get("claim_data") or {}
            pid = str(data.get("practitioner_id") or "").strip()
            if pid:
                roster.setdefault(pid, {"practitioner_id": pid, "practitioner_name": data.get("practitioner_name", "")})
        return sorted(roster.values(), key=lambda p: p["practitioner_name"])

    def delete_claims(self, claim_numbers: list[str]) -> None:
        if claim_numbers:
            self._client.table(self._TABLE).delete().in_(
                "claim_number", claim_numbers
            ).execute()
