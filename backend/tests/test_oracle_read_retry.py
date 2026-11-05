from contextlib import contextmanager
from pathlib import Path
import sys

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from db import connection
from db.oracle_impl import OracleRepository


class FakeCursor:
    def __init__(self, fail):
        self.fail = fail

    def execute(self, *_args, **_kwargs):
        if self.fail:
            self.fail = False
            raise RuntimeError("DPY-4011: connection was unexpectedly closed")

    def fetchall(self):
        return [('{"id":"SYN-CLM-000001"}',)]

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class FakeConnection:
    def __init__(self, fail):
        self.fail = fail
        self.dropped = False

    def cursor(self):
        return FakeCursor(self.fail)

    def drop(self):
        self.dropped = True


class FakePool:
    def __init__(self):
        self.connections = []

    @contextmanager
    def acquire(self):
        conn = FakeConnection(fail=not self.connections)
        self.connections.append(conn)
        yield conn


def test_list_claims_retries_once_after_dropped_connection(monkeypatch):
    pool = FakePool()
    monkeypatch.setattr(connection, "_pool", None)
    monkeypatch.setattr("db.oracle_impl.get_pool", lambda: connection._TrackedPool(pool))

    claims = OracleRepository().list_claims()

    assert claims == [{"id": "SYN-CLM-000001"}]
    assert len(pool.connections) == 2
    assert pool.connections[0].dropped is True
    assert pool.connections[1].dropped is False
