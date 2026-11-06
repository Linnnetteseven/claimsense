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
import asyncio
from time import perf_counter
from fastapi import Form, BackgroundTasks, Header
from fastapi.responses import PlainTextResponse, FileResponse
from ussd.handler import handle_ussd_session
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from config import config
from data.mock_claims import MOCK_CLAIMS
from validation.engine import validate
from validation.rules import RULES_DATE, RULES_VERSION
from fhir.builder import build_claim_response
from fhir.client import openimis
from llm.explainer import explain_errors
from audit import chain, anchor
from db.factory import get_repository, is_oracle_active, configured_backend
from db.connection import (
    connection_mode as oracle_connection_mode,
    begin_sql_query_tracking,
    finish_sql_query_tracking,
    get_pool,
)
from db import response_cache
from db.analytics import VIEW_QUERIES
from evidence.packs import store_evidence_pack
from db.select_ai import run_readonly_analytics_query, SelectAINotAvailable
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


def _require_departments_enabled() -> None:
    if not config.DEPARTMENTS_ENABLED:
        raise HTTPException(status_code=404, detail="Department workflow is disabled")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 50)
    logger.info("ClaimSense starting")
    logger.info("openIMIS: %s", config.OPENIMIS_URL)
    logger.info("Mode: %s", "MOCK" if config.use_mock else "LIVE")
    logger.info("LLM: %s", "enabled" if config.llm_enabled else "disabled — set GEMINI_API_KEY")
    logger.info("=" * 50)
    if configured_backend() in {"oracle", "oracle_with_fallback"}:
        try:
            await asyncio.to_thread(get_pool)
            await _warm_oracle_read_cache()
        except Exception as exc:
            logger.warning("Oracle startup warm-up unavailable (%s); app will continue", type(exc).__name__)
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


@app.middleware("http")
async def log_request_metrics(request, call_next):
    token = begin_sql_query_tracking()
    started = perf_counter()
    response = None
    try:
        response = await call_next(request)
        return response
    finally:
        duration_ms = (perf_counter() - started) * 1000
        sql_count = finish_sql_query_tracking(token)
        route = request.scope.get("route")
        path = getattr(route, "path", request.url.path)
        status = response.status_code if response is not None else 500
        logger.info("HTTP %s %s status=%s duration_ms=%.1f sql_queries=%d",
                    request.method, path, status, duration_ms, sql_count)
        if response is not None:
            response.headers["X-SQL-Query-Count"] = str(sql_count)
            response.headers["Server-Timing"] = f"app;dur={duration_ms:.1f}"


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


@app.get("/settings/ui")
async def ui_settings():
    """Expose non-secret workflow switches used to shape the demo UI."""
    return {"departments_enabled": bool(config.DEPARTMENTS_ENABLED)}


def _analytics_repository():
    repository = get_repository()
    if not is_oracle_active(repository):
        raise HTTPException(status_code=503, detail="Analytics requires Oracle backend")
    return repository


def _load_oracle_queue_base(repository):
    """Prepare a bounded queue projection; never read claim payloads for validated rows."""
    if config.use_mock:
        repository.sync_claims(MOCK_CLAIMS)
    total, claims = repository.list_claim_queue(limit=50)
    for claim in claims:
        payload = claim.pop("_validation_payload", None)
        if payload is not None:
            result = validate(payload)
            claim["_preview"] = {
                "score": result["score"], "status": result["status"], "color": result["color"],
                "error_count": result["error_count"], "warning_count": result["warning_count"],
            }
    return {"total_count": total, "claims": claims}


async def _oracle_queue_base(repository=None):
    repository = repository or _analytics_repository()
    cache_key = ("claims",)
    cached = response_cache.get(cache_key)
    if cached is not None:
        return cached
    data = await asyncio.to_thread(_load_oracle_queue_base, repository)
    return response_cache.put(cache_key, data)


