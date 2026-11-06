from copy import deepcopy
from pathlib import Path
import sys

from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from audit import chain
import main
from data.mock_claims import MOCK_CLAIMS
from db.testing import MemoryRepository
from validation.rules import RULES_DATE, RULES_VERSION


def setup_client(monkeypatch):
    repository = MemoryRepository()
    claim = deepcopy(MOCK_CLAIMS[0])
    repository.create_claim(claim)
    monkeypatch.setattr(main, "get_repository", lambda: repository)
    monkeypatch.setattr(main, "is_oracle_active", lambda _repository=None: True)
    monkeypatch.setattr(chain, "_repository", lambda: repository)
    monkeypatch.setattr(main.config, "OPENIMIS_TOKEN", "")
    main._session_corrections.clear()
    main._session_claims.clear()
    main._session_lifecycle.clear()
    main._session_versions.clear()
    return TestClient(main.app), repository, claim


def validate(client, claim_id):
    response = client.post(f"/claims/{claim_id}/validate")
    assert response.status_code == 200, response.text
    return response.json()


def submit(client, claim_id):
    response = client.post(f"/claims/{claim_id}/submit")
    assert response.status_code == 200, response.text
    return response.json()


def test_each_validation_creates_immutable_version_and_records_rule_metadata(monkeypatch):
    client, repository, claim = setup_client(monkeypatch)
    result = validate(client, claim["id"])
    next_result = validate(client, claim["id"])

    versions = repository.versions[claim["id"]]
    assert [item["version"] for item in versions] == [1, 2, 3]
    assert next_result["lifecycle"]["version"] == 3
    assert repository.validation_runs[-1]["version"] == 3
    assert repository.validation_runs[-1]["rules_version"] == RULES_VERSION
    assert repository.validation_runs[-1]["rules_date"] == RULES_DATE
    validation_events = [event for event in repository.records if event["type"] == "validation"]
    assert len(validation_events) == 2
    assert result["version_fingerprint"] == versions[-2]["fingerprint"]


def test_new_claim_is_validated_and_versioned_on_receipt(monkeypatch):
    client, repository, claim = setup_client(monkeypatch)
    monkeypatch.setattr(main, "explain_errors", lambda _errors, _claim: ({}, False))
    draft = {key: value for key, value in claim.items() if key != "id"}
    draft["department"] = "outpatient"

    response = client.post("/claims", json=draft)

    assert response.status_code == 200, response.text
    created = response.json()["claim"]
    claim_id = created["id"]
    assert response.json()["validation"]["rules_version"] == RULES_VERSION
    assert response.json()["validation"]["rules_date"] == RULES_DATE
    assert len(repository.versions[claim_id]) == 2
    assert repository.validation_runs[-1]["claim_id"] == claim_id
    assert repository.validation_runs[-1]["version"] == 2
    assert repository.validation_runs[-1]["rules_version"] == RULES_VERSION
    assert [event["type"] for event in repository.event_payloads if event.get("claim_id") == claim_id] == [
        "claim_received", "validation",
    ]




def test_edit_and_department_signoff_stale_ready_claim_until_revalidated(monkeypatch):
    client, repository, claim = setup_client(monkeypatch)
    ready = validate(client, claim["id"])
    assert ready["lifecycle"]["status"] == "ready"

    repository.save_department_review(claim["id"], "outpatient", {"signedOffAt": "2026-11-06T08:00:00Z"})
    assert repository.get_claim_lifecycle(claim["id"])["status"] == "needs_revalidation"
    blocked_submit = client.post(f"/claims/{claim['id']}/submit")
    assert blocked_submit.status_code == 409

    fresh = validate(client, claim["id"])
    assert fresh["lifecycle"]["status"] == "ready"
    assert fresh["lifecycle"]["version"] == 3


