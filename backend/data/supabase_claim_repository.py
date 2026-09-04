from typing import Optional

from supabase import create_client, Client

from config import config


class SupabaseClaimRepository:
    """
    Repository for draft claims stored in Supabase.

    Supabase schema:

        claims
        ├── id
        ├── claim_number
        ├── status
        ├── claim_data
        ├── created_at
        └── updated_at

    claim_data contains the actual ClaimSense claim payload.
    """

    def __init__(self):
        if not config.SUPABASE_URL:
            raise RuntimeError("SUPABASE_URL is not configured")

        if not config.SUPABASE_SERVICE_ROLE_KEY:
            raise RuntimeError(
                "SUPABASE_SERVICE_ROLE_KEY is not configured"
            )

        self.client: Client = create_client(
            config.SUPABASE_URL,
            config.SUPABASE_SERVICE_ROLE_KEY,
        )

    def list_claims(self, status: Optional[str] = None) -> list[dict]:
        """
        Return claims from Supabase.

        The returned objects contain the database metadata plus the
        actual claim fields at the top level so the validation engine
        can consume them directly.
        """

        query = (
            self.client
            .table("claims")
            .select("*")
            .order("created_at", desc=False)
        )

        if status:
            query = query.eq("status", status)

        response = query.execute()

        claims = []

        for row in response.data or []:
            claim_data = row.get("claim_data") or {}

            claim = {
                **claim_data,
                "_db_id": row.get("id"),
                "_claim_number": row.get("claim_number"),
                "_db_status": row.get("status"),
                "_created_at": row.get("created_at"),
                "_updated_at": row.get("updated_at"),
            }

            claims.append(claim)

        return claims

    def get_claim(self, claim_id: str) -> Optional[dict]:
        """
        Fetch one claim by Supabase row ID.
        """

        response = (
            self.client
            .table("claims")
            .select("*")
            .eq("id", claim_id)
            .limit(1)
            .execute()
        )

        if not response.data:
            return None

        row = response.data[0]
        claim_data = row.get("claim_data") or {}

        return {
            **claim_data,
            "_db_id": row.get("id"),
            "_claim_number": row.get("claim_number"),
            "_db_status": row.get("status"),
            "_created_at": row.get("created_at"),
            "_updated_at": row.get("updated_at"),
        }

    def update_claim(
        self,
        claim_id: str,
        claim: dict,
    ) -> dict:
        """
        Update the claim_data JSON stored in Supabase.
        """

        response = (
            self.client
            .table("claims")
            .update({
                "claim_data": claim,
            })
            .eq("id", claim_id)
            .execute()
        )

        if not response.data:
            raise RuntimeError(
                f"Claim {claim_id} was not updated"
            )

        return response.data[0]


_repository = None


def get_supabase_repository():
    global _repository

    if _repository is None:
        _repository = SupabaseClaimRepository()

    return _repository
