"""Read-only timing and metadata diagnostics for Oracle ledger tables."""
from __future__ import annotations

from pathlib import Path
import os
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

import oracledb

USER = os.getenv("ORACLE_USER", "")
PASSWORD = os.getenv("ORACLE_PASSWORD", "")
DSN = os.getenv("ORACLE_DSN", "")
WALLET = os.getenv("ORACLE_WALLET_DIR", "")
WALLET_PASSWORD = os.getenv("ORACLE_WALLET_PASSWORD", "")


def connect(dsn: str):
    options = {"user": USER, "password": PASSWORD, "dsn": dsn}
    if WALLET:
        options.update(config_dir=WALLET, wallet_location=WALLET,
                       wallet_password=WALLET_PASSWORD or None)
    return oracledb.connect(**options)


def timed(conn, label: str, sql: str, params=None):
    start = time.perf_counter()
    with conn.cursor() as cur:
        cur.arraysize = 500
        cur.execute(sql, params or {}, fetch_lobs=False)
        rows = cur.fetchall()
    print({"test": label, "duration_ms": round((time.perf_counter()-start)*1000, 1),
           "rows": len(rows), "first_rows": rows[:5]})
    return rows


def main():
    aliases = []
    for suffix in ("low", "tp", "high"):
        if DSN.lower().endswith("_" + suffix):
            aliases.append((suffix, DSN))
        elif DSN.lower().endswith("_low"):
            aliases.append((suffix, DSN[:-4] + "_" + suffix))
    print({"dsn_aliases": [alias for alias, _dsn in aliases]})
    for alias, dsn in aliases:
        try:
            conn = connect(dsn)
            with conn:
                timed(conn, f"{alias}: audit_ledger count", "SELECT COUNT(*) FROM audit_ledger")
                timed(conn, f"{alias}: audit_event_details count", "SELECT COUNT(*) FROM audit_event_details")
                timed(conn, f"{alias}: ledger columns only",
                      "SELECT seq, claim_ref, event_type, payload_hash, prev_hash, hash, chain_version, created_at FROM audit_ledger ORDER BY seq")
                timed(conn, f"{alias}: details columns only",
                      "SELECT event_seq, details_json FROM audit_event_details ORDER BY event_seq")
                timed(conn, f"{alias}: ledger/details join",
                      "SELECT l.seq, l.claim_ref, l.event_type, l.payload_hash, l.prev_hash, l.hash, l.chain_version, l.created_at, d.details_json FROM audit_ledger l LEFT JOIN audit_event_details d ON d.event_seq=l.seq ORDER BY l.seq")
                timed(conn, f"{alias}: table columns",
                      "SELECT table_name, column_name, data_type, data_length, char_used FROM user_tab_columns WHERE table_name IN ('AUDIT_LEDGER','AUDIT_EVENT_DETAILS') ORDER BY table_name, column_id")
                timed(conn, f"{alias}: join indexes",
                      "SELECT i.table_name, i.index_name, i.uniqueness, c.column_name, c.column_position FROM user_indexes i JOIN user_ind_columns c ON c.index_name=i.index_name AND c.table_name=i.table_name WHERE i.table_name IN ('AUDIT_LEDGER','AUDIT_EVENT_DETAILS') ORDER BY i.table_name,i.index_name,c.column_position")
                with conn.cursor() as cur:
                    cur.execute("EXPLAIN PLAN FOR SELECT l.seq, l.claim_ref, l.event_type, l.payload_hash, l.prev_hash, l.hash, l.chain_version, l.created_at, d.details_json FROM audit_ledger l LEFT JOIN audit_event_details d ON d.event_seq=l.seq ORDER BY l.seq")
                    cur.execute("SELECT plan_table_output FROM TABLE(DBMS_XPLAN.DISPLAY())")
                    print({"test": f"{alias}: explain plan", "plan": [row[0] for row in cur.fetchall()]})
            conn.close()
        except Exception as exc:
            print({"service": alias, "error_type": type(exc).__name__, "error": str(exc)[:300]})


if __name__ == "__main__":
    main()
