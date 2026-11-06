from copy import deepcopy
from datetime import date
from pathlib import Path
import sys

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND.parent / "scripts"))

from db.testing import MemoryRepository
from revalidate_synthetic_claims import revalidate_synthetic_claims
from seed_synthetic_claims import generate_claims
from validation.rules import RULES_DATE, RULES_VERSION


def make_repository():
    repository = MemoryRepository()
    for claim in generate_claims(total=3, today=date(2026, 11, 6)):
        repository.create_claim(claim)
    # A synthetic-looking ID without the persisted flag must never be included.
    excluded = deepcopy(generate_claims(total=1, today=date(2026, 11, 6))[0])
    excluded["id"] = "SYN-CLM-999999"
    excluded["patient_id"] = "SYN-999999"
    excluded["is_synthetic"] = False
    repository.create_claim(excluded)
    return repository


def test_revalidate_writes_versions_rule_metadata_and_verifies_ledger():
    repository = make_repository()
    before_versions = sum(len(rows) for rows in repository.versions.values())

    result = revalidate_synthetic_claims(repository, apply=True)

    assert result["synthetic_claims"] == 3
    assert result["to_revalidate"] == 3
    assert result["applied"] is True
    assert result["ledger_after"]["verified"] is True
    assert result["ready"] + result["review"] + result["blocked"] == 3
    assert sum(len(rows) for rows in repository.versions.values()) == before_versions + 3
    assert all(run["rules_version"] == RULES_VERSION for run in repository.validation_runs)
    assert all(run["rules_date"] == RULES_DATE for run in repository.validation_runs)
    assert sum(event["type"] == "validation" for event in repository.event_payloads) == 3
    assert len(repository.versions["SYN-CLM-000001"]) == 2


def test_preview_does_not_write():
    repository = make_repository()
    before = len(repository.records)
    result = revalidate_synthetic_claims(repository, apply=False)
    assert result["to_revalidate"] == 3
    assert result["applied"] is False
    assert result["ledger_after"] is None
    assert len(repository.records) == before


def test_broken_ledger_stops_before_any_claim_is_changed():
    repository = make_repository()
    version_count = sum(len(rows) for rows in repository.versions.values())
    repository.records[0]["hash"] = "f" * 64

    with pytest.raises(RuntimeError, match="Ledger preflight failed"):
        revalidate_synthetic_claims(repository, apply=True)

    assert sum(len(rows) for rows in repository.versions.values()) == version_count
