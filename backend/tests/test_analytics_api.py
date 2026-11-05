from pathlib import Path
import sys

from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import main


class FakeOracleAnalyticsRepository:
    backend_name = "oracle"

    def fetch_analytics_view(self, name):
        sample = {
            "management_kpis": [{"total_claims": 4, "ready_percent": 50,
                                 "ledger_entries": 12, "last_seq": 12,
                                 "last_anchor_at": None, "last_anchor_tx": None,
                                 "unanchored_entries": 12}],
            "claims_by_status": [{"status": "Ready for Submission", "claim_count": 2}],
            "score_by_department": [{"department": "laboratory", "avg_score": 90, "claims": 2}],
            "top_failed_rules": [], "rework_trend_weekly": [],
            "ledger_status": [{"entries": 12, "last_seq": 12}],
            "signoff_progress": [],
        }
        return sample[name]

    def fetch_analytics_status_signoffs(self):
        return {
            "claims_by_status": [{"status": "Ready for Submission", "claim_count": 2}],
            "signoff_progress": [],
        }


def test_management_analytics_endpoint_reads_only_view_results(monkeypatch):
    from db import response_cache
    response_cache.clear()
    monkeypatch.setattr(main, "get_repository", lambda: FakeOracleAnalyticsRepository())

    response = TestClient(main.app).get("/analytics/overview")

    assert response.status_code == 200
    assert response.json()["kpis"]["total_claims"] == 4
    assert response.json()["score_by_department"][0]["department"] == "laboratory"
    assert response.json()["ledger_status"]["entries"] == 12
    assert "claims" not in response.json()["score_by_department"][0] or response.json()["score_by_department"][0]["claims"] == 2


def test_redis_mode_reports_oracle_requirement_and_rejects_unknown_views(monkeypatch):
    class FakeRedisRepository:
        backend_name = "redis"

    monkeypatch.setattr(main, "get_repository", lambda: FakeRedisRepository())
    client = TestClient(main.app)

    response = client.get("/analytics/overview")
    assert response.status_code == 503
    assert response.json()["detail"] == "Analytics requires Oracle backend"
    assert client.get("/analytics/not-a-view").status_code == 404
