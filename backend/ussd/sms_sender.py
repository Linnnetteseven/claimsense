"""
Sends a detailed claim validation report via SMS using Africa's Talking SDK.

Initialised lazily so dotenv has already loaded by the time we read env vars.
In sandbox mode (AT_USERNAME=sandbox), SMS lands in the AT simulator inbox.
"""

import logging
import os
import africastalking

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


def _build_sms_body(claim: dict, result: dict) -> str:
    claim_id = claim.get("id", "N/A")
    patient = claim.get("patient_name", "Unknown")
    score = result["score"]
    color = result["color"]
    status = {"green": "READY", "amber": "REVIEW", "red": "ERRORS"}.get(color, "UNKNOWN")

    lines = [
        f"[Hakiki] {claim_id}",
        f"Patient: {patient}",
        f"Score: {score}/100 | {status}",
        "",
    ]

    errors = [e for e in result.get("errors", []) if e.get("severity") == "error"]
    warnings = [e for e in result.get("errors", []) if e.get("severity") == "warning"]

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

    lines += ["", "Review & submit:", "claimsense-frontend.vercel.app"]
    return "\n".join(lines)


def send_claim_report_sms(phone_number: str, claim: dict, result: dict) -> None:
    """
    Send claim validation report SMS.
    Called as a FastAPI BackgroundTask — failures are logged, not raised.
    """
    sms = _get_sms_service()
    if not sms:
        return

    body = _build_sms_body(claim, result)
    try:
        response = sms.send(body, [phone_number], sender_id="Hakiki")
        logger.info("SMS sent to %s: %s", phone_number, response)
    except Exception as exc:
        logger.error("SMS send failed for %s: %s", phone_number, exc)
