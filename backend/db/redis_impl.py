"""Adapter that preserves Hakiki's current Upstash/in-process ledger behavior."""
from __future__ import annotations

from .repository import RepositoryUnavailable


class RedisRepository:
    backend_name = "redis"

    def __init__(self):
        pass

    @staticmethod
    def _chain():
        # Lazy import avoids a cycle: audit.chain is the public façade.
        from audit import chain
        return chain

    def health(self) -> bool:
        from audit.chain import _audit_enabled, _redis
        if not _audit_enabled():
            return True  # Process-local compatibility mode is intentionally available.
        try:
            _redis("PING")
            return True
        except Exception:
            return False

    def all_ledger_records(self):
        return self._chain()._redis_all_records()

    def append_ledger_event(self, payload):
        return self._chain()._redis_append(payload)

    def append_ledger_events(self, payloads, existing=None):
        return self._chain()._redis_append_many(payloads, existing)

    def record_claim_received(self, claim):
        return self._chain()._record_claim_received_legacy(claim)

    def record_claims_received(self, claims):
        return self._chain()._record_claims_received_legacy(claims)

    def record_claim_correction(self, claim_id, previous, updated):
        return self._chain()._record_claim_correction_legacy(claim_id, previous, updated)

    def record_validation(self, claim_id, claim, result):
        return self._chain()._record_validation_legacy(claim_id, result, claim)

    def record_event(self, payload):
        return self.append_ledger_event(payload)

    def _redis(self, *command):
        from audit.chain import _redis, _audit_enabled
        if _audit_enabled():
            return _redis(*command)
        return None

    def get_department_review(self, claim_id, department):
        raise RepositoryUnavailable("Server-side department state is enabled only with DB_BACKEND=oracle")

    def save_department_review(self, claim_id, department, review):
        raise RepositoryUnavailable("Server-side department state is enabled only with DB_BACKEND=oracle")

    def list_outcomes(self, claim_id=None):
        raise RepositoryUnavailable("Server-side outcomes are enabled only with DB_BACKEND=oracle")

    def save_outcome(self, outcome):
        raise RepositoryUnavailable("Server-side outcomes are enabled only with DB_BACKEND=oracle")

    def _redis_available(self):
        from audit.chain import _audit_enabled
        return _audit_enabled()

    # Claim storage remains the same volatile session store in Redis mode.
    def get_claim(self, _claim_id):
        return None

    def list_claims(self):
        return []

    def sync_claims(self, claims):
        return claims

    def create_claim(self, claim):
        return claim
