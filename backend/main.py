"""
ClaimSense — FastAPI backend.

Routes:
  GET  /                           health + mode check
  GET  /claims                     list all claims with pre-scored summaries
  GET  /claims/{id}                fetch one claim by ID
  POST /claims/{id}/validate       full pipeline: rules + Gemini + FHIR ClaimResponse + audit
  POST /claims/{id}/correct        apply edits + re-validate, save to session store
  POST /claims/{id}/handoff        hand the validated SHA bundle to the hospital HIS (/submit alias)
  GET  /claims/{id}/handoff        latest hand-off and its certified bundle
  POST /validate                   validate any arbitrary claim dict (for re-validation)
  GET  /claims/{id}/audit          hash-chain audit history for one claim
  GET  /claims/{id}/bundle         Kenya eClaims submission Bundle + structural checks
  POST /claims/{id}/reset          demo: restore one claim to its seeded state
  POST /demo/reset                 demo: restore all seeded claims, drop UI-created ones
  GET  /audit/verify               recompute and verify the audit chain
"""
from dotenv import load_dotenv
load_dotenv()


import logging
import secrets
from datetime import date
from fastapi import Form, BackgroundTasks
from fastapi.responses import PlainTextResponse
from ussd.handler import handle_ussd_session
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from config import config
from validation.engine import validate
from fhir.builder import build_claim_response
from fhir.bundle_checks import check_bundle
from fhir.kenya_bundle_builder import build_kenya_eclaims_bundle
from his import handoff as his_handoff
from llm.explainer import explain_errors
from repositories.claims import ClaimsRepository
from audit import chain