def test_submit_uses_latest_validated_snapshot_and_locks_claim(monkeypatch):
    client, repository, claim = setup_client(monkeypatch)
    first = validate(client, claim["id"])
    changed = {**claim, "claimed_amount": 6500}
    corrected = client.post(f"/claims/{claim['id']}/correct", json={"claim": changed})
    assert corrected.status_code == 200, corrected.text
    latest_version = repository.versions[claim["id"]][-1]
    latest_validation = repository.get_latest_validation(claim["id"])
    assert latest_validation["version"] == latest_version["version"]
    assert latest_validation["rules_version"] == RULES_VERSION
    assert latest_validation["rules_date"] == RULES_DATE

    submitted = submit(client, claim["id"])
    assert submitted["version"] == latest_version["version"]
    assert submitted["version_fingerprint"] == latest_version["fingerprint"]
    assert submitted["lifecycle"]["status"] == "submitted"
    submission = [event for event in repository.event_payloads if event["type"] == "submission"][-1]
    assert submission["version"] == latest_version["version"]
    assert submission["version_fingerprint"] == latest_version["fingerprint"]
    assert repository.claims[claim["id"]]["claimed_amount"] == 6500
    assert first["version"] < submitted["version"]

    assert client.post(f"/claims/{claim['id']}/validate").status_code == 409
    assert client.post(f"/claims/{claim['id']}/correct", json={"claim": changed}).status_code == 409
    assert client.post(f"/claims/{claim['id']}/submit").status_code == 409


def test_submitted_readonly_recheck_does_not_change_lock_or_version(monkeypatch):
    client, repository, claim = setup_client(monkeypatch)
    validate(client, claim["id"])
    submitted = submit(client, claim["id"])
    version_count = len(repository.versions[claim["id"]])
    run_count = len(repository.validation_runs)

    response = client.post(f"/claims/{claim['id']}/recheck")
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["validation"]["informational"] is True
    assert result["validation"]["version"] == submitted["version"]
    assert result["lifecycle"]["status"] == "submitted"
    assert len(repository.versions[claim["id"]]) == version_count
    assert len(repository.validation_runs) == run_count + 1
    assert repository.validation_runs[-1]["informational"] is True
    assert repository.get_claim_lifecycle(claim["id"])["status"] == "submitted"


def test_correction_requires_return_or_rejection_or_explicit_reason(monkeypatch):
    client, repository, claim = setup_client(monkeypatch)
    validate(client, claim["id"])
    submit(client, claim["id"])

    unauthorized = client.post(f"/claims/{claim['id']}/correction", json={})
    assert unauthorized.status_code == 422
    rejected = client.post("/outcomes", json={
        "id": "outcome-1", "claimId": claim["id"], "department": claim["department"],
        "outcome": "Returned", "recordedAt": "2026-11-06T08:00:00Z",
    })
    assert rejected.status_code == 422

    outcome = client.post("/outcomes", json={
        "id": "outcome-2", "claimId": claim["id"], "department": claim["department"],
        "outcome": "Returned", "reasonCategory": "Missing documentation",
        "recordedAt": "2026-11-06T08:01:00Z",
    })
    assert outcome.status_code == 200, outcome.text
    assert repository.list_outcomes(claim["id"])[-1]["reasonCategory"] == "Missing documentation"

    correction = client.post(f"/claims/{claim['id']}/correction", json={})
    assert correction.status_code == 200, correction.text
    assert correction.json()["lifecycle"]["status"] == "needs_revalidation"
    assert correction.json()["lifecycle"]["version"] == 3
    assert repository.get_claim_lifecycle(claim["id"])["latest_outcome"] == "Returned"

    # Explicit reason is also sufficient when no payer return is recorded.
    validate(client, claim["id"])
    submit(client, claim["id"])
    reason_correction = client.post(f"/claims/{claim['id']}/correction", json={"reason": "Correct a coding entry"})
    assert reason_correction.status_code == 200


def test_outcome_states_include_accepted_paid_and_rejection_reason(monkeypatch):
    client, repository, claim = setup_client(monkeypatch)
    for index, outcome in enumerate(("Accepted", "Paid")):
        response = client.post("/outcomes", json={
            "id": f"outcome-{index}", "claimId": claim["id"], "department": claim["department"],
            "outcome": outcome, "recordedAt": f"2026-11-06T08:0{index}:00Z",
        })
        assert response.status_code == 200, response.text
    rows = repository.list_outcomes(claim["id"])
    assert [row["outcome"] for row in rows] == ["Accepted", "Paid"]

