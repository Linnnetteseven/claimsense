"""
Hand a Hakiki-validated claim back to the hospital HIS.

Hakiki is a layer: it never submits to SHA. The HIS (or the claims officer using the
SHA provider portal) submits the bundle Hakiki certified. HIS_DELIVERY picks how the
bundle reaches the HIS:

  store    keep it in Hakiki for the HIS to pull (GET /claims/{id}/handoff). Default; demo.
  webhook  POST it to HIS_WEBHOOK_URL (Bearer HIS_WEBHOOK_TOKEN if set).
  openimis POST the FHIR ClaimResponse to openIMIS (the original hackathon target).
"""

import logging

import httpx

from config import config

logger = logging.getLogger(__name__)

MODES = ("store", "webhook", "openimis")


async def deliver(claim: dict, bundle: dict, claim_response: dict) -> tuple[str, dict | None]:
    """Deliver per HIS_DELIVERY. Returns (delivery_status, response_summary)."""
    mode = config.HIS_DELIVERY
    if mode == "store":
        return "stored", None

    if mode == "webhook":
        if not config.HIS_WEBHOOK_URL:
            return "failed", {"error": "HIS_DELIVERY=webhook but HIS_WEBHOOK_URL is not set"}
        headers = {"Content-Type": "application/fhir+json"}
        if config.HIS_WEBHOOK_TOKEN:
            headers["Authorization"] = f"Bearer {config.HIS_WEBHOOK_TOKEN}"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(config.HIS_WEBHOOK_URL, json=bundle, headers=headers)
            ok = resp.is_success
            return ("delivered" if ok else "failed"), {"http_status": resp.status_code, "body": resp.text[:500]}
        except httpx.HTTPError as exc:
            logger.warning("HIS webhook delivery failed for %s: %s", claim.get("id"), exc)
            return "failed", {"error": str(exc)}

    if mode == "openimis":
        from fhir.client import openimis

        try:
            return "delivered", {"openimis": await openimis.post_claim_response(claim_response)}
        except Exception as exc:
            logger.warning("openIMIS delivery failed for %s: %s", claim.get("id"), exc)
            return "failed", {"error": str(exc)}

    return "failed", {"error": f"Unknown HIS_DELIVERY '{mode}'"}
