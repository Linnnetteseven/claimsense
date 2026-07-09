"""
Hakiki USSD session handler.

Africa's Talking sends a POST with these fields on every user action:
  sessionId    — unique per dial session
  phoneNumber  — caller's number (e.g. +254711XXXXXX)
  networkCode  — MNO code
  serviceCode  — the shortcode dialled
  text         — CUMULATIVE user inputs, separated by * (empty on first dial)

We respond with plain text:
  CON <message>  — keep session alive, show message
  END <message>  — close session, show message

Character limit: 160 chars per screen (safe across all networks).
"""

from fastapi import BackgroundTasks
from data.mock_claims import MOCK_CLAIMS
from validation.engine import validate
from ussd.sms_sender import send_claim_report_sms

# In-memory session store — sufficient for demo (USSD sessions complete in <3 min)
_session_store: dict[str, dict] = {}


def _get_claim(claim_id: str) -> dict | None:
    return next((c for c in MOCK_CLAIMS if c["id"].upper() == claim_id.upper()), None)


def _format_status(color: str) -> str:
    return {"green": "READY", "amber": "REVIEW", "red": "ERRORS"}.get(color, "UNKNOWN")


def _normalize_phone(phone_number: str) -> str:
    """Fix + sign lost in URL form encoding — AT sends +254... but form decode turns + to space."""
    phone_number = phone_number.strip()
    if not phone_number.startswith("+"):
        phone_number = "+" + phone_number
    return phone_number


def handle_ussd_session(
    session_id: str,
    phone_number: str,
    text: str,
    background_tasks: BackgroundTasks,
) -> str:
    phone_number = _normalize_phone(phone_number)

    # Parse cumulative input into navigation steps
    steps = [s.strip() for s in text.split("*")] if text.strip() else []

    # ── SCREEN 1: Main menu ────────────────────────────────────────────────
    if not steps or steps == [""]:
        _session_store.pop(session_id, None)
        return (
            "CON Welcome to Hakiki\n"
            "SHA Claims Validator\n\n"
            "1. Check claim\n"
            "0. Exit"
        )

    level1 = steps[0]

    # ── Exit ───────────────────────────────────────────────────────────────
    if level1 == "0":
        return (
            "END Thank you for using Hakiki.\n"
            "Submit ready claims at:\n"
            "claimsense-frontend.vercel.app"
        )

    # ── Option 1: Check claim ──────────────────────────────────────────────
    if level1 == "1":

        # SCREEN 2: Ask for claim ID
        if len(steps) == 1:
            return (
                "CON Enter Claim ID:\n"
                "e.g. SHA-CLM-2026-001"
            )

        claim_id = steps[1].upper().strip()

        # SCREEN 3: Show validation result
        if len(steps) == 2:
            claim = _get_claim(claim_id)

            if not claim:
                return (
                    f"END Claim {claim_id} not found.\n"
                    "Check the ID and try again.\n"
                    "claimsense-frontend.vercel.app"
                )

            result = validate(claim)
            score = result["score"]
            status = _format_status(result["color"])
            errors = result["error_count"]
            warnings = result["warning_count"]

            name = claim.get("patient_name", "Unknown")
            if len(name) > 14:
                name = name[:13] + "."

            _session_store[session_id] = {"claim_id": claim_id}

            return (
                f"CON {claim_id} | {name}\n"
                f"Score: {score}/100 | {status}\n"
                f"Errors: {errors} | Warns: {warnings}\n\n"
                "1. Send SMS report\n"
                "0. Back to menu"
            )

        # SCREEN 4: Act on choice after seeing result
        if len(steps) == 3:
            level3 = steps[2]

            if level3 == "0":
                _session_store.pop(session_id, None)
                return (
                    "CON Welcome to Hakiki\n"
                    "SHA Claims Validator\n\n"
                    "1. Check claim\n"
                    "0. Exit"
                )

            if level3 == "1":
                claim = _get_claim(claim_id)
                if not claim:
                    return "END Error retrieving claim.\nTry again later."

                result = validate(claim)

                # Send SMS in background so USSD response stays under 10s
                background_tasks.add_task(
                    send_claim_report_sms,
                    phone_number=phone_number,
                    claim=claim,
                    result=result,
                )

                _session_store.pop(session_id, None)
                return (
                    f"END Report sent to\n"
                    f"{phone_number}\n\n"
                    "Check your messages.\n"
                    "- Hakiki"
                )

    # ── Fallback ───────────────────────────────────────────────────────────
    return "END Invalid option.\nDial again to retry."
