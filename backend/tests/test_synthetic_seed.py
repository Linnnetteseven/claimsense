from datetime import date
from pathlib import Path
import sys

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND.parent / "scripts"))

from audit import chain
from db.testing import MemoryRepository
from seed_synthetic_claims import generate_claims, seed_repository
from validation.engine import validate
from validation.rules import RULES_DATE, RULES_VERSION


def test_generated_claims_have_expected_bands_and_synthetic_refs():
    claims = generate_claims(today=date(2026, 11, 4))
    assert len(claims) == 250
    assert all(claim["is_synthetic"] for claim in claims)
    assert all(claim["patient_id"].startswith("SYN-") for claim in claims)
    assert all(claim["facility_name"] == "Kerugoya Level 5 Hospital" for claim in claims)
    assert all("patient_name" not in claim for claim in claims)
    assert {claim["department"] for claim in claims} == {"outpatient", "renal", "maternity"}
    assert {department: sum(claim["department"] == department for claim in claims)
            for department in ("outpatient", "renal", "maternity")} == {
                "outpatient": 150, "renal": 50, "maternity": 50,
            }
    assert all(0 <= (date(2026, 11, 4) - date.fromisoformat(claim["_created_at"][:10])).days < 84 for claim in claims)
    groups = {name: [c for c in claims if c["_seed_group"] == name] for name in ("ready", "review", "high_risk")}
    assert [len(groups[name]) for name in ("ready", "review", "high_risk")] == [138, 75, 37]
    for name, expected in (("ready", lambda score: score >= 85),
                           ("review", lambda score: 60 <= score <= 84),
                           ("high_risk", lambda score: score < 60)):
        assert all(expected(validate(claim)["score"]) for claim in groups[name])
    assert sum(1 for claim in claims if claim["_seed_group"] == "high_risk") == 37


def test_seed_is_idempotent_records_versions_and_verifies_chain(monkeypatch):
    repository = MemoryRepository()
    monkeypatch.setattr(chain, "_repository", lambda: repository)

    first = seed_repository(repository, total=21, today=date(2026, 11, 4))
    second = seed_repository(repository, total=21, today=date(2026, 11, 4))

    assert first["added"] == 21
    assert second["added"] == 0
    assert first["chain_verified"] is True
    assert first["ready"] + first["review"] + first["blocked"] == 21
    assert chain.verify_records(repository.all_ledger_records())["verified"] is True
    assert sum(len(versions) > 1 for versions in repository.versions.values()) == 21
    assert sum(len(versions) == 4 for versions in repository.versions.values()) == 7
    assert len(repository.reviews) == 21


def test_reseed_uses_correction_and_validation_write_paths_without_names(monkeypatch):
    repository = MemoryRepository()
    monkeypatch.setattr(chain, "_repository", lambda: repository)
    seed_repository(repository, total=10, today=date(2026, 11, 4))

    result = seed_repository(repository, total=10, today=date(2026, 11, 4), reseed=True)

    assert result["updated"] == 10
    assert result["chain_verified"] is True
    assert {claim["department"] for claim in repository.list_claims()} == {"outpatient", "renal", "maternity"}
    assert all("patient_name" not in claim for claim in repository.list_claims())
    assert all("patient_name" not in version["payload"]
               for versions in repository.versions.values() for version in versions)
    assert all("patient_name" not in payload
               for payload in repository.event_payloads)


def test_lifecycle_event_types_cover_claim_journey(monkeypatch):
    repository = MemoryRepository()
    monkeypatch.setattr(chain, "_repository", lambda: repository)
    claim = next(item for item in generate_claims(total=15, today=date(2026, 11, 4))
                 if item["_seed_group"] == "ready")
    claim.pop("_seed_group", None)
    claim_id = claim["id"]
    repository.create_claim(claim)
    result = validate(claim)
    result.update({"rules_version": RULES_VERSION, "rules_date": RULES_DATE})
    repository.record_validation(claim_id, claim, result)
    corrected = {**claim, "diagnosis_description": "Updated synthetic description"}
    repository.record_claim_correction(claim_id, claim, corrected)
    result = validate(corrected)
    result.update({"rules_version": RULES_VERSION, "rules_date": RULES_DATE})
    repository.record_validation(claim_id, corrected, result)
    repository.record_event({"type": "department_signed_off", "claim_id": claim_id})
    repository.record_submission(claim_id, corrected, "mocked")
    repository.save_outcome({"id": "OUT-1", "claimId": claim_id, "outcome": "accepted"})

    types = {event["type"] for event in repository.event_payloads}
    assert {"claim_received", "validation", "claim_corrected", "department_signed_off",
            "submission", "claim_outcome_recorded"}.issubset(types)
    assert chain.verify_records(repository.all_ledger_records())["verified"] is True


def test_seed_preflight_failure_does_not_write_claims(monkeypatch):
    repository = MemoryRepository()
    monkeypatch.setattr(chain, "_repository", lambda: repository)
    repository.create_claim(generate_claims(total=1, today=date(2026, 11, 4))[0])
    repository.records[0]["hash"] = "f" * 64
    versions_before = sum(len(versions) for versions in repository.versions.values())

    import pytest
    with pytest.raises(RuntimeError, match="Ledger preflight failed"):
        seed_repository(repository, total=1, today=date(2026, 11, 4), reseed=True)

    assert sum(len(versions) for versions in repository.versions.values()) == versions_before
