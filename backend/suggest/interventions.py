"""
Shortlist SHA intervention codes that fit a claim, for suggesting a missing or wrong code.

Every candidate is valid for the claim by construction (catalogue rules below), so
whatever is picked from the list cannot fail the catalogue rules. Ranking uses the
diagnosis link, words shared with the item's description, and the department.
Gemini may choose among the top candidates (llm/explainer.py); it cannot add codes.
"""

import re
from dataclasses import dataclass
from datetime import date
from typing import Optional

from data.sha_tariffs import Intervention, interventions
from validation.rules import _parse_date, billable_period

_DEPARTMENT_CHAPTERS = {
    "maternity": ("SHA-08", "SHA-07-005"),
    "renal": ("SHA-16",),
    "surgical": ("SHA-19",),
    "medical": ("SHA-07-001",),
    "outpatient": ("SHA-12",),
}
_STOP = {"with", "without", "other", "services", "service", "management", "unspecified", "care", "per", "day"}


@dataclass
class Candidate:
    info: Intervention
    score: float
    quantity: int
    unit_price: Optional[float]  # official tariff for the level when OCL has one

    def as_prompt_line(self) -> str:
        price = f"tariff KES {self.unit_price:,.0f}" if self.unit_price is not None else "no published tariff"
        return f"{self.info.code}: {self.info.description} ({self.info.payment_mechanism.lower()}, {price})"


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{4,}", str(text).lower()) if w not in _STOP}


def _age(claim: dict) -> Optional[int]:
    dob, visit = _parse_date(claim.get("dob")), _parse_date(claim.get("visit_date"))
    if not dob or not visit:
        return None
    return visit.year - dob.year - ((visit.month, visit.day) < (dob.month, dob.day))


def _fits(info: Intervention, claim: dict, setting: str, level: str, age, sex, phc: bool) -> bool:
    if level and not info.allowed_at_level(level):
        return False
    if info.access_point in ("IP", "OP") and info.access_point != setting:
        return False
    if info.gender in ("FEMALE", "MALE") and sex and sex != info.gender:
        return False
    if age is not None and ((info.min_age and age < info.min_age) or (info.max_age and age > info.max_age)):
        return False
    if phc != (info.payment_mechanism == "CAPITATION"):
        return False
    if info.code.startswith("PMF") != str(claim.get("scheme_code", "")).upper().startswith("PMF"):
        return False
    return "-SI-" not in info.code  # sub-interventions are billed under their parent


def shortlist(claim: dict, item: Optional[dict] = None, limit: int = 6) -> list[Candidate]:
    from fhir.kenya_bundle_builder import claim_subtype

    setting = "IP" if claim_subtype(claim) == "inpatient" else "OP"
    level = str(claim.get("facility_level") or "").strip()
    sex = {"F": "FEMALE", "M": "MALE"}.get(str(claim.get("gender", "")).strip().upper()[:1])
    phc = str(claim.get("fund", "")).strip().upper() == "PHC"
    age = _age(claim)
    diagnosis = str(claim.get("diagnosis_code", "")).strip()
    wanted = _words((item or {}).get("description", "")) | _words(claim.get("diagnosis_description", ""))
    chapters = _DEPARTMENT_CHAPTERS.get(str(claim.get("department", "")).strip().lower(), ())
    start, end = billable_period(claim)
    days = max(1, (end - start).days) if start and end and end > start else 1

    ranked = []
    for info in interventions().values():
        if not _fits(info, claim, setting, level, age, sex, phc):
            continue
        linked = info.diagnosis_matches(diagnosis) if diagnosis else None
        if linked is False:
            continue
        score = 3.0 * bool(linked)
        score += 2.0 * len(wanted & _words(info.description))
        score += 1.0 * any(info.code.startswith(c) for c in chapters)
        if score <= 0:
            continue
        tariff = info.level_tariffs.get(level) if level else None
        quantity = days if info.payment_mechanism == "PER DIEM" else 1
        ranked.append(Candidate(info, score, quantity, 0.0 if phc else tariff))
    ranked.sort(key=lambda c: (-c.score, c.info.code))
    return ranked[:limit]


def item_from(candidate: Candidate, claim: dict, sequence: int, base: Optional[dict] = None) -> dict:
    """A claim item for a candidate, keeping what the officer already entered where it still fits."""
    start, end = billable_period(claim)
    base = dict(base or {})
    item = {
        **base,
        "sequence": base.get("sequence") or sequence,
        "service_code": candidate.info.code,
        "description": base.get("description") or candidate.info.description,
        "quantity": base.get("quantity") or candidate.quantity,
        "service_start": base.get("service_start") or (start.isoformat() if start else ""),
        "service_end": base.get("service_end") or (end.isoformat() if end else ""),
    }
    if candidate.unit_price is not None:
        item["unit_price"] = candidate.unit_price
    elif "unit_price" not in base:
        item["unit_price"] = 0
    return item


def today() -> date:
    return date.today()
