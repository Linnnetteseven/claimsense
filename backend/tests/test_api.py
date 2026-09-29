"""API tests for the correction and demo-reset flow, with Supabase replaced by a fake."""

import copy

import pytest
from fastapi.testclient import TestClient

import main
from data.mock_claims import resolve_date_tokens
from tests.test_validation import _base_claim


class FakeRepository:
    def __init__(self):
        seed = _base_claim(id="SEED-1", visit_date="{{today-1d}}", diagnosis_code="ZZZ999")
        self.rows = {
            "SEED-1": {"claim_data": resolve_date_tokens(seed), "seed_template": seed, "is_seed": True},
        }
        self.handoffs = []

    def get_claim_by_number(self, number):
        row = self.rows.get(number)
        return copy.deepcopy(row["claim_data"]) if row else None

    def list_claims(self):
        return [copy.deepcopy(r["claim_data"]) for r in self.rows.values()]

    def insert_claims(self, claims):
        for c in claims:
            self.rows[c["id"]] = {"claim_data": c, "seed_template": c, "is_seed": False}
        return claims

    def update_claim(self, number, claim):
        self.rows[number]["claim_data"] = claim
        self.rows[number]["status"] = "draft"
        return copy.deepcopy(claim)

    def reset_claim(self, number):
        row = self.rows.get(number)
        return self.update_claim(number, resolve_date_tokens(row["seed_template"])) if row else None

    def record_handoff(self, row):
        self.handoffs.append({**row, "id": f"H-{len(self.handoffs) + 1}", "created_at": "now"})
        self.rows[row["claim_number"]]["status"] = "handed_off"
        return self.handoffs[-1]

    def latest_handoff(self, number):
        return next((h for h in reversed(self.handoffs) if h["claim_number"] == number), None)

    def reset_demo(self):
        removed = [k for k, r in self.rows.items() if not r["is_seed"]]
        for k in removed:
            del self.rows[k]
        for k in self.rows:
            self.reset_claim(k)
        return {"restored": len(self.rows), "removed": len(removed)}


@pytest.fixture
def client(monkeypatch):
    repo = FakeRepository()
    monkeypatch.setattr(main, "claims_repository", lambda: repo)
    monkeypatch.setattr(main, "explain_errors", lambda errors, claim: ({}, False))
    monkeypatch.setattr(main.config, "DEMO_RESET_ENABLED", True)
    return TestClient(main.app), repo


def test_correct_persists_and_revalidates_whole_claim(client):
    api, repo = client
    body = api.post("/claims/SEED-1/correct", json={"diagnosis_code": "CA40.Z"}).json()
    assert body["validation"]["error_count"] == 0
    assert repo.rows["SEED-1"]["claim_data"]["diagnosis_code"] == "CA40.Z"


def test_reset_claim_restores_seed(client):
    api, repo = client
    api.post("/claims/SEED-1/correct", json={"diagnosis_code": "CA40.Z"})
    body = api.post("/claims/SEED-1/reset").json()
    assert body["claim"]["diagnosis_code"] == "ZZZ999"
    assert body["_preview"]["error_count"] == 1


def test_reset_demo_removes_ui_claims(client):
    api, repo = client
    assert api.post("/claims", json=_base_claim(id="UI-1")).status_code == 200
    assert api.post("/demo/reset").json() == {"restored": 1, "removed": 1}
    assert "UI-1" not in repo.rows


def test_create_duplicate_claim_is_rejected(client):
    api, _ = client
    assert api.post("/claims", json=_base_claim(id="SEED-1")).status_code == 409


def test_reset_can_be_disabled(client, monkeypatch):
    api, _ = client
    monkeypatch.setattr(main.config, "DEMO_RESET_ENABLED", False)
    assert api.post("/demo/reset").status_code == 403
    assert api.post("/claims/SEED-1/reset").status_code == 403


def test_create_without_id_generates_one(client):
    api, repo = client
    claim = _base_claim()
    del claim["id"]
    body = api.post("/claims", json=claim).json()
    assert body["claim"]["id"].startswith("SHA-CLM-") and body["claim"]["id"] in repo.rows


def test_bundle_endpoint_runs_checks(client):
    api, _ = client
    body = api.get("/claims/SEED-1/bundle").json()
    assert body["bundle"]["type"] == "message"
    assert body["checks_passed"] is True and body["issues"] == []


def _fix_seed(api):
    api.post("/claims/SEED-1/correct", json={"diagnosis_code": "CA40.Z"})


def test_handoff_blocked_while_errors_remain(client):
    api, repo = client
    assert api.post("/claims/SEED-1/handoff").status_code == 400
    assert repo.handoffs == []


def test_handoff_stores_certified_bundle(client, monkeypatch):
    api, repo = client
    monkeypatch.setattr(main.config, "HIS_DELIVERY", "store")
    _fix_seed(api)
    body = api.post("/claims/SEED-1/handoff").json()
    assert body["handed_off"] and body["delivery_status"] == "stored"
    assert body["sha_bundle"]["type"] == "message"
    assert repo.rows["SEED-1"]["status"] == "handed_off"
    assert api.get("/claims/SEED-1/handoff").json()["bundle"] == body["sha_bundle"]


def test_warnings_must_be_acknowledged(client):
    api, repo = client
    _fix_seed(api)
    api.post("/claims/SEED-1/correct", json={"department": "renal", "sessions_this_week": 5})
    assert api.post("/claims/SEED-1/handoff").status_code == 409
    body = api.post("/claims/SEED-1/handoff", json={"acknowledge_warnings": True}).json()
    assert body["warnings_acknowledged"] == ["IMPLAUSIBLE_FREQUENCY"]


def test_editing_after_handoff_returns_to_draft(client):
    api, repo = client
    _fix_seed(api)
    api.post("/claims/SEED-1/handoff")
    api.post("/claims/SEED-1/correct", json={"diagnosis_description": "edited"})
    assert repo.rows["SEED-1"]["status"] == "draft"


def test_webhook_delivery(client, monkeypatch):
    api, _ = client
    sent = {}

    class FakeAsyncClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None):
            sent.update(url=url, bundle=json, headers=headers)
            import httpx
            return httpx.Response(202, text="accepted", request=httpx.Request("POST", url))

    from his import handoff
    monkeypatch.setattr(handoff.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(main.config, "HIS_DELIVERY", "webhook")
    monkeypatch.setattr(main.config, "HIS_WEBHOOK_URL", "https://his.example/claims")
    monkeypatch.setattr(main.config, "HIS_WEBHOOK_TOKEN", "t0k")
    _fix_seed(api)
    body = api.post("/claims/SEED-1/handoff").json()
    assert body["delivery_status"] == "delivered"
    assert sent["url"] == "https://his.example/claims" and sent["headers"]["Authorization"] == "Bearer t0k"
    assert sent["bundle"]["resourceType"] == "Bundle"
