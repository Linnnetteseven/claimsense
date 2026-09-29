"""Shared dependencies for routers: the claims repository and claim lookup."""

import logging
from functools import lru_cache

from api.errors import ApiError
from repositories.claims import ClaimsRepository

logger = logging.getLogger("hakiki.deps")


@lru_cache(maxsize=1)
def _repository() -> ClaimsRepository:
    return ClaimsRepository()


def claims_repository() -> ClaimsRepository:
    """One Supabase client per process, reused across requests (no new TLS handshake per call)."""
    try:
        return _repository()
    except RuntimeError as exc:
        raise ApiError(503, str(exc), "database_not_configured") from exc


def get_claim_or_404(claim_id: str, repository: ClaimsRepository) -> dict:
    try:
        match = repository.get_claim_by_number(claim_id)
    except Exception as exc:
        logger.exception("Unable to read claim %s", claim_id)
        raise ApiError(502, "Unable to read the claim from the database") from exc
    if match is None:
        raise ApiError(404, f"Claim '{claim_id}' not found")
    return match
