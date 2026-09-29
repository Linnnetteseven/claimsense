"""
Suggestions for missing patient and practitioner identifiers, from real records only.

Identifiers are never generated (not by Gemini, not by rules): a plausible fake would
attach the claim to the wrong person. Sources, in order:
  - the SHA client / health worker registries, once AfyaLink registry access is set up
    for the pilot (not available yet; see README "Pilot")
  - earlier claims in Hakiki: same patient name and date of birth; practitioners seen
    at the same facility (the HIS roster replaces this during the pilot)

One clear match becomes a one-click fix. Several become a pick list for the officer, who
knows who treated the patient. None gives guidance on where to find the number.
"""

import re
from typing import Optional, Protocol


class Lookups(Protocol):
    def patient_ids(self, claim: dict) -> list[dict]: ...
    def practitioners(self, claim: dict) -> list[dict]: ...


class RepositoryLookups:
    """Lookups over earlier claims in the Hakiki database. Failures return nothing."""

    def __init__(self, repository):
        self.repository = repository

    def patient_ids(self, claim: dict) -> list[dict]:
        try:
            return self.repository.find_patient_ids(
                claim.get("patient_name", ""), claim.get("dob", ""), exclude=claim.get("id", "")
            )
        except Exception:
            return []

    def practitioners(self, claim: dict) -> list[dict]:
        try:
            return self.repository.facility_practitioners(claim.get("facility_code", ""))
        except Exception:
            return []


def _name_words(name: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{3,}", str(name).lower()) if w not in {"doctor", "clinical", "officer"}}


def patient_suggestion(claim: dict, lookups: Lookups) -> dict:
    """Update for the MISSING_FIELDS result when patient_id is missing."""
    name = str(claim.get("patient_name", "")).strip()
    if not name or name.lower().startswith("unknown") or not claim.get("dob"):
        return {"suggestion_note": (
            "Hakiki can only look up the SHA number with the patient's full name and date of birth. "
            "Enter them from the patient file, or ask the patient for the SHA number on their SHA card or SMS."
        )}
    found = lookups.patient_ids(claim)
    source = "Earlier claim for the same name and date of birth"
    if len(found) == 1:
        f = found[0]
        return {
            "suggested_changes": {"patient_id": f["patient_id"]},
            "suggested_label": f"use SHA number {f['patient_id']} from claim {f['claim_number']} ({f['facility_name']})",
            "suggestion_source": source,
        }
    if found:
        return {
            "suggested_choices": [
                {"label": f"{f['patient_id']} (claim {f['claim_number']}, {f['facility_name']})",
                 "changes": {"patient_id": f["patient_id"]}}
                for f in found
            ],
            "suggestion_source": source + ": several found, confirm with the patient",
        }
    return {"suggestion_note": (
        f"No earlier claim for {name} with this date of birth. Ask the patient for the SHA number on "
        "their SHA card or SMS, or look them up in the SHA client registry."
    )}


def practitioner_suggestion(claim: dict, lookups: Lookups) -> dict:
    """Update for the FHIR_BUNDLE_VALID result when the practitioner is missing."""
    roster = lookups.practitioners(claim)
    typed = _name_words(claim.get("practitioner_name", ""))
    source = "Practitioners on earlier claims at this facility"
    if typed:
        matches = [p for p in roster if typed <= _name_words(p["practitioner_name"])]
        if len(matches) == 1:
            m = matches[0]
            return {
                "suggested_changes": {"practitioner_id": m["practitioner_id"], "practitioner_name": m["practitioner_name"]},
                "suggested_label": f"use {m['practitioner_name']}, registry number {m['practitioner_id']}",
                "suggestion_source": source,
            }
        if matches:
            roster = matches
    if roster:
        return {
            "suggested_choices": [
                {"label": f"{p['practitioner_name']} ({p['practitioner_id']})",
                 "changes": {"practitioner_id": p["practitioner_id"], "practitioner_name": p["practitioner_name"]}}
                for p in roster[:10]
            ],
            "suggestion_source": source + ": choose who treated the patient",
        }
    return {"suggestion_note": (
        "No practitioners on record for this facility yet. Enter the treating practitioner's registry "
        "number (PUID) from the patient file or the health worker registry, and their name."
    )}


def prompt_hint(update: dict) -> Optional[str]:
    """What Hakiki can offer, for Gemini to mention; never includes the identifiers themselves."""
    if update.get("suggested_changes"):
        return "Hakiki found a matching record; tell the officer to check it and click Apply fix."
    if update.get("suggested_choices"):
        return "Hakiki shows a short list to choose from; tell the officer to pick the correct one."
    return None
