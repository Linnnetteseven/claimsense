"""Seed a synthetic 12-week Kerugoya workload into the selected Oracle DB.

All identifiers, references, and clinical records created by this script are
synthetic. It never calls Gemini or openIMIS. Run from the repo root with
DB_BACKEND=oracle and the Oracle connection variables configured.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from audit.chain import verify_records  # noqa: E402
from db.factory import configured_backend, get_repository  # noqa: E402
from validation.engine import validate  # noqa: E402

FACILITY = "Kerugoya County Referral Hospital (SYNTHETIC DEMO)"
DEPARTMENTS = ("outpatient", "inpatient", "maternity", "laboratory", "pharmacy", "radiology", "surgical")
DIAGNOSES = {
    "outpatient": ("J18.9", "E11.9", "K29.7", "I10"),
    "inpatient": ("J18.9", "K35.8", "E11.9", "N39.0"),
    "maternity": ("O80", "O82", "O26.9", "O99.0"),
    "laboratory": ("D64.9", "E11.9", "N18.6", "J18.9"),
    "pharmacy": ("E11.9", "I10", "J18.9", "K59.0"),
    "radiology": ("S09.9", "J18.9", "K35.8", "M54.5"),
    "surgical": ("K35.8", "K40.9", "S52.5", "N20.0"),
}
SERVICE_CODES = {
    "outpatient": "SYN-OPD-CONSULT", "inpatient": "SYN-IPD-CARE",
    "maternity": "SYN-MAT-DELIVERY", "laboratory": "SYN-LAB-CBC",
    "pharmacy": "SYN-PHARM-DISPENSE", "radiology": "SYN-RAD-IMAGE",
    "surgical": "SYN-SURG-PROCEDURE",
}


def _baseline(index: int, department: str, received: date, rng: random.Random) -> dict:
    patient_ref = f"SYN-{index:06d}"
    maternity = department == "maternity"
    surgical = department == "surgical"
    amount = rng.randrange(1800, 12500, 100)
    claim = {
        "id": f"SYN-CLM-{index:06d}", "is_synthetic": True,
        "patient_id": patient_ref, "patient_name": f"Synthetic patient {patient_ref}",
        "facility_code": "KRG-L5-SYN", "facility_name": FACILITY,
        "department": department, "visit_date": received.isoformat(),
        "diagnosis_code": rng.choice(DIAGNOSES[department]),
        "diagnosis_description": f"Synthetic {department} service episode",
        "coverage_start_date": "2024-01-01", "coverage_end_date": "2028-12-31",
        "items": [{"service_code": SERVICE_CODES[department],
                   "description": f"Synthetic {department} service", "quantity": 1,
                   "unit_price": amount}],
        "claimed_amount": amount, "scheme_code": "SYNTHETIC-DEMO",
        "_created_at": datetime.combine(received, datetime.min.time(), timezone.utc).isoformat(),
    }
    if maternity:
        claim.update({"partograph_id": f"SYN-PARTO-{index:06d}", "is_delivery": True})
    if surgical:
        claim.update({"overnight_stay": True, "postop_notes_attached": f"SYN-POSTOP-{index:06d}"})
    return claim


def _with_status(claim: dict, group: str, index: int) -> dict:
    result = deepcopy(claim)
    if group == "review":
        # Two warning-only checks: amount differs from lines and exceeds the
        # current internal review heuristic. These are demo heuristics only.
        threshold = 160_000 if result["department"] == "maternity" else 60_000
        result["items"] = [{"service_code": SERVICE_CODES.get(result["department"], "SYN-REN-DIALYSIS"),
                            "description": "Synthetic review service", "quantity": 1,
                            "unit_price": int(threshold * .8)}]
        result["claimed_amount"] = threshold
    elif group == "high_risk":
        result["facility_code"] = ""
        result["diagnosis_code"] = "SYNTHETIC-INVALID"
        result["items"] = []
    result["_seed_group"] = group
    return result


def generate_claims(total: int = 250, seed: int = 20261104, today: date | None = None) -> list[dict]:
    """Return a deterministic workload with 55/30/15 final score bands."""
    if total < 1:
        raise ValueError("total must be positive")
    today = today or date.today()
    rng = random.Random(seed)
    ready_count = round(total * .55)
    review_count = round(total * .30)
    high_count = total - ready_count - review_count
    groups = ["ready"] * ready_count + ["review"] * review_count + ["high_risk"] * high_count
    rng.shuffle(groups)
    claims = []
    for index, group in enumerate(groups, 1):
        department = DEPARTMENTS[(index - 1) % len(DEPARTMENTS)]
        received = today - timedelta(days=rng.randrange(4, 84))
        claim = _with_status(_baseline(index, department, received, rng), group, index)
        claims.append(claim)
    return claims


def _initial_rework_version(final_claim: dict) -> dict:
    initial = deepcopy(final_claim)
    initial.pop("_seed_group", None)
    initial["facility_code"] = ""
    initial["diagnosis_code"] = "SYNTHETIC-INVALID"
    initial["items"] = []
    initial["coverage_end_date"] = "2020-01-01"
    return initial


def seed_repository(repository, total: int = 250, seed: int = 20261104, today: date | None = None) -> dict:
    """Idempotently append new synthetic claims and their audit events."""
    existing = {str(c.get("id")): c for c in repository.list_claims()}
    claims = generate_claims(total=total, seed=seed, today=today)
    added = 0
    for index, final_claim in enumerate(claims, 1):
        claim_id = final_claim["id"]
        if claim_id in existing:
            if not existing[claim_id].get("is_synthetic"):
                raise ValueError(f"Refusing to overwrite non-synthetic claim {claim_id}")
            continue
        group = final_claim.pop("_seed_group")
        initial = _initial_rework_version(final_claim) if index % 3 == 0 else final_claim
        repository.create_claim(initial)
        first_result = validate(initial)
        received_at = datetime.fromisoformat(initial["_created_at"])
        first_result["recorded_at"] = (received_at + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        repository.record_validation(claim_id, initial, first_result)
        if initial is not final_claim:
            corrected_at = datetime.fromisoformat(final_claim["_created_at"]) + timedelta(days=1)
            final_claim["_corrected_at"] = corrected_at.strftime("%Y-%m-%dT%H:%M:%SZ")
            repository.record_claim_correction(claim_id, initial, final_claim)
            final_claim.pop("_corrected_at", None)
            final_result = validate(final_claim)
            final_result["recorded_at"] = (corrected_at + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
            repository.record_validation(claim_id, final_claim, final_result)
        else:
            final_result = first_result
        # Different sign-off states, all unmistakably synthetic.
        state = index % 4
        review = {"completedChecks": [], "evidenceReferences": {}, "note": "Synthetic demo review"}
        if state != 0:
            review["reviewer"] = "Synthetic demo officer"
        if state == 1:
            review["signedOffBy"] = "Synthetic demo officer"
            review["signedOffAt"] = (today or date.today()).isoformat() + "T12:00:00Z"
        repository.save_department_review(claim_id, final_claim["department"], review)
        added += 1
    records = repository.all_ledger_records()
    integrity = verify_records(records)
    if not integrity.get("verified"):
        raise RuntimeError(f"Audit chain verification failed at record {integrity.get('broken_at')}")
    return {"added": added, "existing": len(claims) - added, "total": len(claims),
            "chain_verified": True}


def reset_synthetic_rows(repository) -> int:
    """Delete synthetic app rows, keeping the append-only audit ledger intact."""
    from db.connection import get_pool

    with get_pool().acquire() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM claims WHERE JSON_VALUE(payload, '$.is_synthetic') = 'true'")
            ids = [row[0] for row in cursor.fetchall()]
            if not ids:
                return 0
            # Bind every identifier; ledger entries remain to preserve history.
            for claim_id in ids:
                binds = {"claim_id": claim_id}
                for table in ("claim_outcomes", "validation_runs", "claim_versions", "department_signoffs"):
                    cursor.execute(f"DELETE FROM {table} WHERE claim_id = :claim_id", binds)
                cursor.execute("DELETE FROM claims WHERE id = :claim_id", binds)
            connection.commit()
    return len(ids)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true", help="delete only rows whose claim payload is_synthetic=true")
    parser.add_argument("--count", type=int, default=250)
    args = parser.parse_args()
    if configured_backend() != "oracle":
        parser.error("Set DB_BACKEND=oracle; this seed script must not seed Redis or mock mode")
    repository = get_repository()
    if args.reset:
        removed = reset_synthetic_rows(repository)
        print(f"Removed {removed} synthetic claims and their dependent app rows; audit history retained.")
    print(seed_repository(repository, total=args.count))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
