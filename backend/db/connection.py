"""Lazy python-oracledb thin-mode connection pool for Autonomous Database."""
from __future__ import annotations

import os
import logging
from pathlib import Path
from threading import Lock
from typing import Any

_pool: Any | None = None
_pool_lock = Lock()
logger = logging.getLogger(__name__)


def connection_mode() -> str:
    """Return the configured Oracle transport without exposing connection details."""
    return "wallet_mtls" if os.getenv("ORACLE_WALLET_DIR", "").strip() else "walletless_tls"


def get_pool():
    """Create the pool once per process. python-oracledb defaults to Thin mode."""
    global _pool
    if _pool is not None:
        return _pool
    with _pool_lock:
        if _pool is not None:
            return _pool
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
            min=1,
            max=5,
            increment=1,
            timeout=30,
            wait_timeout=5000,
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
        return _pool


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
