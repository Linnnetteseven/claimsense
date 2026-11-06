import sys
from pathlib import Path

from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
import main
from config import config


def test_cors_rejects_unconfigured_origin():
    client = TestClient(main.app)
    response = client.options(
        "/",
        headers={
            "Origin": "https://untrusted.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.headers.get("access-control-allow-origin") != "https://untrusted.example"


def test_ussd_requires_secret_when_configured(monkeypatch):
    monkeypatch.setattr(config, "USSD_SHARED_SECRET", "unit-test-secret")
    client = TestClient(main.app)
    response = client.post("/ussd", data={"sessionId": "s", "phoneNumber": "+254700123456", "text": ""})
    assert response.status_code == 401
    accepted = client.post(
        "/ussd",
        data={"sessionId": "s", "phoneNumber": "+254700123456", "text": ""},
        headers={"X-USSD-Secret": "unit-test-secret"},
    )
    assert accepted.status_code == 200


def test_ussd_has_no_secret_requirement_when_unset(monkeypatch):
    monkeypatch.setattr(config, "USSD_SHARED_SECRET", "")
    client = TestClient(main.app)
    response = client.post("/ussd", data={"sessionId": "s", "phoneNumber": "+254700123456", "text": ""})
    assert response.status_code == 200
