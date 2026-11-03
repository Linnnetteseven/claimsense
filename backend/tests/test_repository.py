from pathlib import Path
import sys

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from audit import chain
from db.testing import MemoryRepository


def test_five_appends_verify_and_tamper_is_detected(monkeypatch):
    repository = MemoryRepository()
    monkeypatch.setattr(chain, "_repository", lambda: repository)

    for index in range(5):
        chain._append({"type": "validation", "claim_id": "synthetic-claim", "score": 90 - index})

    records = chain.all_records()
    assert len(records) == 5
    assert chain.verify_records(records)["verified"] is True

    tampered = [dict(row) for row in records]
    tampered[2]["payload_hash"] = "f" * 64
    assert chain.verify_records(tampered)["verified"] is False


def test_repository_keeps_claim_versions_and_review_state(monkeypatch):
    repository = MemoryRepository()
    monkeypatch.setattr(chain, "_repository", lambda: repository)
    original = {"id": "SYN-001", "patient_name": "Synthetic Patient", "claimed_amount": 9000}
    repository.create_claim(original)
    changed = {**original, "claimed_amount": 7500}

    repository.record_claim_correction(original["id"], original, changed)
    state = {"completed": {"Discharge summary": True}, "signedOffAt": "2026-01-01T00:00:00Z"}
    repository.save_department_review(original["id"], "outpatient", state)

    assert repository.get_claim(original["id"])["claimed_amount"] == 7500
    assert [version["version"] for version in repository.versions[original["id"]]] == [1, 2]
    assert repository.verify_current_claim_version(original["id"], changed)["status"] == "matches"
    assert repository.get_department_review(original["id"], "outpatient") == state
