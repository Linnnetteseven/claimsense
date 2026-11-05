"""Small process-local TTL cache for Oracle-backed queue and analytics reads."""
from __future__ import annotations

from threading import RLock
from time import monotonic

_TTL_SECONDS = 45
_MAX_ENTRIES = 64
_lock = RLock()
_entries: dict[tuple, tuple[float, object]] = {}


def get(key: tuple):
    with _lock:
        entry = _entries.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if expires_at <= monotonic():
            _entries.pop(key, None)
            return None
        return value


def put(key: tuple, value):
    with _lock:
        if len(_entries) >= _MAX_ENTRIES:
            oldest = min(_entries, key=lambda item: _entries[item][0])
            _entries.pop(oldest, None)
        _entries[key] = (monotonic() + _TTL_SECONDS, value)
    return value


def clear() -> None:
    with _lock:
        _entries.clear()


def clear_prefix(prefix: str) -> None:
    with _lock:
        for key in list(_entries):
            if key and key[0] == prefix:
                _entries.pop(key, None)
