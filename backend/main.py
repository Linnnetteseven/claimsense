"""
ClaimSense — FastAPI backend.

Routes:
  GET  /                           health + mode check
  GET  /claims                     list all claims with pre-scored summaries
  GET  /claims/{id}                fetch one claim by ID
  POST /claims/{id}/validate       full pipeline: rules + Gemini + FHIR ClaimResponse + audit event
  POST /claims/{id}/correct        apply edits + re-validate, save to session store
  POST /claims/{id}/submit         POST ClaimResponse to openIMIS (mock or live)
  POST /validate                   validate any arbitrary claim dict (for re-validation)
"""
from dotenv import load_dotenv
load_dotenv()


import logging
from fastapi import Form, BackgroundTasks, Header
from fastapi.responses import PlainTextResponse, FileResponse
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
from audit import chain, anchor
from db.factory import get_repository, is_oracle_active, configured_backend
from db.connection import connection_mode as oracle_connection_mode
from db.analytics import VIEW_QUERIES
from evidence.packs import store_evidence_pack
import os
import hmac
import re
import traceback
from pathlib import Path

logging.basicConfig(
    level=logging.DEBUG if config.DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("claimsense.main")


def _storage_unavailable(exc: Exception, detail: str) -> HTTPException:
    logger.warning("Storage operation failed (%s)", type(exc).__name__)
    return HTTPException(status_code=503, detail=detail)


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
    allow_origins=list(dict.fromkeys(config.ALLOWED_ORIGINS + ([config.DEPLOYED_FRONTEND_URL] if config.DEPLOYED_FRONTEND_URL else []))),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health/db")
async def database_health():
    """Report selected storage mode and connectivity without exposing configuration."""
    repository = get_repository()
    try:
        connected = bool(repository.health())
    except Exception as exc:
        logger.warning("Database health check failed (%s)", type(exc).__name__)
        connected = False
    active = getattr(repository, "active_backend", repository.backend_name)
    if active == "redis":
        from audit.chain import _audit_enabled
        durable = _audit_enabled()
    else:
        durable = active == "oracle"
    return {
        "configured_backend": configured_backend(),
        "active_backend": active,
        "connection_mode": active if active == "redis" else oracle_connection_mode(),
        "connected": connected,
        "durable": durable,
    }


def _analytics_repository():
    repository = get_repository()
    if not is_oracle_active(repository):
        raise HTTPException(status_code=503, detail="Analytics requires Oracle backend")
    return repository


@app.get("/analytics/overview")
async def get_management_analytics():
    """Return aggregate metrics from Oracle views; no claim-level data is selected."""
    repository = _analytics_repository()
    try:
        kpis = repository.fetch_analytics_view("management_kpis")
        return {
            "available": True,
            "kpis": kpis[0] if kpis else {},
            "claims_by_status": repository.fetch_analytics_view("claims_by_status"),
            "score_by_department": repository.fetch_analytics_view("score_by_department"),
            "top_failed_rules": repository.fetch_analytics_view("top_failed_rules"),
            "rework_trend_weekly": repository.fetch_analytics_view("rework_trend_weekly"),
            "ledger_status": (repository.fetch_analytics_view("ledger_status") or [{}])[0],
            "signoff_progress": repository.fetch_analytics_view("signoff_progress"),
        }
    except Exception as exc:
        logger.warning("Analytics views unavailable (%s)", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Analytics views are unavailable; apply backend/db/views.sql as HAKIKI_APP") from None


@app.get("/analytics/{view_name}")
async def get_management_analytics_view(view_name: str):
    """Read one named analytics view. View names are an allowlist, never SQL input."""
    view_names = set(VIEW_QUERIES) - {"management_kpis"}
    if view_name not in view_names:
        raise HTTPException(status_code=404, detail="Analytics view not found")
    repository = _analytics_repository()
    try:
        return {"items": repository.fetch_analytics_view(view_name)}
    except Exception as exc:
        logger.warning("Analytics view read failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Analytics view is unavailable; apply backend/db/views.sql as HAKIKI_APP") from None


@app.post("/claims/{claim_id}/evidence-pack")
async def create_claim_evidence_pack(claim_id: str):
    """Export minimized lifecycle evidence for synthetic-reference claims only."""
    repository = get_repository()
    if not is_oracle_active(repository):
        raise HTTPException(status_code=503, detail="Evidence packs require Oracle backend")
    try:
        pack = repository.get_evidence_pack_data(claim_id)
        if not pack:
            raise HTTPException(status_code=404, detail="Claim not found")
        saved = store_evidence_pack(pack)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Evidence pack creation failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Evidence pack could not be created") from None
    response = {key: value for key, value in saved.items() if key not in {"json_path", "pdf_path"}}
    response["files"] = {
        "json": f"/evidence-packs/{saved['pack_id']}.json",
        "pdf": f"/evidence-packs/{saved['pack_id']}.pdf",
    }
    return response


@app.get("/evidence-packs/{pack_id}.{extension}")
async def download_local_evidence_pack(pack_id: str, extension: str):
    if not re.fullmatch(r"[0-9a-f]{24}", pack_id) or extension not in {"json", "pdf"}:
        raise HTTPException(status_code=404, detail="Evidence pack not found")
    directory = Path(os.getenv("EVIDENCE_DIR", "./evidence_packs")).expanduser().resolve()
    path = (directory / f"{pack_id}.{extension}").resolve()
    if path.parent != directory or not path.is_file():
        raise HTTPException(status_code=404, detail="Evidence pack not found")
    media_type = "application/json" if extension == "json" else "application/pdf"
    return FileResponse(path, media_type=media_type, filename=path.name)

# Session-scoped store for user corrections.
# Persists for the life of the server process (sufficient for a demo).
_session_corrections: dict[str, dict] = {}
_session_claims: list[dict] = []


def get_claim_or_404(claim_id: str) -> dict:
    """Look up a corrected, newly created, or seeded claim."""
    repository = get_repository()
    if is_oracle_active(repository):
        try:
            stored = repository.get_claim(claim_id)
        except Exception as exc:
            logger.warning("Oracle claim lookup failed (%s)", type(exc).__name__)
            raise HTTPException(status_code=503, detail="Selected database is unavailable") from None
        if is_oracle_active(repository):
            if stored:
                return stored
            raise HTTPException(status_code=404, detail=f"Claim '{claim_id}' not found")
    if claim_id in _session_corrections:
        return _session_corrections[claim_id]
    match = next((c for c in [*_session_claims, *MOCK_CLAIMS] if c["id"] == claim_id), None)
    if not match:
        raise HTTPException(status_code=404, detail=f"Claim '{claim_id}' not found")
    return match


def full_pipeline(claim: dict, record_audit: bool = True) -> dict:
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
    if record_audit and claim.get("id"):
        try:
            chain.record_claim_received(claim)
            chain.record_validation(claim.get("id"), result, claim)
        except Exception as exc:
            raise _storage_unavailable(exc, "Audit storage is unavailable; validation was not recorded") from None
    return result


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/claims/{claim_id}/audit")
async def get_claim_audit(claim_id: str):
    """Claim lifecycle events and comparison against the current saved version."""
    claim = get_claim_or_404(claim_id)
    try:
        chain.record_claim_received(claim)
        return {
            "claim_id": claim_id,
            "history": chain.get_chain_for_claim(claim_id),
            "current_version": chain.verify_current_claim_version(claim_id, claim),
        }
    except Exception as exc:
        raise _storage_unavailable(exc, "Audit history is unavailable") from None


@app.get("/audit/verify")
async def verify_audit_chain():
    """Recomputes every hash in the ledger and confirms nothing was altered."""
    try:
        return chain.verify_chain()
    except Exception as exc:
        raise _storage_unavailable(exc, "Audit ledger is unavailable") from None

@app.post("/ledger/anchor")
async def anchor_audit_ledger(x_anchor_secret: str = Header(default="", alias="X-Anchor-Secret")):
    if not config.ANCHOR_API_SECRET or not hmac.compare_digest(x_anchor_secret, config.ANCHOR_API_SECRET):
        raise HTTPException(status_code=403, detail="Manual ledger anchoring is not authorized")
    return anchor.anchor_latest()


@app.get("/ledger/verify-anchor")
async def verify_ledger_anchor():
    return anchor.verify_anchors()


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
        source_claims = [*MOCK_CLAIMS, *_session_claims]
    else:
        try:
            source_claims = await openimis.get_claims_parsed()
            if not source_claims:
                logger.warning("openIMIS returned 0 claims — falling back to mock")
                source_claims = [*MOCK_CLAIMS, *_session_claims]
        except Exception as exc:
            logger.warning("openIMIS unreachable (%s) — falling back to mock", exc)
            source_claims = [*MOCK_CLAIMS, *_session_claims]

    # Apply in-session corrections
    repository = get_repository()
    if is_oracle_active(repository):
        if not config.use_mock:
            raise HTTPException(status_code=503, detail="Oracle mode is restricted to synthetic demo claims; live openIMIS data is disabled")
        try:
            claims = repository.sync_claims(source_claims)
        except Exception as exc:
            frames = traceback.extract_tb(exc.__traceback__)
            if frames:
                frame = frames[-1]
                logger.warning(
                    "Oracle claim sync failed (%s at %s:%d in %s)",
                    type(exc).__name__, Path(frame.filename).name, frame.lineno, frame.name,
                )
            else:
                logger.warning("Oracle claim sync failed (%s)", type(exc).__name__)
            raise HTTPException(status_code=503, detail="Oracle database is unavailable; try again or use oracle_with_fallback") from None
        if not is_oracle_active(repository):
            claims = [_session_corrections.get(c["id"], c) for c in source_claims]
            chain.record_claims_received(claims)
    else:
        claims = [_session_corrections.get(c["id"], c) for c in source_claims]
        chain.record_claims_received(claims)

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
    claim = get_claim_or_404(claim_id)
    try:
        chain.record_claim_received(claim)
    except Exception as exc:
        raise _storage_unavailable(exc, "Claim intake could not be recorded") from None
    return claim


@app.post("/claims")
async def create_claim(claim: dict):
    """Add a demo claim to its owning department's inbox for this server session."""
    import uuid

    department = str(claim.get("department", "")).strip().lower()
    if department not in {"outpatient", "maternity", "renal", "surgical"}:
        raise HTTPException(status_code=422, detail="Choose a valid owning department")
    created = {
        **claim,
        "id": claim.get("id") or f"SHA-CLM-DEMO-{uuid.uuid4().hex[:8].upper()}",
        "is_synthetic": True,
        "facility_name": "Kerugoya Level 5 Hospital",
        "facility_code": "KRG-005",
        "department": department,
    }
    repository = get_repository()
    try:
        if is_oracle_active(repository):
            created = repository.create_claim(created)
        if not is_oracle_active(repository):
            _session_claims.insert(0, created)
            chain.record_claim_received(created)
    except Exception as exc:
        logger.warning("Claim creation failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Claim could not be saved to the selected database") from None
    result = validate(created)
    return {"claim": created, "_preview": {"score": result["score"], "status": result["status"], "color": result["color"], "error_count": result["error_count"], "warning_count": result["warning_count"]}}


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
    # This endpoint accepts an arbitrary preview payload. It is deliberately
    # not saved as a claim version or included in the audit trail.
    result = full_pipeline(claim, record_audit=False)
    return result


@app.post("/claims/{claim_id}/correct")
async def correct_claim(claim_id: str, corrections: dict):
    """
    Merge corrections into the claim, save to the session store, re-validate.
    The frontend sends the full corrected claim dict in the body.
    """
    original = get_claim_or_404(claim_id)
    try:
        chain.record_claim_received(original)
    except Exception as exc:
        raise _storage_unavailable(exc, "Claim intake could not be recorded") from None

    # Merge: original fields overridden by corrections
    public_corrections = {key: value for key, value in corrections.items() if not str(key).startswith("_")}
    updated = {**original, **public_corrections, "id": claim_id}
    try:
        chain.record_claim_correction(claim_id, original, updated)
    except Exception as exc:
        raise _storage_unavailable(exc, "Correction and its audit event could not be saved") from None
    if not is_oracle_active(get_repository()):
        _session_corrections[claim_id] = updated

    result = full_pipeline(updated)
    logger.info("Claim %s corrected — new score: %d", claim_id, result["score"])

    return {"claim": updated, "validation": result}


@app.post("/claims/{claim_id}/department-review")
async def record_department_review(claim_id: str, review_event: dict):
    """Append a fingerprinted department action; raw notes/evidence stay client-side."""
    claim = get_claim_or_404(claim_id)
    try:
        chain.record_claim_received(claim)
    except Exception as exc:
        raise _storage_unavailable(exc, "Claim intake could not be recorded") from None
    department = str(review_event.get("department", "")).strip().lower()
    if department != str(claim.get("department", "")).strip().lower():
        raise HTTPException(status_code=422, detail="Department does not own this claim")
    action = str(review_event.get("action", ""))
    allowed_actions = {
        "department_check_completed", "department_check_reopened",
        "department_evidence_saved", "department_signed_off",
        "department_signoff_revoked", "department_reviewer_updated",
        "department_review_note_saved",
    }
    fingerprint = str(review_event.get("review_fingerprint", ""))
    completed_checks = review_event.get("completed_checks", [])
    if (action not in allowed_actions or not re.fullmatch(r"[0-9a-f]{64}", fingerprint)
            or not isinstance(completed_checks, list)
            or len(completed_checks) > 30
            or any(not isinstance(item, str) or len(item) > 120 for item in completed_checks)):
        raise HTTPException(status_code=422, detail="Invalid department review event")
    review_event["actor_label"] = str(review_event.get("actor_label", ""))[:120]
    try:
        event = chain.record_department_review(
            claim_id, department, review_event, action,
            str(review_event.get("step_title", ""))[:120] or None,
            claim,
        )
    except Exception as exc:
        raise _storage_unavailable(exc, "Department action could not be recorded") from None
    return {"recorded": event is not None, "event": event}


@app.get("/claims/{claim_id}/department-review")
async def get_department_review_state(claim_id: str, department: str):
    claim = get_claim_or_404(claim_id)
    department = department.strip().lower()
    if department != str(claim.get("department", "")).strip().lower():
        raise HTTPException(status_code=422, detail="Department does not own this claim")
    try:
        review = get_repository().get_department_review(claim_id, department)
        return {"review": review}
    except Exception as exc:
        logger.warning("Department review read failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Department review storage is unavailable") from None


@app.put("/claims/{claim_id}/department-review")
async def save_department_review_state(claim_id: str, body: dict):
    claim = get_claim_or_404(claim_id)
    department = str(body.get("department", "")).strip().lower()
    review = body.get("review")
    if department != str(claim.get("department", "")).strip().lower():
        raise HTTPException(status_code=422, detail="Department does not own this claim")
    if not isinstance(review, dict):
        raise HTTPException(status_code=422, detail="A review state object is required")
    try:
        saved = get_repository().save_department_review(claim_id, department, review)
        return {"review": saved, "saved": True}
    except Exception as exc:
        logger.warning("Department review save failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Department review could not be saved") from None


@app.get("/outcomes")
async def get_outcomes(claim_id: str | None = None):
    try:
        return {"outcomes": get_repository().list_outcomes(claim_id)}
    except Exception as exc:
        logger.warning("Outcome read failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Outcome storage is unavailable") from None


@app.post("/outcomes")
async def save_outcome(body: dict):
    required = ("id", "claimId", "outcome", "recordedAt")
    if any(not body.get(field) for field in required):
        raise HTTPException(status_code=422, detail="Outcome id, claimId, outcome and recordedAt are required")
    claim = get_claim_or_404(str(body["claimId"]))
    if len(str(body.get("note", ""))) > 2000:
        raise HTTPException(status_code=422, detail="Outcome note is too long")
    if body.get("department") != (claim.get("department") or "Unassigned"):
        raise HTTPException(status_code=422, detail="Outcome department does not match the claim")
    try:
        saved = get_repository().save_outcome(body)
        return {"outcome": saved, "saved": True}
    except Exception as exc:
        logger.warning("Outcome save failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Outcome could not be saved") from None


@app.post("/claims/{claim_id}/staff-review")
async def record_staff_review(claim_id: str, review_event: dict):
    """Record the officer's review of the currently saved claim version."""
    claim = get_claim_or_404(claim_id)
    try:
        chain.record_claim_received(claim)
    except Exception as exc:
        raise _storage_unavailable(exc, "Claim intake could not be recorded") from None
    reviewer = str(review_event.get("reviewer", "")).strip()[:120]
    decision = str(review_event.get("decision", ""))
    if not reviewer or decision not in {"reviewed", "correction_requested"}:
        raise HTTPException(status_code=422, detail="Reviewer name and a valid review decision are required")
    try:
        event = chain.record_staff_review(claim_id, claim, reviewer, decision)
    except Exception as exc:
        raise _storage_unavailable(exc, "Staff review could not be recorded") from None
    return {"recorded": event is not None, "event": event}


@app.post("/claims/{claim_id}/submit")
async def submit_claim(claim_id: str):
    """
    Submit the ClaimResponse to openIMIS.
    Blocked if there are any error-severity rule failures remaining.
    """
    claim = get_claim_or_404(claim_id)
    try:
        chain.record_claim_received(claim)
    except Exception as exc:
        raise _storage_unavailable(exc, "Claim intake could not be recorded") from None
    result = validate(claim)

    if result["error_count"] > 0:
        try:
            chain.record_submission(claim_id, claim, "blocked", f"{result['error_count']} validation errors remain")
        except Exception as exc:
            raise _storage_unavailable(exc, "Submission result could not be recorded") from None
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
        try:
            chain.record_submission(claim_id, claim, "mocked", "Mock mode; no payer submission was made")
        except Exception as exc:
            raise _storage_unavailable(exc, "Submission result could not be recorded") from None
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
        chain.record_submission(claim_id, claim, "accepted_by_openimis", "openIMIS returned a response")
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
        chain.record_submission(claim_id, claim, "failed", "openIMIS request failed")
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
    x_ussd_secret: str = Header(default="", alias="X-USSD-Secret"),
):
    """
    Africa's Talking USSD callback.

    AT sends application/x-www-form-urlencoded POST on every user input.
    We respond with plain text: 'CON <msg>' to continue or 'END <msg>' to close.
    Registered as callback URL in the AT dashboard under USSD settings.
    """
    if config.USSD_SHARED_SECRET and x_ussd_secret != config.USSD_SHARED_SECRET:
        raise HTTPException(status_code=401, detail="Invalid USSD callback secret")

    masked_phone = f"***{phoneNumber[-3:]}" if len(phoneNumber) >= 3 else "***"
    logger.info(
        "USSD | session=%s phone=%s text=%r",
        sessionId,
        masked_phone,
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
