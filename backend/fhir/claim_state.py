"""
Read SHA's claim-state extension from a ClaimResponse and map it to Hakiki workflow states.

Two vocabularies are in use:
  - AfyaLink claim integration guide (ClaimResponse claim-state extension): queued, approved,
    rejected, in-review, clinical-review, sent-for-payment-processing, sent-to-surveillance,
    payment-completed, payment-declined
  - DHA eClaims IG CodeSystem claim-state-cs: sent-back, approved, canceled, pending, under-review
Both map onto one set of workflow states; the original code and system are kept.
"""

from typing import Optional

# workflow state -> (label, officer needs to act?)
WORKFLOW_STATES = {
    "queued": ("Queued at SHA", False),
    "in_review": ("Under review", False),
    "clinical_review": ("Clinical review", False),
    "surveillance": ("Sent to surveillance", False),
    "approved": ("Approved", False),
    "sent_back": ("Sent back: fix and resubmit", True),
    "rejected": ("Rejected", True),
    "cancelled": ("Cancelled", False),
    "payment_processing": ("Sent for payment", False),
    "paid": ("Payment completed", False),
    "payment_declined": ("Payment declined", True),
    "unknown": ("Unknown state", True),
}

_CODE_TO_STATE = {
    # AfyaLink
    "queued": "queued",
    "approved": "approved",
    "rejected": "rejected",
    "in-review": "in_review",
    "clinical-review": "clinical_review",
    "sent-for-payment-processing": "payment_processing",
    "sent-to-surveillance": "surveillance",
    "payment-completed": "paid",
    "payment-declined": "payment_declined",
    # DHA eClaims IG
    "sent-back": "sent_back",
    "canceled": "cancelled",
    "cancelled": "cancelled",
    "pending": "queued",
    "under-review": "in_review",
}


def _state_coding(claim_response: dict) -> Optional[dict]:
    """The coding of the claim-state extension, whichever URL variant SHA used."""
    for ext in claim_response.get("extension") or []:
        url = str(ext.get("url", ""))
        if url.rstrip("/").endswith(("claim-state-extension", "eclaim-state-extension", "claim-state")):
            codings = (ext.get("valueCodeableConcept") or {}).get("coding") or []
            if codings:
                return codings[0]
            if ext.get("valueCode"):
                return {"code": ext["valueCode"]}
    return None


def parse_claim_state(claim_response: dict) -> Optional[dict]:
    """
    Return {state, label, action_needed, sha_code, sha_system} for a ClaimResponse,
    or None when it carries no claim-state extension.
    """
    coding = _state_coding(claim_response)
    if not coding:
        return None
    code = str(coding.get("code", "")).strip().lower()
    state = _CODE_TO_STATE.get(code, "unknown")
    label, action = WORKFLOW_STATES[state]
    return {
        "state": state,
        "label": label if state != "unknown" else f"Unknown SHA state '{code}'",
        "action_needed": action,
        "sha_code": code,
        "sha_system": coding.get("system"),
    }