async def _load_analytics_overview(repository):
    """Run five independent aggregate reads concurrently, never scan the ledger."""
    kpis, combined, scores, failures, trend = await asyncio.gather(
        asyncio.to_thread(repository.fetch_analytics_view, "management_kpis"),
        asyncio.to_thread(repository.fetch_analytics_status_signoffs),
        asyncio.to_thread(repository.fetch_analytics_view, "score_by_department"),
        asyncio.to_thread(repository.fetch_analytics_view, "top_failed_rules"),
        asyncio.to_thread(repository.fetch_analytics_view, "rework_trend_weekly"),
    )
    kpi = kpis[0] if kpis else {}
    ledger = {
        "entries": kpi.get("ledger_entries", 0), "last_seq": kpi.get("last_seq", 0),
        "last_anchor_at": kpi.get("last_anchor_at"), "last_anchor_tx": kpi.get("last_anchor_tx"),
        "unanchored_entries": kpi.get("unanchored_entries", 0),
    }
    return {"available": True, "kpis": kpi,
            "claims_by_status": combined["claims_by_status"],
            "score_by_department": scores, "top_failed_rules": failures,
            "rework_trend_weekly": trend, "ledger_status": ledger,
            "signoff_progress": combined["signoff_progress"]}


async def _oracle_analytics_overview(repository=None):
    repository = repository or _analytics_repository()
    cache_key = ("analytics", "overview")
    cached = response_cache.get(cache_key)
    if cached is not None:
        return cached
    data = await _load_analytics_overview(repository)
    return response_cache.put(cache_key, data)


async def _warm_oracle_read_cache():
    repository = get_repository()
    if not is_oracle_active(repository):
        return
    queue_data = await _oracle_queue_base(repository)
    analytics_data = await _oracle_analytics_overview(repository)
    logger.info("Oracle read cache warmed (claims=%d, analytics=yes)", len(queue_data["claims"]))


@app.get("/analytics/overview")
async def get_management_analytics():
    """Return aggregate metrics from Oracle views; no claim-level data is selected."""
    repository = _analytics_repository()
    try:
        return await _oracle_analytics_overview(repository)
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
        key = ("analytics", view_name)
        cached = response_cache.get(key)
        if cached is None:
            cached = await asyncio.to_thread(repository.fetch_analytics_view, view_name)
            response_cache.put(key, cached)
        return {"items": cached}
    except Exception as exc:
        logger.warning("Analytics view read failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Analytics view is unavailable; apply backend/db/views.sql as HAKIKI_APP") from None


@app.post("/analytics/ask")
async def ask_management_analytics(body: dict):
    """Experimental natural-language analytics, backed by a view-only Oracle user."""
    if not config.ENABLE_SELECT_AI:
        raise HTTPException(status_code=503, detail="Experimental Oracle Select AI is disabled")
    question = str(body.get("question", "")).strip()
    if not question or len(question) > 500:
        raise HTTPException(status_code=422, detail="Provide an analytics question under 500 characters")
    if re.search(r"\b(patient|member|person|individual|patient name|phone|national id|claim id|specific claim)\b|SYN-[0-9]{6}|SHA-CLM-[A-Z0-9-]+", question, re.IGNORECASE):
        raise HTTPException(status_code=422, detail="Ask about aggregate facility metrics only; patient-level questions are not supported")
    try:
        return {"experimental": True, **run_readonly_analytics_query(question)}
    except SelectAINotAvailable:
        return {"available": False, "message": "Oracle Select AI is not available for this database or profile."}
    except Exception as exc:
        logger.warning("Experimental Select AI query unavailable (%s)", type(exc).__name__)
        return {"available": False, "message": "Oracle Select AI is not available for this database or profile."}


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
_session_lifecycle: dict[str, dict] = {}
_session_versions: dict[str, list[dict]] = {}


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
        match = _session_corrections[claim_id]
    else:
        match = next((c for c in [*_session_claims, *MOCK_CLAIMS] if c["id"] == claim_id), None)
    if not match:
        raise HTTPException(status_code=404, detail=f"Claim '{claim_id}' not found")
    from audit.chain import claim_fingerprint
    state = _session_lifecycle.setdefault(claim_id, {
        "status": "needs_revalidation", "version": 1,
        "version_fingerprint": claim_fingerprint(match),
    })
    return {**match, "_lifecycle": dict(state)}


