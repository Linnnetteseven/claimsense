"""Supabase data access for ClaimSense draft claims.

This module deliberately returns the pre-existing internal claim dictionaries.
Validation and FHIR layers therefore remain independent of Supabase.
"""

from typing import Any

from supabase import Client, create_client

from config import config


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

    @staticmethod
    def _claim_from_row(row: dict[str, Any] | None) -> dict | None:
        if not row:
            return None
        claim = row.get("claim_data")
        if not isinstance(claim, dict):
            raise RuntimeError("Supabase claim row has invalid claim_data")
        return claim

    def list_claims(self) -> list[dict]:
        response = self._client.table(self._TABLE).select("claim_data").order(
            "claim_number"
        ).execute()
        return [claim for row in response.data or [] if (claim := self._claim_from_row(row))]

    def get_claim_by_id(self, claim_id: str) -> dict | None:
        response = self._client.table(self._TABLE).select("claim_data").eq(
            "id", claim_id
        ).limit(1).execute()
        return self._claim_from_row((response.data or [None])[0])

    def get_claim_by_number(self, claim_number: str) -> dict | None:
        response = self._client.table(self._TABLE).select("claim_data").eq(
            "claim_number", claim_number
        ).limit(1).execute()
        return self._claim_from_row((response.data or [None])[0])

    def insert_claims(self, claims: list[dict]) -> list[dict]:
        rows = [
            {"claim_number": claim["id"], "status": "draft", "claim_data": claim}
            for claim in claims
        ]
        if not rows:
            return []
        response = self._client.table(self._TABLE).upsert(
            rows, on_conflict="claim_number"
        ).execute()
        return [claim for row in response.data or [] if (claim := self._claim_from_row(row))]

    def update_claim(self, claim_number: str, claim: dict) -> dict | None:
        if claim.get("id") != claim_number:
            raise ValueError("Claim id must match the claim number being updated")
        response = self._client.table(self._TABLE).update(
            {"claim_data": claim, "status": "draft"}
        ).eq("claim_number", claim_number).execute()
        return self._claim_from_row((response.data or [None])[0])

    def delete_claims(self, claim_numbers: list[str]) -> None:
        if claim_numbers:
            self._client.table(self._TABLE).delete().in_(
                "claim_number", claim_numbers
            ).execute()
