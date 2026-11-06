"""Fixed read-only SELECT statements over the shared analytics views."""

VIEW_QUERIES = {
    "claims_by_status": "SELECT status, claim_count FROM v_claims_by_status ORDER BY status",
    "score_by_department": "SELECT department, avg_score, claims FROM v_score_by_department ORDER BY department",
    "top_failed_rules": "SELECT rule_id, rule_name, failures FROM v_top_failed_rules ORDER BY failures DESC, rule_id",
    "rework_trend_weekly": "SELECT week_start, claims, reworked, rework_rate FROM v_rework_trend_weekly ORDER BY week_start",
    "ledger_status": "SELECT entries, last_seq, last_anchor_at, last_anchor_tx, unanchored_entries FROM v_ledger_status",
    "signoff_progress": "SELECT department, pending, signed_off FROM v_signoff_progress ORDER BY department",
    "management_kpis": "SELECT total_claims, ready_percent, rework_rate, ledger_entries, last_seq, last_anchor_at, last_anchor_tx, unanchored_entries FROM v_management_kpis",
}


def fetch_view_rows(cursor, view_name: str) -> list[dict]:
    """Execute only a named, source-controlled view query and return dictionaries."""
    query = VIEW_QUERIES.get(view_name)
    if query is None:
        raise ValueError("Unknown analytics view")
    cursor.execute(query)
    columns = [column[0].lower() for column in cursor.description]
    rows = []
    for row in cursor.fetchall():
        rows.append({key: (value.isoformat() if hasattr(value, "isoformat") else value)
                     for key, value in zip(columns, row)})
    return rows
