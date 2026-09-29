"""
Hakiki backend: FastAPI entry point (Vercel runs this module).

Routers (api/routers/):
  health      GET /  (liveness), GET /health (dependencies)
  claims      GET/POST /claims, GET /claims/{id}, POST /claims/{id}/correct,
              GET /claims/{id}/history, POST /claims/{id}/reset, POST /demo/reset
  validation  POST /claims/{id}/validate, POST /validate, GET /claims/{id}/audit, GET /audit/verify
  fhir        GET /claims/{id}/bundle, POST /claims/{id}/handoff (/submit alias), GET /claims/{id}/handoff
  ussd        POST /ussd

Errors always have the shape {"error": {"code", "message", "details"}} (api/errors.py).
Routes are plain functions: FastAPI runs them in a worker thread, so a slow database
or Gemini call does not block other requests.
"""

from dotenv import load_dotenv

load_dotenv()

import logging  # noqa: E402
from contextlib import asynccontextmanager  # noqa: E402

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from api import errors  # noqa: E402
from api.routers import claims, fhir, health, ussd, validation  # noqa: E402
from config import config  # noqa: E402
from validation.rules import RULESET_VERSION  # noqa: E402

logging.basicConfig(
    level=logging.DEBUG if config.DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("hakiki")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Hakiki %s starting; ruleset %s", health.VERSION, RULESET_VERSION)
    logger.info(
        "Gemini: %s",
        f"{config.GEMINI_MODEL} (fallback {config.GEMINI_FALLBACK_MODEL})"
        if config.llm_enabled else "disabled, set GEMINI_API_KEY",
    )
    logger.info("HIS delivery: %s; demo reset %s", config.HIS_DELIVERY,
                "on" if config.DEMO_RESET_ENABLED else "off")
    yield


app = FastAPI(
    title="Hakiki API",
    description="Pre-submission checks for SHA claims. Scores come from deterministic rules; "
                "Gemini only explains.",
    version=health.VERSION,
    lifespan=lifespan,
)

# CORS: only our frontend (production, local dev, this team's Vercel previews) may call
# the API from a browser. Server-to-server callers (the HIS, Africa's Talking) are not
# affected by CORS. Authentication, not CORS, is what will protect the data.
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_origin_regex=config.CORS_ORIGIN_REGEX or None,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key"],
    max_age=600,
)

errors.install(app)
for module in (health, claims, validation, fhir, ussd):
    app.include_router(module.router)
