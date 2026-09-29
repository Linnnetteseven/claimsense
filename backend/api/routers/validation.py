"""Validation of stored or ad hoc claims, and the audit chain."""

import logging

from fastapi import APIRouter

from api.deps import claims_repository, get_claim_or_404
from api.models import ClaimIn, Validation
from audit import chain
from services.pipeline import full_pipeline, record_run
from suggest.identity import RepositoryLookups

logger = logging.getLogger("hakiki.validation")
router = APIRouter(tags=["validation"])


@router.post("/claims/{claim_id}/validate", response_model=Validation)
def validate_claim(claim_id: str):
    """Full pipeline for a stored claim: rules, suggestions, explanations, FHIR ClaimResponse."""
    repository = claims_repository()
    claim = get_claim_or_404(claim_id, repository)
    result = full_pipeline(claim, RepositoryLookups(repository))
    record_run(repository, claim_id, result)
    logger.info("%s: score %d, %d errors, %d warnings", claim_id, result["score"],
                result["error_count"], result["warning_count"])
    return result


@router.post("/validate", response_model=Validation)
def validate_arbitrary(claim: ClaimIn):
    """Validate a claim sent in the body without saving it."""
    return full_pipeline(claim.as_claim())


@router.get("/claims/{claim_id}/audit")
def get_claim_audit(claim_id: str) -> dict:
    """Hash-chain history of one claim's validation runs (Upstash)."""
    return {"claim_id": claim_id, "history": chain.get_chain_for_claim(claim_id)}


@router.get("/audit/verify")
def verify_audit_chain() -> dict:
    """Recompute every hash in the ledger and confirm nothing was altered."""
    return chain.verify_chain()
