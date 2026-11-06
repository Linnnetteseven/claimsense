"""Select the repository from DB_BACKEND; Redis remains the default."""
from __future__ import annotations

import logging
import os
from threading import Lock

logger = logging.getLogger(__name__)
_repository = None
_lock = Lock()


class FallbackRepository:
    backend_name = "oracle_with_fallback"

    def __init__(self, primary, fallback):
        self.primary = primary
        self.fallback = fallback
        self.active_backend = "oracle"

    def health(self):
        if self.active_backend == "oracle" and self.primary.health():
            return True
        self.active_backend = "redis"
        return self.fallback.health()

    def __getattr__(self, name):
        primary_method = getattr(self.primary, name)
        fallback_method = getattr(self.fallback, name)

        def call(*args, **kwargs):
            if self.active_backend == "redis":
                return fallback_method(*args, **kwargs)
            try:
                return primary_method(*args, **kwargs)
            except Exception as exc:
                logger.warning("Oracle operation unavailable; using Redis fallback (%s)", type(exc).__name__)
                self.active_backend = "redis"
                return fallback_method(*args, **kwargs)
        return call


def configured_backend() -> str:
    return os.getenv("DB_BACKEND", "redis").strip().lower() or "redis"


def get_repository():
    global _repository
    if _repository is not None:
        return _repository
    with _lock:
        if _repository is not None:
            return _repository
        mode = configured_backend()
        from .redis_impl import RedisRepository
        redis_repository = RedisRepository()
        if mode == "redis":
            _repository = redis_repository
        elif mode in {"oracle", "oracle_with_fallback"}:
            from .oracle_impl import OracleRepository
            oracle_repository = OracleRepository()
            _repository = (
                FallbackRepository(oracle_repository, redis_repository)
                if mode == "oracle_with_fallback"
                else oracle_repository
            )
        else:
            raise ValueError("DB_BACKEND must be redis, oracle, or oracle_with_fallback")
        return _repository


def is_oracle_active(repository=None) -> bool:
    repository = repository or get_repository()
    return repository.backend_name == "oracle" or (
        repository.backend_name == "oracle_with_fallback"
        and repository.active_backend == "oracle"
    )


def reset_repository_for_tests() -> None:
    global _repository
    with _lock:
        _repository = None
