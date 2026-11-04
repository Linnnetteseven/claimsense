from pathlib import Path
import re


VIEWS_SQL = Path(__file__).resolve().parents[1] / "db" / "views.sql"


def test_analytics_views_define_all_requested_aggregate_shapes():
    sql = VIEWS_SQL.read_text(encoding="utf-8").lower()
    expected = {
        "v_claims_by_status": ("status", "claim_count"),
        "v_score_by_department": ("department", "avg_score", "claims"),
        "v_top_failed_rules": ("rule_id", "rule_name", "failures"),
        "v_rework_trend_weekly": ("week_start", "claims", "reworked", "rework_rate"),
        "v_ledger_status": ("entries", "last_seq", "last_anchor_at", "last_anchor_tx", "unanchored_entries"),
        "v_signoff_progress": ("department", "pending", "signed_off"),
        "v_management_kpis": ("total_claims", "ready_percent", "rework_rate", "ledger_entries"),
    }
    for view, columns in expected.items():
        assert re.search(rf"create\s+or\s+replace\s+view\s+{view}\s+as", sql)
        view_sql = sql.split(f"create or replace view {view} as", 1)[1].split("create or replace view", 1)[0]
        for column in columns:
            assert re.search(rf"\bas\s+{column}\b", view_sql)


def test_metrics_are_limited_to_synthetic_claim_payloads():
    sql = VIEWS_SQL.read_text(encoding="utf-8").lower()
    assert sql.count("json_value(c.payload, '$.is_synthetic') = 'true'") >= 5
    assert "patient_name" not in sql
    assert "patient_id" not in sql
