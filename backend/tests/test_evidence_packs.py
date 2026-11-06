import json
from pathlib import Path
import sys

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from evidence.packs import build_pdf_summary, evidence_pack_safety_error, store_evidence_pack


def _pack():
    return {
        "synthetic_reference": "SYN-000123",
        "department": "laboratory",
        "generated_at": "2026-11-04T10:00:00+00:00",
        "claim_version_history": [{"version": 1, "fingerprint": "a" * 64, "changed_fields": []}],
        "validation_runs": [{"version": 1, "score": 90, "status": "Needs Review"}],
        "department_signoffs": [{"department": "laboratory", "status": "signed_off"}],
        "ledger_entries": [{"seq": 1, "hash": "b" * 64}],
        "anchors": [],
        "anchor_verification": {"status": "not_anchored"},
    }


def test_local_evidence_pack_writes_json_and_pdf_without_claim_payload(tmp_path, monkeypatch):
    monkeypatch.setenv("EVIDENCE_DIR", str(tmp_path))

    result = store_evidence_pack(_pack())

    json_path = Path(result["json_path"])
    pdf_path = Path(result["pdf_path"])
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert result["storage"] == "local"
    assert pdf_path.read_bytes().startswith(b"%PDF-1.4")
    assert payload["synthetic_reference"] == "SYN-000123"
    assert "patient_name" not in json_path.read_text(encoding="utf-8")


def test_evidence_pack_rejects_raw_or_non_synthetic_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("EVIDENCE_DIR", str(tmp_path))
    unsafe = {**_pack(), "patient_name": "Should never be exported"}

    with pytest.raises(ValueError, match="minimized synthetic-reference"):
        store_evidence_pack(unsafe)
    assert list(tmp_path.iterdir()) == []


def test_oci_mode_falls_back_to_local_and_says_so(tmp_path, monkeypatch):
    monkeypatch.setenv("EVIDENCE_DIR", str(tmp_path))

    result = store_evidence_pack(_pack(), storage="oci")

    assert result["storage"] == "local"
    assert "OCI storage is not enabled" in result["message"]


def test_synthetic_eligibility_uses_flag_and_reference_not_display_name():
    claim = {"is_synthetic": True, "patient_id": "SYN-000123", "patient_name": "Fictional Demo Name"}
    assert evidence_pack_safety_error(claim) is None
    assert evidence_pack_safety_error({**claim, "is_synthetic": False})
    assert evidence_pack_safety_error({**claim, "patient_id": "INS-12345"})


def test_evidence_footer_uses_compact_demo_label_and_contains_no_patient_name():
    pack = _pack()
    rendered = build_pdf_summary(pack)
    assert b"Demo environment: synthetic data" in rendered
    assert b"Fictional Demo Name" not in rendered
