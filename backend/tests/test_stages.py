"""Claim lifecycle stages for the queue views."""

import pytest

from services.stages import claim_stage

CLEAN = {"error_count": 0, "warning_count": 0}
ERRORS = {"error_count": 2, "warning_count": 0}
WARNS = {"error_count": 0, "warning_count": 1}


def sha(state, action=False):
    return {"state": state, "action_needed": action}


@pytest.mark.parametrize("claim,preview,stage", [
    ({}, ERRORS, "todo"),
    ({}, WARNS, "todo"),
    ({}, CLEAN, "ready"),
    ({"_status": "handed_off"}, CLEAN, "with_sha"),
    ({"_status": "handed_off", "_sha_state": sha("in_review")}, CLEAN, "with_sha"),
    ({"_status": "handed_off", "_sha_state": sha("sent_back", True)}, CLEAN, "todo"),
    ({"_status": "handed_off", "_sha_state": sha("rejected", True)}, CLEAN, "todo"),
    ({"_status": "handed_off", "_sha_state": sha("approved")}, CLEAN, "closed"),
    ({"_status": "handed_off", "_sha_state": sha("paid")}, CLEAN, "closed"),
])
def test_stage(claim, preview, stage):
    assert claim_stage(claim, preview) == stage
