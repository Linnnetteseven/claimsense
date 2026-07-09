"""
ClaimSense — FastAPI backend.

Routes:
  GET  /                           health + mode check
  GET  /claims                     list all claims with pre-scored summaries
  GET  /claims/{id}                fetch one claim by ID
  POST /claims/{id}/validate       full pipeline: rules + Claude + FHIR ClaimResponse
  POST /claims/{id}/correct        apply edits + re-validate, save to session store
  POST /claims/{id}/submit         POST ClaimResponse to openIMIS (mock or live)
  POST /validate                   validate any arbitrary claim dict (for re-validation)
"""

import logging
from fastapi import Form, BackgroundTasks
from fastapi.responses import PlainTextResponse
from ussd.handler import handle_ussd_session
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from config import config
from data.mock_claims import MOCK_CLAIMS
from validation.engine import validate
from fhir.builder import build_claim_response
from fhir.client import openimis
from llm.explainer import explain_errors

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

# Session-scoped store for user corrections.
# Persists for the life of the server process (sufficient for a demo).
_session_corrections: dict[str, dict] = {}


def get_claim_or_404(claim_id: str) -> dict:
    """Look up a claim: corrected version first, then original mock data."""
    if claim_id in _session_corrections:
        return _session_corrections[claim_id]
    match = next((c for c in MOCK_CLAIMS if c["id"] == claim_id), None)
    if not match:
        raise HTTPException(status_code=404, detail=f"Claim '{claim_id}' not found")
    return match


def full_pipeline(claim: dict) -> dict:
    """
    The core validation pipeline used by multiple routes:
      1. Run all 7 validation rules
      2. Ask Claude to explain errors in plain English
      3. Build the FHIR R4 ClaimResponse resource
    Returns everything the frontend needs in one response.
    """
    result = validate(claim)
    result["explanations"] = explain_errors(result["errors"], claim)
    result["fhir_claim_response"] = build_claim_response(claim, result)
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
    if config.use_mock:
        source_claims = MOCK_CLAIMS
    else:
        try:
            source_claims = await openimis.get_claims_parsed()
            if not source_claims:
                logger.warning("openIMIS returned 0 claims — falling back to mock")
                source_claims = MOCK_CLAIMS
        except Exception as exc:
            logger.warning("openIMIS unreachable (%s) — falling back to mock", exc)
            source_claims = MOCK_CLAIMS

    # Apply in-session corrections
    claims = [_session_corrections.get(c["id"], c) for c in source_claims]

    # Score all claims
    scored = []
    for claim in claims:
        v = validate(claim)
        scored.append({
            **claim,
            "_preview": {
                "score": v["score"],
                "status": v["status"],
                "color": v["color"],
                "error_count": v["error_count"],
                "warning_count": v["warning_count"],
            },
        })

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
    return get_claim_or_404(claim_id)


@app.post("/claims/{claim_id}/validate")
async def validate_claim(claim_id: str):
    """Full validation pipeline for a claim fetched by ID."""
    claim = get_claim_or_404(claim_id)
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
    original = get_claim_or_404(claim_id)

    # Merge: original fields overridden by corrections
    updated = {**original, **corrections, "id": claim_id}
    _session_corrections[claim_id] = updated

    result = full_pipeline(updated)
    logger.info("Claim %s corrected — new score: %d", claim_id, result["score"])

    return {"claim": updated, "validation": result}


@app.post("/claims/{claim_id}/submit")
async def submit_claim(claim_id: str):
    """
    Submit the ClaimResponse to openIMIS.
    Blocked if there are any error-severity rule failures remaining.
    """
    claim = get_claim_or_404(claim_id)
    result = validate(claim)

    if result["error_count"] > 0:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Cannot submit — {result['error_count']} error(s) remain. "
                "Fix all errors first."
            ),
        )

    fhir_cr = build_claim_response(claim, result)

    if config.use_mock:
        logger.info("MOCK submit — would POST ClaimResponse for %s", claim_id)
        return {
            "submitted": True,
            "mode": "mock",
            "claim_id": claim_id,
            "score": result["score"],
            "fhir_claim_response": fhir_cr,
            "note": "Set OPENIMIS_TOKEN in .env to submit to the live instance.",
        }

    try:
        openimis_resp = await openimis.post_claim_response(fhir_cr)
        logger.info("openIMIS accepted ClaimResponse for %s", claim_id)
        return {
            "submitted": True,
            "mode": "live",
            "claim_id": claim_id,
            "score": result["score"],
            "openimis_response": openimis_resp,
            "fhir_claim_response": fhir_cr,
        }
    except Exception as exc:
        logger.error("openIMIS submission failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"openIMIS rejected the submission: {exc}")


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