logging.basicConfig(
    level=logging.DEBUG if config.DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("claimsense.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 50)
    logger.info("ClaimSense starting")
    logger.info("openIMIS: %s", config.OPENIMIS_URL)
    logger.info("Mode: %s", "MOCK" if config.use_mock else "LIVE")
    logger.info("LLM: %s", "enabled" if config.llm_enabled else "disabled — set GEMINI_API_KEY")
    logger.info("=" * 50)
    yield


app = FastAPI(
    title="ClaimSense API",
    description="Pre-submission SHA claims validation — openIMIS Hackathon Track 3",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def claims_repository() -> ClaimsRepository:
    """Create the backend-only Supabase repository on demand."""
    try:
        return ClaimsRepository()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def get_claim_or_404(claim_id: str, repository: ClaimsRepository) -> dict:
    """Look up the current draft claim by its stable business identifier."""
    match = repository.get_claim_by_number(claim_id)
    if match is None:
        raise HTTPException(status_code=404, detail=f"Claim '{claim_id}' not found")
    return match


def _preview(result: dict) -> dict:
    """The score summary shown in the claims queue."""
    return {
        key: result[key]
        for key in ("score", "status", "color", "error_count", "warning_count")
    }


def full_pipeline(claim: dict) -> dict:
    """
    The core validation pipeline used by multiple routes:
      1. Run the deterministic validation rules
      2. Ask Gemini to explain errors in plain English
      3. Build the FHIR R4 ClaimResponse resource
      4. Record the result in the tamper-evident audit trail
    Returns everything the frontend needs in one response.
    """
    result = validate(claim)
    explanations, ai_used = explain_errors(result["errors"], claim)
    result["explanations"] = explanations
    result["ai_explanations_used"] = ai_used
    result["fhir_claim_response"] = build_claim_response(claim, result)
    try:
        chain.record_validation(claim.get("id"), result)
    except Exception:
        # The audit trail is optional; never fail validation over it.
        logger.exception("Audit chain write failed for %s", claim.get("id"))
    return result


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/")
async def health_check():
    return {
        "service": "ClaimSense",
        "status": "running",
        "mode": "mock" if config.use_mock else "live",
        "llm": "enabled" if config.llm_enabled else "disabled",
        "openimis_url": config.OPENIMIS_URL,
    }


@app.get("/claims/{claim_id}/audit")
async def get_claim_audit(claim_id: str):
    """Full hash-chain history for one claim's validation runs."""
    return {"claim_id": claim_id, "history": chain.get_chain_for_claim(claim_id)}


@app.get("/audit/verify")
async def verify_audit_chain():
    """Recomputes every hash in the ledger and confirms nothing was altered."""
    return chain.verify_chain()


@app.get("/claims")
async def list_claims(
    q: str = "",
    status: str = "all",
    page: int = 1,
    page_size: int = 20,
):
    """
    Returns claims with pre-scores. Supports:
      q         — search by patient name or claim ID (case-insensitive)
      status    — all | ready | review | error
      page      — page number (1-based)
      page_size — claims per page (default 20)
    """
    repository = claims_repository()
    try:
        claims = repository.list_claims()
    except Exception as exc:
        logger.exception("Unable to retrieve Supabase draft claims")
        raise HTTPException(status_code=502, detail="Unable to retrieve draft claims") from exc

    # Score all claims
    scored = [{**claim, "_preview": _preview(validate(claim))} for claim in claims]

    # Filter by status
    if status == "ready":
        scored = [c for c in scored if c["_preview"]["color"] == "green"]
    elif status == "review":
        scored = [c for c in scored if c["_preview"]["color"] == "amber"]
    elif status == "error":
        scored = [c for c in scored if c["_preview"]["color"] == "red"]

    # Search by patient name or claim ID
    if q.strip():
        q_lower = q.strip().lower()
        scored = [
            c for c in scored
            if q_lower in c.get("patient_name", "").lower()
            or q_lower in c.get("id", "").lower()
            or q_lower in c.get("facility_name", "").lower()
        ]

    # Pagination
    total = len(scored)
    start = (page - 1) * page_size
    end = start + page_size
    page_claims = scored[start:end]

    return {
        "count": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, -(-total // page_size)),  # ceiling division
        "claims": page_claims,
    }


@app.get("/claims/{claim_id}")
async def get_claim(claim_id: str):
    return get_claim_or_404(claim_id, claims_repository())


@app.post("/claims")
async def create_claim(claim: dict):
    """Persist one new draft claim using the existing internal claim shape."""
    if not claim:
        raise HTTPException(status_code=400, detail="Request body must be a claim dict")
    if not claim.get("id"):
        claim = {**claim, "id": f"SHA-CLM-{date.today():%Y%m%d}-{secrets.token_hex(3).upper()}"}
    repository = claims_repository()
    if repository.get_claim_by_number(claim["id"]) is not None:
        raise HTTPException(status_code=409, detail=f"Claim '{claim['id']}' already exists")
    try:
        saved = repository.insert_claims([claim])[0]
    except Exception as exc:
        logger.exception("Unable to create Supabase draft claim")
        raise HTTPException(status_code=502, detail="Unable to create draft claim") from exc
    return {"claim": saved, "_preview": _preview(validate(saved))}


@app.post("/claims/{claim_id}/validate")
async def validate_claim(claim_id: str):
    """Full validation pipeline for a claim fetched by ID."""
    claim = get_claim_or_404(claim_id, claims_repository())
    logger.info("Validating %s", claim_id)
    result = full_pipeline(claim)
    logger.info(
        "%s — score: %d, errors: %d, warnings: %d",
        claim_id,
        result["score"],
        result["error_count"],
        result["warning_count"],
    )
    return result


@app.post("/validate")
async def validate_arbitrary(claim: dict):
    """
    Validate any claim dict sent in the request body.
    Used by the correction form to re-validate without committing the save.
    """
    if not claim:
        raise HTTPException(status_code=400, detail="Request body must be a claim dict")
    result = full_pipeline(claim)
    return result


@app.post("/claims/{claim_id}/correct")
async def correct_claim(claim_id: str, corrections: dict):
    """
    Merge corrections into the claim, save to the session store, re-validate.
    The frontend sends the full corrected claim dict in the body.
    """
    repository = claims_repository()
    original = get_claim_or_404(claim_id, repository)

    # Merge: original fields overridden by corrections. The id is never editable.
    updated = {**original, **corrections, "id": claim_id}
    try:
        saved = repository.update_claim(claim_id, updated)
    except Exception as exc:
        logger.exception("Unable to update Supabase draft claim %s", claim_id)
        raise HTTPException(status_code=502, detail="Unable to update draft claim") from exc
    if saved is None:
        raise HTTPException(status_code=404, detail=f"Claim '{claim_id}' not found")

    result = full_pipeline(saved)
    logger.info("Claim %s corrected — new score: %d", claim_id, result["score"])

    return {"claim": saved, "validation": result}


def _bundle_with_checks(claim: dict) -> dict:
    bundle = build_kenya_eclaims_bundle(claim)
    issues = check_bundle(bundle)
    return {
        "bundle": bundle,
        "checks_passed": not issues,
        "issues": [{"check_id": i.check_id, "message": i.message, "fields": i.fields} for i in issues],
    }


@app.get("/claims/{claim_id}/bundle")
async def get_claim_bundle(claim_id: str):
    """The SHA eClaims submission Bundle this claim would produce, with pre-submission checks."""
    return _bundle_with_checks(get_claim_or_404(claim_id, claims_repository()))


def _require_demo_reset() -> None:
    if not config.DEMO_RESET_ENABLED:
        raise HTTPException(status_code=403, detail="Demo reset is disabled on this deployment")


@app.post("/claims/{claim_id}/reset")
async def reset_claim(claim_id: str):
    """Demo only: restore one claim to its seeded (or originally created) state."""
    _require_demo_reset()
    repository = claims_repository()
    try:
        restored = repository.reset_claim(claim_id)
    except Exception as exc:
        logger.exception("Unable to reset claim %s", claim_id)
        raise HTTPException(status_code=502, detail="Unable to reset claim") from exc
    if restored is None:
        raise HTTPException(status_code=404, detail=f"Claim '{claim_id}' has no saved original to restore")
    return {"claim": restored, "_preview": _preview(validate(restored))}


@app.post("/demo/reset")
async def reset_demo():
    """Demo only: restore every seeded claim and delete claims added through the UI."""
    _require_demo_reset()
    try:
        counts = claims_repository().reset_demo()
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Demo reset failed")
        raise HTTPException(status_code=502, detail="Demo reset failed") from exc
    logger.info("Demo reset: %s", counts)
    return counts


@app.post("/claims/{claim_id}/handoff")
@app.post("/claims/{claim_id}/submit")  # older clients
async def handoff_claim(claim_id: str, body: dict | None = None):
    """
    Hand a validated claim back to the hospital HIS, which submits it to SHA.

    Blocked while any error remains. Warnings must be acknowledged
    ({"acknowledge_warnings": true}). The certified bundle is stored with its
    score and ruleset version, then delivered per HIS_DELIVERY.
    """
    repository = claims_repository()
    claim = get_claim_or_404(claim_id, repository)
    result = validate(claim)

    if result["error_count"] > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot hand off: {result['error_count']} error(s) remain. Fix all errors first.",
        )
    if result["warning_count"] > 0 and not (body or {}).get("acknowledge_warnings"):
        raise HTTPException(
            status_code=409,
            detail=f"{result['warning_count']} warning(s) need review. Confirm you have reviewed them to hand off.",
        )

    sha_bundle = _bundle_with_checks(claim)
    if not sha_bundle["checks_passed"]:
        raise HTTPException(
            status_code=400,
            detail="Cannot hand off: the SHA bundle failed checks: "
            + "; ".join(i["message"] for i in sha_bundle["issues"]),
        )

    delivery_status, delivery_response = await his_handoff.deliver(
        claim, sha_bundle["bundle"], build_claim_response(claim, result)
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
        raise HTTPException(status_code=502, detail="Unable to record the hand-off") from exc

    logger.info("Claim %s handed off to HIS (%s: %s)", claim_id, config.HIS_DELIVERY, delivery_status)
    return {
        "handed_off": delivery_status != "failed",
        "claim_id": claim_id,
        "handoff_id": record["id"],
        "created_at": record["created_at"],
        "score": result["score"],
        "ruleset_version": result["ruleset_version"],
        "warnings_acknowledged": [w["rule_id"] for w in result["warnings"]],
        "delivery": config.HIS_DELIVERY,
        "delivery_status": delivery_status,
        "delivery_response": delivery_response,
        "sha_bundle": sha_bundle["bundle"],
    }


@app.get("/claims/{claim_id}/handoff")
async def get_handoff(claim_id: str):
    """Latest hand-off for a claim, including the certified bundle. The HIS pulls from here."""
    record = claims_repository().latest_handoff(claim_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Claim '{claim_id}' has not been handed off")
    return record


# ---------------------------------------------------------------------------
# Africa's Talking USSD + SMS Routes
# ---------------------------------------------------------------------------

@app.post("/ussd", response_class=PlainTextResponse)
async def ussd_callback(
    background_tasks: BackgroundTasks,
    sessionId: str = Form(...),
    phoneNumber: str = Form(...),
    networkCode: str = Form(default=""),
    serviceCode: str = Form(default=""),
    text: str = Form(default=""),
):
    """
    Africa's Talking USSD callback.

    AT sends application/x-www-form-urlencoded POST on every user input.
    We respond with plain text: 'CON <msg>' to continue or 'END <msg>' to close.
    Registered as callback URL in the AT dashboard under USSD settings.
    """
    logger.info(
        "USSD | session=%s phone=%s text=%r",
        sessionId,
        phoneNumber,
        text,
    )

    response = handle_ussd_session(
        session_id=sessionId,
        phone_number=phoneNumber,
        text=text,
        background_tasks=background_tasks,
    )

    logger.info("USSD response: %r", response[:60])
    return response
