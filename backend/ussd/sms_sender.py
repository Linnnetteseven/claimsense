"""
Sends a detailed claim validation report via SMS using Africa's Talking SDK.

Initialised lazily so dotenv has already loaded by the time we read env vars.
In sandbox mode (AT_USERNAME=sandbox), SMS lands in the AT simulator inbox.
"""

import logging
import os
import africastalking

from config import config

logger = logging.getLogger("hakiki.sms")


def _get_sms_service():
    """Initialise AT SDK on first use — reads env vars after dotenv has loaded."""
    api_key = os.getenv("AT_API_KEY", "")
    username = os.getenv("AT_USERNAME", "sandbox")

    if not api_key:
        logger.warning("AT_API_KEY not set — SMS sending disabled")
        return None

    africastalking.initialize(username, api_key)
    logger.info("Africa's Talking SMS initialised (username=%s)", username)
    return africastalking.SMS


def mask_phone(phone_number: str) -> str:
    """For logs: keep the country code and last 3 digits only."""
    return phone_number[:4] + "*" * max(0, len(phone_number) - 7) + phone_number[-3:]


def build_sms_body(claim: dict, result: dict) -> str:
    """Claim ID, facility and results. Never the patient's name (SMS can be read by others)."""
    claim_id = claim.get("id", "N/A")
    status = {"green": "READY", "amber": "REVIEW", "red": "ERRORS"}.get(result["color"], "UNKNOWN")

    lines = [
        f"[Hakiki] {claim_id}",
        str(claim.get("facility_name") or claim.get("facility_code") or ""),
        f"Score: {result['score']}/100 | {status}",
        "",
    ]

    errors = result.get("errors", [])
    warnings = result.get("warnings", [])

    if errors:
        lines.append("ERRORS (fix before submit):")
        for i, err in enumerate(errors[:3], 1):
            msg = err.get("message", "Unknown error")
            lines.append(f"{i}. {msg[:50]}" if len(msg) > 50 else f"{i}. {msg}")

    if warnings:
        lines.append("")
        lines.append("WARNINGS:")
        for warn in warnings[:2]:
            msg = warn.get("message", "")
            lines.append(f"- {msg[:50]}" if len(msg) > 50 else f"- {msg}")

    lines += ["", "Fix and hand off:", config.FRONTEND_URL]
    return "\n".join(lines)


def send_claim_report_sms(phone_number: str, claim: dict, result: dict) -> None:
    """
    Send claim validation report SMS.
    Called as a FastAPI BackgroundTask — failures are logged, not raised.
    """
    sms = _get_sms_service()
    if not sms:
        return

    body = build_sms_body(claim, result)
    try:
        sms.send(body, [phone_number])
        logger.info("SMS report for %s sent to %s", claim.get("id"), mask_phone(phone_number))
    except Exception as exc:
        logger.error("SMS send failed for %s: %s", mask_phone(phone_number), exc)
