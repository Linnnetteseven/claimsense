"""Supabase data access for ClaimSense draft claims.

This module deliberately returns the pre-existing internal claim dictionaries.
Validation and FHIR layers therefore remain independent of Supabase.
"""

from typing import Any

from supabase import Client, create_client

from config import config
from data.mock_claims import resolve_date_tokens


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
        self._client = create_client(
            config.SUPABASE_URL,
            config.SUPABASE_SERVICE_ROLE_KEY,
        )

    _HANDOFFS = "claim_handoffs"

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
        return claim

    def list_claims(self) -> list[dict]:
        response = self._client.table(self._TABLE).select("claim_data, status").order(
            "claim_number"
        ).execute()
        return [claim for row in response.data or [] if (claim := self._claim_from_row(row))]

    def get_claim_by_id(self, claim_id: str) -> dict | None:
        response = self._client.table(self._TABLE).select("claim_data").eq(
            "id", claim_id
        ).limit(1).execute()
        return self._claim_from_row((response.data or [None])[0])

    def get_claim_by_number(self, claim_number: str) -> dict | None:
        response = self._client.table(self._TABLE).select("claim_data, status").eq(
            "claim_number", claim_number
        ).limit(1).execute()
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
        response = self._client.table(self._TABLE).update(
            {"claim_data": claim, "status": "draft"}
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
        self._client.table(self._HANDOFFS).delete().eq("claim_number", claim_number).execute()
        return self.update_claim(claim_number, resolve_date_tokens(row["seed_template"]))

    def reset_demo(self) -> dict[str, int]:
        """Delete UI-created claims and restore every seeded claim from its template."""
        self._client.table(self._HANDOFFS).delete().neq("claim_number", "").execute()
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

    def latest_handoff(self, claim_number: str) -> dict | None:
        response = self._client.table(self._HANDOFFS).select("*").eq(
            "claim_number", claim_number
        ).order("created_at", desc=True).limit(1).execute()
        return (response.data or [None])[0]

    def delete_claims(self, claim_numbers: list[str]) -> None:
        if claim_numbers:
            self._client.table(self._TABLE).delete().in_(
                "claim_number", claim_numbers
            ).execute()
