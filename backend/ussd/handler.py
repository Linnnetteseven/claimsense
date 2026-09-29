"""
Hakiki USSD session handler (Africa's Talking).

AT posts on every key press: sessionId, phoneNumber, serviceCode and text, where
text holds ALL inputs so far separated by '*' (empty on first dial). We answer
"CON <screen>" to continue or "END <screen>" to close; keep screens under 160 chars.

Claims are read from the database through the lookup the router passes in.
Privacy: screens and SMS carry the claim ID, facility and results, never the
patient's name. USSD_ALLOWED_PHONES limits access to registered officers' numbers
(set it for the pilot; empty = open, for demos).
"""

import logging
from typing import Callable, Optional

from fastapi import BackgroundTasks

from config import config
from ussd.sms_sender import mask_phone, send_claim_report_sms
from validation.engine import validate

logger = logging.getLogger("hakiki.ussd")

Lookup = Callable[[str], Optional[dict]]

MENU = "CON Welcome to Hakiki\nSHA Claims Validator\n\n1. Check claim\n0. Exit"
_STATUS = {"green": "READY", "amber": "REVIEW", "red": "ERRORS"}


def normalize_phone(phone_number: str) -> str:
    """AT sends +254...; form decoding can turn the + into a space."""
    phone_number = phone_number.strip()
    return phone_number if phone_number.startswith("+") else "+" + phone_number


def allowed(phone_number: str) -> bool:
    return not config.USSD_ALLOWED_PHONES or phone_number in config.USSD_ALLOWED_PHONES


def _summary(claim_id: str, claim: dict, result: dict) -> str:
    facility = str(claim.get("facility_name") or claim.get("facility_code") or "")[:22]
    lines = [
        f"CON {claim_id}",
        facility,
        f"Score: {result['score']}/100 | {_STATUS.get(result['color'], 'UNKNOWN')}",
        f"Errors: {result['error_count']} | Warns: {result['warning_count']}",
    ]
    if claim.get("_status") == "handed_off":
        lines.append("Handed off to HIS")
    lines += ["", "1. SMS report", "0. Menu"]
    return "\n".join(line for line in lines if line is not None)


def handle_ussd_session(
    session_id: str,
    phone_number: str,
    text: str,
    background_tasks: BackgroundTasks,
    lookup: Lookup,
) -> str:
    phone_number = normalize_phone(phone_number)
    if not allowed(phone_number):
        logger.warning("USSD refused for unregistered number %s", mask_phone(phone_number))
        return "END This number is not registered for Hakiki.\nAsk your claims supervisor to add it."

    steps = [s.strip() for s in text.split("*")] if text.strip() else []
    if not steps:
        return MENU
    if steps[0] == "0":
        return f"END Thank you for using Hakiki.\nFix and hand off claims at:\n{config.FRONTEND_URL}"
    if steps[0] != "1":
        return "END Invalid option.\nDial again to retry."
    if len(steps) == 1:
        return "CON Enter Claim ID:\ne.g. SHA-CLM-2026-001"

    claim_id = steps[1].upper()
    try:
        claim = lookup(claim_id)
    except Exception:
        logger.exception("USSD claim lookup failed")
        return "END Hakiki is unavailable right now.\nPlease try again shortly."
    if not claim:
        return f"END Claim {claim_id[:30]} not found.\nCheck the ID and try again."
    result = validate(claim)

    if len(steps) == 2:
        return _summary(claim_id, claim, result)
    if len(steps) == 3 and steps[2] == "0":
        return MENU
    if len(steps) == 3 and steps[2] == "1":
        # In the background so the USSD reply stays inside AT's time limit.
        background_tasks.add_task(send_claim_report_sms, phone_number=phone_number, claim=claim, result=result)
        return f"END Report for {claim_id} sent by SMS.\n- Hakiki"
    return "END Invalid option.\nDial again to retry."
