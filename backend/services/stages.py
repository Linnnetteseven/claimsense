"""
Where a claim is in its life, for the queue views.

  todo      needs the officer: errors or warnings, or SHA sent it back / rejected it
  ready     no errors or warnings, not yet handed off
  with_sha  handed off to the HIS; waiting for SHA's answer (or SHA is still reviewing)
  closed    SHA approved, paid or cancelled it; read-only, kept for audit

The frontend mirrors this in src/constants/stages.js.
"""

STAGES = ("todo", "ready", "with_sha", "closed")
CLOSED_SHA_STATES = {"approved", "payment_processing", "paid", "cancelled"}


def claim_stage(claim: dict, preview: dict) -> str:
    sha = claim.get("_sha_state") or {}
    if sha:
        if sha.get("action_needed"):
            return "todo"
        if sha.get("state") in CLOSED_SHA_STATES:
            return "closed"
        return "with_sha"
    if claim.get("_status") == "handed_off":
        return "with_sha"
    if preview["error_count"] == 0 and preview["warning_count"] == 0:
        return "ready"
    return "todo"
