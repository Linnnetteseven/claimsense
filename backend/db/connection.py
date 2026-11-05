"""Lazy python-oracledb thin-mode connection pool for Autonomous Database."""
from __future__ import annotations

import os
import logging
from pathlib import Path
from threading import Lock
from typing import Any
from contextvars import ContextVar, Token
from contextlib import contextmanager

_pool: Any | None = None
_pool_lock = Lock()
_request_sql_lock = Lock()
logger = logging.getLogger(__name__)
_request_sql_count: ContextVar[list[int] | None] = ContextVar("request_sql_count", default=None)


def begin_sql_query_tracking() -> Token:
    return _request_sql_count.set([0])


def finish_sql_query_tracking(token: Token) -> int:
    counter = _request_sql_count.get()
    with _request_sql_lock:
        count = counter[0] if counter else 0
    _request_sql_count.reset(token)
    return count


def _count_sql_call() -> None:
    counter = _request_sql_count.get()
    if counter is not None:
        with _request_sql_lock:
            counter[0] += 1


_RETRYABLE_ORACLE_CODES = ("DPY-4011", "DPY-1001", "ORA-03113", "ORA-03114", "ORA-03135", "DPI-1067", "DPI-1080")


def is_retryable_read_error(exc: Exception) -> bool:
    """Recognize dropped-connection and call-timeout errors safe for read retry."""
    message = str(exc).upper()
    if any(code in message for code in _RETRYABLE_ORACLE_CODES):
        return True
    return "TIMEOUT" in type(exc).__name__.upper() or "TIMED OUT" in message


class _TrackedCursor:
    def __init__(self, cursor: Any, connection: Any):
        object.__setattr__(self, "_cursor", cursor)
        object.__setattr__(self, "_connection", connection)

    def _call(self, name, *args, **kwargs):
        try:
            return getattr(self._cursor, name)(*args, **kwargs)
        except Exception as exc:
            if is_retryable_read_error(exc):
                self._connection.drop()
            raise

    def __setattr__(self, name, value):
        if name == "_cursor":
            object.__setattr__(self, name, value)
        else:
            setattr(self._cursor, name, value)

    def execute(self, *args, **kwargs):
        _count_sql_call()
        return self._call("execute", *args, **kwargs)

    def executemany(self, *args, **kwargs):
        _count_sql_call()
        return self._call("executemany", *args, **kwargs)

    def fetchone(self):
        return self._call("fetchone")

    def fetchall(self):
        return self._call("fetchall")

    def fetchmany(self, *args, **kwargs):
        return self._call("fetchmany", *args, **kwargs)

    def __enter__(self):
        self._cursor.__enter__()
        return self

    def __exit__(self, *args):
        return self._cursor.__exit__(*args)

    def __getattr__(self, name):
        return getattr(self._cursor, name)


class _TrackedConnection:
    def __init__(self, connection: Any):
        self._connection = connection
        # Bound a hung Oracle round trip so callers can surface an error or
        # retry a safe read instead of waiting on a dead socket indefinitely.
        self._connection.call_timeout = 30000

    def cursor(self, *args, **kwargs):
        return _TrackedCursor(self._connection.cursor(*args, **kwargs), self)

    def drop(self):
        """Discard a broken pooled connection instead of returning it idle."""
        drop = getattr(self._connection, "drop", None)
        if drop:
            return drop()
        return self._connection.close()

    def __getattr__(self, name):
        return getattr(self._connection, name)


class _TrackedPool:
    def __init__(self, pool: Any):
        self._pool = pool

    @contextmanager
    def acquire(self, *args, **kwargs):
        with self._pool.acquire(*args, **kwargs) as connection:
            yield _TrackedConnection(connection)

    def __getattr__(self, name):
        return getattr(self._pool, name)


def connection_mode() -> str:
    """Return the configured Oracle transport without exposing connection details."""
    return "wallet_mtls" if os.getenv("ORACLE_WALLET_DIR", "").strip() else "walletless_tls"


def get_pool():
    """Create the pool once per process. python-oracledb defaults to Thin mode."""
    global _pool
    if _pool is not None:
        return _TrackedPool(_pool)
    with _pool_lock:
        if _pool is not None:
            return _TrackedPool(_pool)
        import oracledb

        user = os.getenv("ORACLE_USER", "").strip()
        password = os.getenv("ORACLE_PASSWORD", "")
        dsn = os.getenv("ORACLE_DSN", "").strip()
        wallet_dir = os.getenv("ORACLE_WALLET_DIR", "").strip()
        wallet_password = os.getenv("ORACLE_WALLET_PASSWORD", "")
        if not all((user, password, dsn)):
            raise RuntimeError("Oracle database configuration is incomplete")

        # No init_oracle_client call: both transports use python-oracledb Thin mode.
        pool_options = dict(
            user=user,
            password=password,
            dsn=dsn,
            min=2,
            max=5,
            increment=1,
            # Reap connections idle in the pool for two minutes.
            timeout=120,
            wait_timeout=5000,
            # Ping connections idle in the pool for 30 seconds before reuse.
            ping_interval=30,
            ping_timeout=5000,
            # Send Oracle Net keepalive probes every minute on supported hosts.
            expire_time=1,
            getmode=oracledb.POOL_GETMODE_TIMEDWAIT,
        )
        if wallet_dir:
            wallet_path = Path(wallet_dir).expanduser().resolve()
            if not wallet_path.is_dir():
                raise RuntimeError("Oracle wallet directory is unavailable")
            pool_options.update(
                config_dir=str(wallet_path),
                wallet_location=str(wallet_path),
                wallet_password=wallet_password or None,
            )

        _pool = oracledb.create_pool(**pool_options)
        logger.info("Oracle pool ready (idle_timeout_s=120 ping_interval_s=30 ping_timeout_ms=5000 expire_time_min=1 wait_timeout_ms=5000 call_timeout_ms=30000)")
        return _TrackedPool(_pool)


def health_check() -> bool:
    try:
        with get_pool().acquire() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1 FROM dual")
                return cursor.fetchone() == (1,)
    except Exception as exc:
        logger.warning("Oracle database health check failed (%s)", type(exc).__name__)
        return False


def close_pool() -> None:
    global _pool
    with _pool_lock:
        if _pool is not None:
            _pool.close()
            _pool = None
