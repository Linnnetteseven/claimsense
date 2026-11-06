"""Separate view-only Oracle pool for the experimental Select AI endpoint."""
from __future__ import annotations

import os
from pathlib import Path
from threading import Lock

_pool = None
_lock = Lock()


def get_select_ai_pool():
    global _pool
    if _pool is not None:
        return _pool
    with _lock:
        if _pool is not None:
            return _pool
        import oracledb

        user = os.getenv("ORACLE_SELECT_AI_USER", "").strip()
        password = os.getenv("ORACLE_SELECT_AI_PASSWORD", "")
        dsn = os.getenv("ORACLE_DSN", "").strip()
        if not all((user, password, dsn)):
            raise RuntimeError("Select AI read-only database credentials are incomplete")
        options = {"user": user, "password": password, "dsn": dsn,
                   "min": 1, "max": 2, "increment": 1, "timeout": 30}
        wallet_dir = os.getenv("ORACLE_WALLET_DIR", "").strip()
        if wallet_dir:
            wallet_path = Path(wallet_dir).expanduser().resolve()
            if not wallet_path.is_dir():
                raise RuntimeError("Oracle wallet directory is unavailable")
            options.update({"config_dir": str(wallet_path), "wallet_location": str(wallet_path),
                            "wallet_password": os.getenv("ORACLE_WALLET_PASSWORD") or None})
        _pool = oracledb.create_pool(**options)
        return _pool


def close_select_ai_pool():
    global _pool
    with _lock:
        if _pool is not None:
            _pool.close()
            _pool = None
