"""
Department-specific SOP context injected into the Gemini explanation prompt.

To add a new department: add an entry to DEPARTMENT_SOPS. No other code
changes needed — explainer.py picks this up automatically based on
claim["department"].
"""

from typing import Optional

DEPARTMENT_SOPS = {
    "maternity": (
        "This is a MATERNITY claim. Facility SOP requires: a partograph reference ID, "
        "the delivery mode (vaginal / assisted / C-section), and gestation week. "
        "Maternal complications (e.g. PPH, eclampsia) must be coded separately from the delivery code."
    ),
    "renal": (
        "This is a RENAL/DIALYSIS claim. Facility SOP requires: dialysis session count for the "
        "billing period, latest creatinine or eGFR reading, and vascular access type "
        "(fistula / graft / catheter). Frequency above 3x/week needs a clinical note."
    ),
    "surgical": (
        "This is a SURGICAL claim. Facility SOP requires: the procedure code must match the "
        "signed consent form, theatre time and anaesthesia type must be itemised, and post-op "
        "notes are required for any overnight stay."
    ),
    "outpatient": (
        "This is an OUTPATIENT claim. Facility SOP requires: a single primary diagnosis per visit "
        "(split multi-issue visits into separate claims), and dispensed medication should align "
        "with the coded diagnosis."
    ),
}


def get_department_context(department: Optional[str]) -> str:
    if not department:
        return ""
    return DEPARTMENT_SOPS.get(department.strip().lower(), "")