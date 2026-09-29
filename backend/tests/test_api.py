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
        self.runs = []
        self.corrections = []

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

    def record_validation_run(self, number, result):
        self.runs.append((number, result["score"], result["ruleset_version"]))

    def record_corrections(self, number, before, after, source="manual"):
        changed = [f for f in set(before) | set(after)
                   if not f.startswith("_") and f != "id" and before.get(f) != after.get(f)]
        self.corrections += [(number, f, before.get(f), after.get(f), source) for f in sorted(changed)]
        return len(changed)

    def history(self, number):
        return {"validation_runs": [r for r in self.runs if r[0] == number],
                "corrections": [c for c in self.corrections if c[0] == number]}

    def ping(self):
        if getattr(self, "down", False):
            raise RuntimeError("unreachable")

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
    import api.deps
    import services.pipeline
    monkeypatch.setattr(api.deps, "_repository", lambda: repo)
    monkeypatch.setattr(services.pipeline, "explain_errors", lambda errors, claim, targets=None: ({}, False))
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


def test_validation_runs_and_corrections_are_recorded(client):
    api, repo = client
    api.post("/claims/SEED-1/validate")
    api.post("/claims/SEED-1/correct?source=suggestion:%20WHO%20map", json={"diagnosis_code": "CA40.Z"})
    assert [r[1] for r in repo.runs] == [80, 100]
    assert repo.corrections == [("SEED-1", "diagnosis_code", "ZZZ999", "CA40.Z", "suggestion: WHO map")]
    history = api.get("/claims/SEED-1/history").json()
    assert len(history["validation_runs"]) == 2 and len(history["corrections"]) == 1


def test_health_reports_dependencies(client, monkeypatch):
    from api.routers import health
    api, repo = client
    monkeypatch.setitem(health.CHECKS, "sha_uat", (lambda: (True, "HTTP 200"), False))
    monkeypatch.setitem(health.CHECKS, "upstash", (lambda: (None, "not configured"), False))
    body = api.get("/health").json()
    assert body["ok"] is True and body["checks"]["supabase"]["ok"] is True
    assert body["checks"]["upstash"]["ok"] is None and body["ruleset_version"]


def test_health_is_503_when_database_is_down(client, monkeypatch):
    from api.routers import health
    api, repo = client
    monkeypatch.setitem(health.CHECKS, "sha_uat", (lambda: (True, "HTTP 200"), False))
    repo.down = True
    resp = api.get("/health")
    assert resp.status_code == 503 and resp.json()["checks"]["supabase"]["detail"] == "unreachable"


def test_optional_dependency_down_keeps_health_ok(client, monkeypatch):
    from api.routers import health
    api, _ = client

    def boom():
        raise RuntimeError("timeout")
    monkeypatch.setitem(health.CHECKS, "sha_uat", (boom, False))
    body = api.get("/health").json()
    assert body["ok"] is True and body["checks"]["sha_uat"]["ok"] is False


def test_errors_have_one_shape(client):
    api, _ = client
    missing = api.get("/claims/NOPE").json()
    assert missing == {"error": {"code": "not_found", "message": "Claim 'NOPE' not found", "details": None}}
    bad = api.post("/claims", json={"items": "not a list"})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "invalid_request"
    assert bad.json()["error"]["details"][0]["field"] == "items"


def test_handoff_warnings_error_lists_rules(client):
    api, _ = client
    _fix_seed(api)
    api.post("/claims/SEED-1/correct", json={"department": "renal", "sessions_this_week": 5})
    body = api.post("/claims/SEED-1/handoff").json()
    assert body["error"]["code"] == "warnings_not_acknowledged"
    assert body["error"]["details"] == ["IMPLAUSIBLE_FREQUENCY"]


def test_liveness_touches_no_dependency(client):
    api, repo = client
    repo.down = True
    assert api.get("/").json()["status"] == "running"


@pytest.mark.parametrize("origin,allowed", [
    ("https://claimsense-frontend.vercel.app", True),
    ("http://localhost:5173", True),
    ("https://claimsense-frontend-e9orcpw0l-mugwanjalk-gmailcoms-projects.vercel.app", True),
    ("https://claimsense-frontend-evil.vercel.app", False),
    ("https://example.com", False),
])
def test_cors_only_allows_our_frontends(client, origin, allowed):
    api, _ = client
    resp = api.options("/claims", headers={"Origin": origin, "Access-Control-Request-Method": "POST"})
    assert (resp.headers.get("access-control-allow-origin") == origin) is allowed
    assert resp.headers.get("access-control-allow-credentials") is None