def full_pipeline(claim: dict, record_audit: bool = True, informational: bool = False) -> dict:
    """
    The core validation pipeline used by multiple routes:
      1. Run the deterministic validation rules
      2. Ask Gemini to explain errors in plain English
      3. Build the FHIR R4 ClaimResponse resource
      4. Record the result in the tamper-evident audit trail
    Returns everything the frontend needs in one response.
    """
    result = validate(claim)
    result["rules_version"] = RULES_VERSION
    result["rules_date"] = RULES_DATE
    explanations, ai_used = explain_errors(result["errors"], claim)
    result["explanations"] = explanations
    result["ai_explanations_used"] = ai_used
    result["fhir_claim_response"] = build_claim_response(claim, result)
    if record_audit and claim.get("id"):
        try:
            claim_id = str(claim["id"])
            if informational:
                lifecycle = claim.get("_lifecycle") or get_repository().get_claim_lifecycle(claim_id) or {}
                result["version"] = int(lifecycle.get("version") or 1)
                event = chain.record_validation(claim_id, result, claim, informational=True)
            else:
                chain.record_claim_received(claim)
                lifecycle = claim.get("_lifecycle") or _session_lifecycle.get(claim_id, {})
                result["version"] = int(lifecycle.get("version") or 1) + 1
                event = chain.record_validation(claim_id, result, claim)
                if event and event.get("version"):
                    result["version"] = int(event["version"])
                fingerprint = chain.claim_fingerprint(claim)
                result["version_fingerprint"] = fingerprint
                if is_oracle_active(get_repository()):
                    state = get_repository().get_claim_lifecycle(claim_id) or {}
                else:
                    versions = _session_versions.setdefault(claim_id, [])
                    versions.append({"version": result["version"], "claim": {k: v for k, v in claim.items() if not k.startswith("_")},
                                     "version_fingerprint": fingerprint})
                    state = {"status": "ready" if result.get("status") == "Ready for Submission" else "needs_review" if result.get("status") == "Needs Review" else "blocked",
                             "version": result["version"], "version_fingerprint": fingerprint}
                    _session_lifecycle[claim_id] = state
                result["lifecycle"] = state
        except Exception as exc:
            raise _storage_unavailable(exc, "Audit storage is unavailable; validation was not recorded") from None
    return result


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/claims/{claim_id}/audit")
async def get_claim_audit(claim_id: str):
    """Claim lifecycle events and comparison against the current saved version."""
    repository = get_repository()
    if is_oracle_active(repository):
        try:
            result = repository.get_claim_audit(claim_id, limit=50)
            if result is None:
                raise HTTPException(status_code=404, detail=f"Claim '{claim_id}' not found")
            return {"claim_id": claim_id, **result}
        except Exception as exc:
            if isinstance(exc, HTTPException):
                raise
            raise _storage_unavailable(exc, "Audit history is unavailable") from None
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
async def anchor_audit_ledger(
    background_tasks: BackgroundTasks,
    x_anchor_secret: str = Header(default="", alias="X-Anchor-Secret"),
):
    if not config.ANCHOR_API_SECRET or not hmac.compare_digest(x_anchor_secret, config.ANCHOR_API_SECRET):
        raise HTTPException(status_code=403, detail="Manual ledger anchoring is not authorized")
    result = anchor.anchor_latest()
    if result.get("status") == "blocked":
        raise HTTPException(status_code=409, detail=result.get("message") or result.get("reason"))
    if result.get("submitted") and result.get("root_hash"):
        background_tasks.add_task(anchor.confirm_anchor, result["root_hash"])
    return result


@app.get("/ledger/verify-anchor")
async def verify_ledger_anchor():
    return anchor.verify_anchors()


@app.get("/ledger/anchor-status")
async def get_ledger_anchor_status(root_hash: str | None = None):
    return anchor.anchor_status(root_hash)


@app.post("/ledger/anchor-status/check")
async def check_ledger_anchor_status(root_hash: str | None = None):
    return anchor.anchor_status(root_hash, check_chain=True)


