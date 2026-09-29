"""USSD flow against a fake claim lookup; SMS body privacy."""

import pytest
from fastapi import BackgroundTasks

from config import config
from data.mock_claims import load_demo_claims
from ussd import handler
from ussd.sms_sender import build_sms_body, mask_phone
from validation.engine import validate

CLAIMS = {c["id"]: c for c in load_demo_claims()}
PHONE = "+254711000111"


@pytest.fixture(autouse=True)
def open_access(monkeypatch):
    monkeypatch.setattr(config, "USSD_ALLOWED_PHONES", set())


def dial(text, phone=PHONE, lookup=CLAIMS.get, tasks=None):
    return handler.handle_ussd_session("s1", phone, text, tasks or BackgroundTasks(), lookup)


def test_menu():
    assert dial("").startswith("CON Welcome to Hakiki")


def test_claim_summary_from_database_without_patient_name():
    screen = dial("1*sha-clm-2026-004")
    claim = CLAIMS["SHA-CLM-2026-004"]
    assert screen.startswith("CON SHA-CLM-2026-004") and "Score: 80/100 | REVIEW" in screen
    assert claim["patient_name"] not in screen and len(screen) <= 160


def test_handed_off_status_shown():
    claim = {**CLAIMS["SHA-CLM-2026-001"], "_status": "handed_off"}
    assert "Handed off to HIS" in dial("1*SHA-CLM-2026-001", lookup=lambda _: claim)


def test_not_found():
    assert "not found" in dial("1*NOPE")


def test_database_down():
    def boom(_):
        raise RuntimeError("timeout")
    assert "unavailable" in dial("1*SHA-CLM-2026-001", lookup=boom)


def test_sms_queued_in_background():
    tasks = BackgroundTasks()
    screen = dial("1*SHA-CLM-2026-004*1", tasks=tasks)
    assert screen.startswith("END") and len(tasks.tasks) == 1


def test_allow_list(monkeypatch):
    monkeypatch.setattr(config, "USSD_ALLOWED_PHONES", {"+254722000222"})
    assert "not registered" in dial("1*SHA-CLM-2026-001")
    assert dial("", phone="254722000222").startswith("CON")  # + lost in form decoding


def test_sms_body_has_no_patient_name_and_lists_warnings():
    claim = CLAIMS["SHA-CLM-2026-006"]
    body = build_sms_body(claim, validate(claim))
    assert claim["patient_name"] not in body
    assert "WARNINGS:" in body and "Score: 70/100" in body


def test_mask_phone():
    assert mask_phone("+254711000111") == "+254******111"
