from contextlib import contextmanager
from pathlib import Path
import logging
import sys

from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from db import connection, response_cache
from db.oracle_impl import OracleRepository
import main


class _Cursor:
    description = []
    rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, *_args, **_kwargs):
        self.rowcount = 1

    def executemany(self, *_args, **_kwargs):
        self.rowcount = 1

    def fetchone(self):
        return None

    def fetchall(self):
        return []


class _Connection:
    def cursor(self, *_args, **_kwargs):
        return _Cursor()


class _Pool:
    @contextmanager
    def acquire(self, *_args, **_kwargs):
        yield _Connection()


class _BatchCursor(_Cursor):
    def __init__(self, pool):
        self.pool = pool

    def execute(self, sql, *_args, **_kwargs):
        self.pool.sql.append(sql)
        if "audit_ledger_head" in sql:
            self.pool.fetchone_result = (0, "0" * 16)
        elif "SELECT id FROM claims" in sql:
            self.pool.fetchall_result = []

    def fetchone(self):
        result = self.pool.fetchone_result
        self.pool.fetchone_result = None
        return result

    def fetchall(self):
        result = self.pool.fetchall_result or []
        self.pool.fetchall_result = None
        return result


class _BatchConnection:
    def __init__(self, pool):
        self.pool = pool

    def cursor(self, *_args, **_kwargs):
        return _BatchCursor(self.pool)

    def commit(self):
        pass

    def rollback(self):
        pass


class _BatchPool:
    def __init__(self):
        self.sql = []
        self.fetchone_result = None
        self.fetchall_result = None

    @contextmanager
    def acquire(self, *_args, **_kwargs):
        yield _BatchConnection(self)


class _OracleRepo:
    backend_name = "oracle"

    @staticmethod
    def _one_query():
        with connection.get_pool().acquire() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1 FROM dual")

    def sync_claims(self, _claims):
        self._one_query()  # batched existence probe; batch inserts are tested separately

    def list_claim_queue(self, limit=50):
        self._one_query()
        return 1, [{
            "id": "SYN-CLM-000001", "patient_name": "Synthetic Patient",
            "patient_id": "SYN-000001", "facility_name": "Demo Facility",
            "department": "outpatient", "visit_date": "2026-11-04",
            "is_synthetic": True, "_preview": {"score": 100, "status": "Ready for Submission",
                                                  "color": "green", "error_count": 0,
                                                  "warning_count": 0},
            "_validation_payload": None,
        }][:limit]

    def get_claim(self, _claim_id):
        self._one_query()
        return {"id": "SYN-CLM-000001", "patient_name": "Synthetic Patient",
                "department": "outpatient", "items": []}

    def get_claim_audit(self, _claim_id, claim=None, limit=50):
        self._one_query()
        return {"history": [], "current_version": {"status": "not_recorded"}}

    def fetch_analytics_view(self, name):
        self._one_query()
        if name == "management_kpis":
            return [{"total_claims": 1, "ready_percent": 100, "rework_rate": 0,
                     "ledger_entries": 1, "last_seq": 1, "last_anchor_at": None,
                     "last_anchor_tx": None, "unanchored_entries": 1}]
        return []

    def fetch_analytics_status_signoffs(self):
        self._one_query()
        return {"claims_by_status": [], "signoff_progress": []}


def test_oracle_intake_sync_batches_n_claims_in_three_round_trips(monkeypatch):
    pool = _BatchPool()
    monkeypatch.setattr(connection, "_pool", pool)
    response_cache.clear()

    OracleRepository().sync_claims([{
        "id": "SYN-CLM-000001", "patient_name": "Synthetic Patient",
        "is_synthetic": True, "_created_at": "2026-11-04T00:00:00+00:00",
    }])

    assert len(pool.sql) == 3
    assert "SELECT id FROM claims" in pool.sql[1]
    assert "JSON_TABLE" in pool.sql[2]
    assert "INSERT INTO audit_ledger" in pool.sql[2]


def test_main_oracle_reads_stay_within_five_sql_calls(monkeypatch, caplog):
    repository = _OracleRepo()
    monkeypatch.setattr(connection, "_pool", _Pool())
    monkeypatch.setattr(main, "get_repository", lambda: repository)
    monkeypatch.setattr(main, "config", type("Config", (), {"use_mock": True})())
    response_cache.clear()
    caplog.set_level(logging.INFO, logger="claimsense.main")
    client = TestClient(main.app)

    paths = [
        "/claims",
        "/claims/SYN-CLM-000001",
        "/claims/SYN-CLM-000001/audit",
        "/analytics/overview",
        "/analytics/claims_by_status",
        "/analytics/score_by_department",
        "/analytics/top_failed_rules",
        "/analytics/rework_trend_weekly",
        "/analytics/ledger_status",
        "/analytics/signoff_progress",
    ]
    for path in paths:
        response = client.get(path)
        assert response.status_code == 200, (path, response.text)
        assert int(response.headers["X-SQL-Query-Count"]) <= 5, path

    metric_lines = [record.message for record in caplog.records if "HTTP GET" in record.message]
    assert len(metric_lines) == len(paths)
    assert all("duration_ms=" in line and "sql_queries=" in line for line in metric_lines)