@app.post("/ledger/verify-full")
async def verify_full_ledger():
    try:
        return anchor.verify_full_ledger()
    except Exception as exc:
        raise _storage_unavailable(exc, "Full ledger verification could not be completed") from None


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
    page_size: int | None = None,
):
    """
    Returns claims with pre-scores. Supports:
      q         — search by patient name or claim ID (case-insensitive)
      status    — all | ready | review | error
      page      — page number (1-based)
      page_size — claims per page (Oracle default 50, Redis default 20)
    """
    repository = get_repository()
    if is_oracle_active(repository):
        if not config.use_mock:
            raise HTTPException(status_code=503, detail="Oracle mode is restricted to synthetic demo claims; live openIMIS data is disabled")
        try:
            base = await _oracle_queue_base(repository)
        except Exception as exc:
            frames = traceback.extract_tb(exc.__traceback__)
            location = f"{Path(frames[-1].filename).name}:{frames[-1].lineno}" if frames else "unknown"
            logger.warning("Oracle queue read failed (%s at %s)", type(exc).__name__, location)
            raise HTTPException(status_code=503, detail="Database slow / unreachable; Oracle claims could not be loaded") from None

        claims = list(base["claims"])
        if status == "ready":
            claims = [claim for claim in claims if claim.get("_preview", {}).get("color") == "green"]
        elif status == "review":
            claims = [claim for claim in claims if claim.get("_preview", {}).get("color") == "amber"]
        elif status == "error":
            claims = [claim for claim in claims if claim.get("_preview", {}).get("color") == "red"]
        if q.strip():
            q_lower = q.strip().lower()
            claims = [claim for claim in claims if any(
                q_lower in str(claim.get(key) or "").lower()
                for key in ("patient_name", "id", "facility_name")
            )]
        bounded_page_size = min(50, max(1, page_size or 50))
        start = max(0, page - 1) * bounded_page_size
        page_claims = claims[start:start + bounded_page_size]
        return {
            "count": len(claims), "total_count": base["total_count"],
            "page": page, "page_size": bounded_page_size,
            "total_pages": max(1, -(-min(base["total_count"], 50) // bounded_page_size)),
            "claims": page_claims,
        }

    # Keep the pre-existing Redis default unchanged.
    if page_size is None:
        page_size = 20
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
    claims = [_session_corrections.get(c["id"], c) for c in source_claims]
    chain.record_claims_received(claims)

    # Score all claims
    scored = []
    for claim in claims:
        v = validate(claim)
        lifecycle = _session_lifecycle.setdefault(claim["id"], {
            "status": "needs_revalidation", "version": 1,
            "version_fingerprint": chain.claim_fingerprint(claim),
        })
        preview = {
            "score": v["score"],
            "status": v["status"],
            "color": v["color"],
            "error_count": v["error_count"],
            "warning_count": v["warning_count"],
        }
        if lifecycle["status"] == "needs_revalidation":
            preview.update({"status": "Needs revalidation", "color": "amber"})
        elif lifecycle["status"] == "submitted":
            preview.update({"status": "Submitted, locked", "color": "green"})
        scored.append({
            **claim,
            "_preview": preview,
            "_lifecycle": dict(lifecycle),
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
    if not is_oracle_active(get_repository()):
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
    result = full_pipeline(created)
    if result.get("lifecycle"):
        created["_lifecycle"] = result["lifecycle"]
    return {"claim": created, "_preview": {"score": result["score"], "status": result["status"], "color": result["color"], "error_count": result["error_count"], "warning_count": result["warning_count"]}, "validation": result}


@app.post("/claims/{claim_id}/validate")
async def validate_claim(claim_id: str):
    """Full validation pipeline for a claim fetched by ID."""
    claim = get_claim_or_404(claim_id)
    if str((claim.get("_lifecycle") or {}).get("status", "")).lower() == "submitted":
        raise HTTPException(status_code=409, detail="Submitted claims are locked; use the read-only re-check")
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


@app.post("/claims/{claim_id}/recheck")
async def recheck_submitted_claim(claim_id: str):
    """Run current rules against a submitted snapshot without changing lifecycle status."""
    claim = get_claim_or_404(claim_id)
    lifecycle = claim.get("_lifecycle") or {}
    if str(lifecycle.get("status", "")).lower() != "submitted":
        raise HTTPException(status_code=409, detail="Read-only re-check is only available after submission")
    version = int(lifecycle.get("version") or 0)
    repository = get_repository()
    try:
        if is_oracle_active(repository):
            saved = repository.get_claim_version(claim_id, version)
            if not saved:
                raise HTTPException(status_code=409, detail="Submitted claim version is unavailable")
            version_claim = saved["claim"]
            if saved["version_fingerprint"] != chain.claim_fingerprint(version_claim):
                raise HTTPException(status_code=409, detail="Submitted claim version fingerprint does not match")
        else:
            saved = next((item for item in _session_versions.get(claim_id, []) if item["version"] == version), None)
            version_claim = saved["claim"] if saved else {k: v for k, v in claim.items() if not k.startswith("_")}
        result = full_pipeline(version_claim, record_audit=False)
        result.update({"version": version, "version_fingerprint": chain.claim_fingerprint(version_claim),
                       "informational": True})
        if is_oracle_active(repository):
            chain.record_validation(claim_id, result, version_claim, informational=True)
        else:
            chain.record_event({"type": "informational_validation", "claim_id": claim_id,
                                "version": version, "version_fingerprint": result["version_fingerprint"],
                                "score": result["score"], "status": result["status"],
                                "rules_version": RULES_VERSION, "rules_date": RULES_DATE})
        return {"validation": result, "lifecycle": lifecycle}
    except HTTPException:
        raise
    except Exception as exc:
        raise _storage_unavailable(exc, "Read-only re-check could not be recorded") from None


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
    lifecycle = original.get("_lifecycle") or {}
    if str(lifecycle.get("status", "")).lower() == "submitted":
        raise HTTPException(status_code=409, detail="Submitted claims are locked; start a correction version first")
    correction_reason = str(corrections.get("correction_reason") or "").strip()
    if isinstance(corrections.get("claim"), dict):
        corrections = corrections["claim"]
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


@app.post("/claims/{claim_id}/correction")
async def start_claim_correction(claim_id: str, body: dict):
    """Open an immutable correction snapshot after payer return/rejection or a reason."""
    claim = get_claim_or_404(claim_id)
    lifecycle = claim.get("_lifecycle") or {}
    if str(lifecycle.get("status", "")).lower() != "submitted":
        raise HTTPException(status_code=409, detail="A correction can only be started after submission")
    reason = str(body.get("reason") or "").strip()
    outcome = str(lifecycle.get("latest_outcome") or "").strip().lower()
    if outcome not in {"returned", "rejected"} and not reason:
        raise HTTPException(status_code=422, detail="Record a Returned/Rejected outcome or provide a correction reason")
    if len(reason) > 500:
        raise HTTPException(status_code=422, detail="Correction reason is too long")
    repository = get_repository()
    try:
        if is_oracle_active(repository):
            correction = repository.create_correction_version(claim_id, reason or None)
            lifecycle = repository.get_claim_lifecycle(claim_id) or correction
        else:
            version = int(lifecycle.get("version") or 1) + 1
            fingerprint = chain.claim_fingerprint(claim)
            clean = {k: v for k, v in claim.items() if not k.startswith("_")}
            event = chain.record_event({"type": "claim_correction_started", "claim_id": claim_id,
                                        "from_version": version - 1, "version": version,
                                        "previous_version_fingerprint": fingerprint,
                                        "version_fingerprint": fingerprint,
                                        "correction_authorization": "explicit_reason" if reason else "returned_or_rejected_outcome"})
            _session_versions.setdefault(claim_id, []).append({"version": version, "claim": clean, "version_fingerprint": fingerprint})
            lifecycle = {"status": "needs_revalidation", "version": version, "version_fingerprint": fingerprint,
                         "latest_outcome": outcome or None}
            _session_lifecycle[claim_id] = lifecycle
            correction = {"claim": clean, **lifecycle, "event": event}
        return {"correction": correction, "lifecycle": lifecycle}
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except Exception as exc:
        raise _storage_unavailable(exc, "Correction version could not be created") from None


@app.post("/claims/{claim_id}/department-review")
async def record_department_review(claim_id: str, review_event: dict):
    """Append a fingerprinted department action; raw notes/evidence stay client-side."""
    _require_departments_enabled()
    claim = get_claim_or_404(claim_id)
    if str((claim.get("_lifecycle") or {}).get("status", "")).lower() == "submitted":
        raise HTTPException(status_code=409, detail="Submitted claims are locked; start a correction version first")
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
        if is_oracle_active(get_repository()):
            get_repository().mark_claim_stale(claim_id, "department review changed")
        else:
            _session_lifecycle[claim_id] = {**(claim.get("_lifecycle") or {}), "status": "needs_revalidation"}
    except Exception as exc:
        raise _storage_unavailable(exc, "Department action could not be recorded") from None
    return {"recorded": event is not None, "event": event}


@app.get("/claims/{claim_id}/department-review")
async def get_department_review_state(claim_id: str, department: str):
    _require_departments_enabled()
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
    _require_departments_enabled()
    claim = get_claim_or_404(claim_id)
    if str((claim.get("_lifecycle") or {}).get("status", "")).lower() == "submitted":
        raise HTTPException(status_code=409, detail="Submitted claims are locked; start a correction version first")
    department = str(body.get("department", "")).strip().lower()
    review = body.get("review")
    if department != str(claim.get("department", "")).strip().lower():
        raise HTTPException(status_code=422, detail="Department does not own this claim")
    if not isinstance(review, dict):
        raise HTTPException(status_code=422, detail="A review state object is required")
    try:
        saved = get_repository().save_department_review(claim_id, department, review)
        return {"review": saved, "saved": True}
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
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
    if str(body.get("outcome")) not in {"Submitted", "Accepted", "Paid", "Returned", "Rejected", "Queried", "Resubmitted", "Other"}:
        raise HTTPException(status_code=422, detail="Choose a supported claim outcome")
    claim = get_claim_or_404(str(body["claimId"]))
    if len(str(body.get("note", ""))) > 2000:
        raise HTTPException(status_code=422, detail="Outcome note is too long")
    if str(body.get("outcome", "")).lower() in {"returned", "rejected"} and not str(body.get("reasonCategory") or "").strip():
        raise HTTPException(status_code=422, detail="A return/rejection reason is required")
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
    repository = get_repository()
    lifecycle = claim.get("_lifecycle") or {}
    if str(lifecycle.get("status", "")).lower() == "submitted":
        raise HTTPException(status_code=409, detail="Claim is already submitted and locked")
    if str(lifecycle.get("status", "")).lower() == "needs_revalidation":
        raise HTTPException(status_code=409, detail="Claim changed after its last validation; revalidate before submitting")
    if is_oracle_active(repository):
        latest = repository.get_latest_validation(claim_id)
        current_version = int(lifecycle.get("version") or 0)
        if not latest or latest["version"] != current_version:
            raise HTTPException(status_code=409, detail="Revalidate the current claim version before submitting")
        if str(lifecycle.get("status", "")).lower() != "ready" or latest.get("status") != "Ready for Submission":
            raise HTTPException(status_code=409, detail="Only a Ready claim can be submitted")
        if latest.get("rules_version") != RULES_VERSION:
            raise HTTPException(status_code=409, detail="Validation used older rules; revalidate before submitting")
        saved = repository.get_claim_version(claim_id, latest["version"])
        if not saved or chain.claim_fingerprint(saved["claim"]) != saved["version_fingerprint"]:
            raise HTTPException(status_code=409, detail="Latest validated claim version failed fingerprint verification")
        claim = saved["claim"]
        result = validate(claim)
        result["rules_version"] = RULES_VERSION
        result["rules_date"] = RULES_DATE
        result["version"] = latest["version"]
        result["version_fingerprint"] = saved["version_fingerprint"]
        if result["error_count"] != latest["error_count"]:
            raise HTTPException(status_code=409, detail="Validation result changed; run validation again before submitting")
    else:
        latest = _session_lifecycle.get(claim_id, {})
        saved = next((item for item in _session_versions.get(claim_id, []) if item["version"] == latest.get("version")), None)
        if not saved or latest.get("status") != "ready":
            raise HTTPException(status_code=409, detail="Revalidate the current claim version before submitting")
        claim = saved["claim"]
        result = validate(claim)
        result["rules_version"] = RULES_VERSION
        result["rules_date"] = RULES_DATE
        result["version"] = saved["version"]
        result["version_fingerprint"] = saved["version_fingerprint"]

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
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        except Exception as exc:
            raise _storage_unavailable(exc, "Submission result could not be recorded") from None
        if not is_oracle_active(repository):
            _session_lifecycle[claim_id] = {**_session_lifecycle[claim_id], "status": "submitted"}
        return {
            "submitted": True,
            "mode": "mock",
            "claim_id": claim_id,
            "score": result["score"],
            "version": result.get("version"),
            "version_fingerprint": result.get("version_fingerprint"),
            "lifecycle": (repository.get_claim_lifecycle(claim_id) if is_oracle_active(repository) else _session_lifecycle.get(claim_id)),
            "fhir_claim_response": fhir_cr,
            "note": "Set OPENIMIS_TOKEN in .env to submit to the live instance.",
        }

    try:
        openimis_resp = await openimis.post_claim_response(fhir_cr)
        chain.record_submission(claim_id, claim, "accepted_by_openimis", "openIMIS returned a response")
        if not is_oracle_active(repository):
            _session_lifecycle[claim_id] = {**_session_lifecycle[claim_id], "status": "submitted"}
        logger.info("openIMIS accepted ClaimResponse for %s", claim_id)
        return {
            "submitted": True,
            "mode": "live",
            "claim_id": claim_id,
            "score": result["score"],
            "version": result.get("version"),
            "version_fingerprint": result.get("version_fingerprint"),
            "lifecycle": (repository.get_claim_lifecycle(claim_id) if is_oracle_active(repository) else _session_lifecycle.get(claim_id)),
            "openimis_response": openimis_resp,
            "fhir_claim_response": fhir_cr,
        }
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
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
