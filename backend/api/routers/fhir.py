"""SHA eClaims bundle and the hand-off to the hospital HIS."""

import logging

import anyio
from fastapi import APIRouter

from api.deps import claims_repository, get_claim_or_404
from api.errors import ApiError
from api.models import BundleResult, HandoffRequest, HandoffResult
from config import config
from fhir.builder import build_claim_response
from his import handoff as his_handoff
from services.pipeline import bundle_with_checks
from validation.engine import validate

logger = logging.getLogger("hakiki.fhir")
router = APIRouter(tags=["fhir"])


@router.get("/claims/{claim_id}/bundle", response_model=BundleResult)
def get_claim_bundle(claim_id: str):
    """The SHA eClaims Bundle this claim would produce, with pre-submission checks."""
    return bundle_with_checks(get_claim_or_404(claim_id, claims_repository()))


@router.post("/claims/{claim_id}/handoff", response_model=HandoffResult)
@router.post("/claims/{claim_id}/submit", response_model=HandoffResult, include_in_schema=False)  # older clients
def handoff_claim(claim_id: str, body: HandoffRequest | None = None):
    """
    Hand a validated claim back to the hospital HIS, which submits it to SHA.
    Blocked while errors remain or the bundle fails its checks; warnings must be
    acknowledged. The certified bundle is stored, then delivered per HIS_DELIVERY.
    """
    repository = claims_repository()
    claim = get_claim_or_404(claim_id, repository)
    result = validate(claim)

    if result["error_count"] > 0:
        raise ApiError(400, f"Cannot hand off: {result['error_count']} error(s) remain. Fix all errors first.",
                       "errors_remain")
    if result["warning_count"] > 0 and not (body and body.acknowledge_warnings):
        raise ApiError(409, f"{result['warning_count']} warning(s) need review. Confirm you have reviewed them "
                       "to hand off.", "warnings_not_acknowledged",
                       [w["rule_id"] for w in result["warnings"]])

    sha_bundle = bundle_with_checks(claim)
    if not sha_bundle["checks_passed"]:
        raise ApiError(400, "Cannot hand off: the SHA bundle failed its checks", "bundle_checks_failed",
                       sha_bundle["issues"])

    # Delivery is async (httpx); this route runs in a worker thread.
    delivery_status, delivery_response = anyio.from_thread.run(
        his_handoff.deliver, claim, sha_bundle["bundle"], build_claim_response(claim, result)
    )
    try:
        record = repository.record_handoff({
            "claim_number": claim_id,
            "bundle": sha_bundle["bundle"],
            "score": result["score"],
            "ruleset_version": result["ruleset_version"],
            "warnings": [w["rule_id"] for w in result["warnings"]],
            "delivery": config.HIS_DELIVERY,
            "delivery_status": delivery_status,
            "delivery_response": delivery_response,
        })
    except Exception as exc:
        logger.exception("Unable to record hand-off for %s", claim_id)
        raise ApiError(502, "Unable to record the hand-off") from exc

    logger.info("Claim %s handed off to HIS (%s: %s)", claim_id, config.HIS_DELIVERY, delivery_status)
    return {
        "handed_off": delivery_status != "failed",
        "claim_id": claim_id,
        "handoff_id": str(record["id"]),
        "created_at": str(record["created_at"]),
        "score": result["score"],
        "ruleset_version": result["ruleset_version"],
        "warnings_acknowledged": [w["rule_id"] for w in result["warnings"]],
        "delivery": config.HIS_DELIVERY,
        "delivery_status": delivery_status,
        "delivery_response": delivery_response,
        "sha_bundle": sha_bundle["bundle"],
    }


@router.get("/claims/{claim_id}/handoff")
def get_handoff(claim_id: str) -> dict:
    """Latest hand-off for a claim, including the certified bundle. The HIS pulls from here."""
    try:
        record = claims_repository().latest_handoff(claim_id)
    except ApiError:
        raise
    except Exception as exc:
        raise ApiError(502, "Unable to read the hand-off") from exc
    if record is None:
        raise ApiError(404, f"Claim '{claim_id}' has not been handed off")
    return record
