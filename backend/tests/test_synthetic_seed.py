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


def test_generated_claims_have_expected_bands_and_synthetic_refs():
    claims = generate_claims(today=date(2026, 11, 4))
    assert len(claims) == 250
    assert all(claim["is_synthetic"] for claim in claims)
    assert all(claim["patient_id"].startswith("SYN-") for claim in claims)
    assert all(claim["facility_name"] == "Kerugoya County Referral Hospital (SYNTHETIC DEMO)" for claim in claims)
    assert {claim["department"] for claim in claims} == {
        "outpatient", "inpatient", "maternity", "laboratory", "pharmacy", "radiology", "surgical",
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
    assert chain.verify_records(repository.all_ledger_records())["verified"] is True
    assert sum(len(versions) > 1 for versions in repository.versions.values()) == 7
    assert len(repository.reviews) == 21
