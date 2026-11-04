from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from db.select_ai import validate_generated_select
import main


def test_generated_select_accepts_only_analytics_views():
    sql = 'SELECT department, avg_score FROM HAKIKI_APP.V_SCORE_BY_DEPARTMENT ORDER BY avg_score DESC'
    assert validate_generated_select(sql) == sql


@pytest.mark.parametrize("sql", [
    "SELECT * FROM claims",
    "DELETE FROM v_claims_by_status",
    "SELECT * FROM HAKIKI_APP.CLAIMS",
    "SELECT * FROM dual",
    "SELECT * FROM HAKIKI_APP.V_CLAIMS_BY_STATUS; DROP TABLE claims",
    "SELECT * FROM HAKIKI_APP.V_CLAIMS_BY_STATUS, HAKIKI_APP.CLAIMS",
    "SELECT * FROM HAKIKI_APP.V_CLAIMS_BY_STATUS CROSS APPLY HAKIKI_APP.CLAIMS",
])
def test_generated_select_rejects_base_tables_and_non_select_sql(sql):
    with pytest.raises(ValueError):
        validate_generated_select(sql)


def test_select_ai_endpoint_is_disabled_by_default(monkeypatch):
    monkeypatch.setattr(main.config, "ENABLE_SELECT_AI", False)

    response = TestClient(main.app).post("/analytics/ask", json={"question": "count claims by status"})

    assert response.status_code == 503
    assert response.json()["detail"] == "Experimental Oracle Select AI is disabled"
