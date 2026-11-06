import sys
from pathlib import Path
from contextlib import contextmanager

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from db import connection
from db.oracle_impl import OracleRepository


class Cursor:
    arraysize = 1
    description = []

    def __init__(self):
        self.sql = []
        self.kwargs = []

    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def execute(self, sql, *args, **kwargs):
        self.sql.append(sql)
        self.kwargs.append(kwargs)
    def fetchall(self): return []


class Conn:
    def __init__(self): self.cursor_obj = Cursor()
    def cursor(self): return self.cursor_obj


class Pool:
    def __init__(self): self.conn = Conn()
    @contextmanager
    def acquire(self): yield self.conn


def test_all_ledger_records_uses_one_joined_lob_safe_query(monkeypatch):
    pool = Pool()
    monkeypatch.setattr(connection, "_pool", pool)

    assert OracleRepository().all_ledger_records() == []
    cursor = pool.conn.cursor_obj
    assert len(cursor.sql) == 1
    assert "LEFT JOIN audit_event_details" in cursor.sql[0]
    assert cursor.kwargs[0]["fetch_lobs"] is False
    assert cursor.arraysize == 500
