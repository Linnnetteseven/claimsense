"""
Liveness (/) and dependency health (/health).

/health checks every dependency in parallel with short timeouts. Only Supabase is
required: without it Hakiki cannot work, so /health answers 503. The others degrade
gracefully (no AI wording, no audit chain, no UAT checks) and are reported as such.
ok = None means "not configured", so not checked.
"""

import os
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from api.deps import claims_repository
from api.models import Health
from config import config
from validation.rules import RULESET_VERSION

router = APIRouter(tags=["health"])
VERSION = "2.0.0"
TIMEOUT = 3.0


@router.get("/")
def liveness() -> dict:
    """Cheap check for uptime monitors; touches no dependency."""
    return {"service": "Hakiki", "status": "running", "version": VERSION}


def _timed(fn):
    start = time.perf_counter()
    try:
        ok, detail = fn()
    except Exception as exc:
        ok, detail = False, str(exc)[:200]
    return {"ok": ok, "detail": detail, "ms": int((time.perf_counter() - start) * 1000)}


def _supabase():
    claims_repository().ping()
    return True, None


def _upstash():
    url, token = os.environ.get("UPSTASH_REDIS_REST_URL"), os.environ.get("UPSTASH_REDIS_REST_TOKEN")
    if not (url and token):
        return None, "not configured: audit chain and shared explanation cache off"
    resp = httpx.post(url, headers={"Authorization": f"Bearer {token}"}, json=["PING"], timeout=TIMEOUT)
    return resp.is_success, None if resp.is_success else f"HTTP {resp.status_code}"


def _gemini():
    # Key presence only: calling the model costs quota and time.
    if not config.llm_enabled:
        return None, "not configured: rule advice shown without AI wording"
    return True, f"key set; model {config.GEMINI_MODEL}"


def _reachable(url: str, headers: dict | None = None):
    resp = httpx.get(url, headers=headers or {}, timeout=TIMEOUT, verify=config.SHA_FHIR_VERIFY_SSL)
    return resp.status_code < 500, f"HTTP {resp.status_code}"


def _sha():
    return _reachable(f"{config.SHA_FHIR_URL}/metadata", {"Accept": "application/fhir+json"})


def _openimis():
    if not config.OPENIMIS_TOKEN:
        return None, "not configured"
    return _reachable(config.OPENIMIS_URL)


CHECKS = {
    "supabase": (_supabase, True),
    "upstash": (_upstash, False),
    "gemini": (_gemini, False),
    "sha_uat": (_sha, False),
    "openimis": (_openimis, False),
}


@router.get("/health", response_model=Health, responses={503: {"model": Health}})
def health():
    with ThreadPoolExecutor(max_workers=len(CHECKS)) as pool:
        futures = {name: pool.submit(_timed, fn) for name, (fn, _) in CHECKS.items()}
        checks = {name: {**f.result(), "required": CHECKS[name][1]} for name, f in futures.items()}
    ok = all(c["ok"] for c in checks.values() if c["required"])
    body = {"ok": ok, "version": VERSION, "ruleset_version": RULESET_VERSION, "checks": checks}
    return body if ok else JSONResponse(Health(**body).model_dump(), status_code=503)
