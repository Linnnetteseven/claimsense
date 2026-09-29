"""Claims: list, read, create, correct, history, and demo resets."""

import logging
import secrets
from datetime import date

from fastapi import APIRouter

from api.deps import claims_repository, get_claim_or_404
from api.errors import ApiError
from api.models import ClaimIn, ClaimList, ClaimWithPreview, CorrectionResult, History, ResetCounts
from config import config
from services.pipeline import full_pipeline, preview, record_run
from suggest.identity import RepositoryLookups
from validation.engine import validate

logger = logging.getLogger("hakiki.claims")
router = APIRouter(tags=["claims"])


@router.get("/claims", response_model=ClaimList)
def list_claims(q: str = "", status: str = "all", page: int = 1, page_size: int = 20):
    """
    Claims with pre-scores.
      q          search patient name, claim ID or facility (case-insensitive)
      status     all | ready | review | error
      page       1-based
      page_size  claims per page
    """
    try:
        claims = claims_repository().list_claims()
    except ApiError:
        raise
    except Exception as exc:
        logger.exception("Unable to list claims")
        raise ApiError(502, "Unable to retrieve claims from the database") from exc

    scored = [{**claim, "_preview": preview(validate(claim))} for claim in claims]
    colors = {"ready": "green", "review": "amber", "error": "red"}
    if status in colors:
        scored = [c for c in scored if c["_preview"]["color"] == colors[status]]
    if q.strip():
        needle = q.strip().lower()
        scored = [
            c for c in scored
            if needle in str(c.get("patient_name", "")).lower()
            or needle in str(c.get("id", "")).lower()
            or needle in str(c.get("facility_name", "")).lower()
        ]

    page, page_size = max(1, page), max(1, page_size)
    total = len(scored)
    start = (page - 1) * page_size
    return {
        "count": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, -(-total // page_size)),
        "claims": scored[start:start + page_size],
    }


@router.get("/claims/{claim_id}")
def get_claim(claim_id: str) -> dict:
    return get_claim_or_404(claim_id, claims_repository())


@router.post("/claims", response_model=ClaimWithPreview, response_model_by_alias=True)
def create_claim(body: ClaimIn):
    """Create a draft claim. An ID is generated when none is sent."""
    claim = body.as_claim()
    if not claim.get("id"):
        claim["id"] = f"SHA-CLM-{date.today():%Y%m%d}-{secrets.token_hex(3).upper()}"
    repository = claims_repository()
    if get_existing(repository, claim["id"]) is not None:
        raise ApiError(409, f"Claim '{claim['id']}' already exists")
    try:
        saved = repository.insert_claims([claim])[0]
    except Exception as exc:
        logger.exception("Unable to create claim")
        raise ApiError(502, "Unable to create the claim") from exc
    return {"claim": saved, "preview": preview(validate(saved))}


def get_existing(repository, claim_id: str):
    try:
        return repository.get_claim_by_number(claim_id)
    except Exception as exc:
        raise ApiError(502, "Unable to read the claim from the database") from exc


@router.post("/claims/{claim_id}/correct", response_model=CorrectionResult)
def correct_claim(claim_id: str, corrections: ClaimIn, source: str = "manual"):
    """
    Merge corrections into the claim, save, and re-validate the whole claim.
    source: "manual" or the suggestion applied; kept in the corrections history.
    """
    repository = claims_repository()
    original = get_claim_or_404(claim_id, repository)
    updated = {**original, **corrections.as_claim(), "id": claim_id}  # the id is never editable
    try:
        saved = repository.update_claim(claim_id, updated)
    except Exception as exc:
        logger.exception("Unable to update claim %s", claim_id)
        raise ApiError(502, "Unable to save the corrections") from exc
    if saved is None:
        raise ApiError(404, f"Claim '{claim_id}' not found")

    try:
        repository.record_corrections(claim_id, original, saved, source)
    except Exception:
        logger.exception("Unable to record corrections for %s", claim_id)
    result = full_pipeline(saved, RepositoryLookups(repository))
    record_run(repository, claim_id, result)
    logger.info("Claim %s corrected, new score %d", claim_id, result["score"])
    return {"claim": saved, "validation": result}


@router.get("/claims/{claim_id}/history", response_model=History)
def get_claim_history(claim_id: str):
    """Validation runs and field corrections for a claim, newest first."""
    repository = claims_repository()
    get_claim_or_404(claim_id, repository)
    return {"claim_id": claim_id, **repository.history(claim_id)}


def _require_demo_reset() -> None:
    if not config.DEMO_RESET_ENABLED:
        raise ApiError(403, "Demo reset is disabled on this deployment", "demo_reset_disabled")


@router.post("/claims/{claim_id}/reset", response_model=ClaimWithPreview, response_model_by_alias=True)
def reset_claim(claim_id: str):
    """Demo only: restore one claim to its seeded (or originally created) state."""
    _require_demo_reset()
    try:
        restored = claims_repository().reset_claim(claim_id)
    except ApiError:
        raise
    except Exception as exc:
        logger.exception("Unable to reset claim %s", claim_id)
        raise ApiError(502, "Unable to reset the claim") from exc
    if restored is None:
        raise ApiError(404, f"Claim '{claim_id}' has no saved original to restore")
    return {"claim": restored, "preview": preview(validate(restored))}


@router.post("/demo/reset", response_model=ResetCounts)
def reset_demo():
    """Demo only: restore every seeded claim and delete claims added through the UI."""
    _require_demo_reset()
    try:
        counts = claims_repository().reset_demo()
    except ApiError:
        raise
    except Exception as exc:
        logger.exception("Demo reset failed")
        raise ApiError(502, "Demo reset failed") from exc
    logger.info("Demo reset: %s", counts)
    return counts
