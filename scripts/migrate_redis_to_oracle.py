"""One-off verified migration of the existing Upstash ledger into Oracle.

Run with DB_BACKEND=oracle and Redis/Oracle variables set. The source Redis
ledger is read-only; its contents are never deleted or modified.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND = Path(__file__).resolve().parents[1] / "backend"
load_dotenv(REPO_ROOT / ".env")
sys.path.insert(0, str(BACKEND))

from audit import chain  # noqa: E402
from db.oracle_impl import OracleRepository  # noqa: E402


def main() -> int:
    if os.getenv("DB_BACKEND", "redis").strip().lower() != "oracle":
        print("Set DB_BACKEND=oracle for this one-off migration.")
        return 2
    if not os.getenv("UPSTASH_REDIS_REST_URL") or not os.getenv("UPSTASH_REDIS_REST_TOKEN"):
        print("Redis source credentials are missing; no source ledger was changed.")
        return 2
    try:
        source_records = chain._redis_all_records()
        if not source_records:
            print("The Redis ledger is empty; nothing to migrate.")
            return 0
        source_integrity = chain.verify_records(source_records)
        if not source_integrity.get("verified"):
            print("Redis ledger verification failed; migration stopped before Oracle writes.")
            return 1
        result = OracleRepository().import_legacy_records(source_records, chain.verify_records)
        print(
            "Migration complete: "
            f"{result['copied_count']} entries copied; source and Oracle chains verified; "
            f"{result['legacy_anchors_archived']} old anchors archived as legacy references."
        )
        print("The Redis source remains unchanged. Oracle hashes use the privacy-safe v3 ledger format.")
        return 0
    except Exception as exc:
        logging.getLogger(__name__).error("Migration stopped (%s); no secrets or record payloads printed.", type(exc).__name__)
        print("Migration failed. Check Oracle schema, wallet and connectivity; Redis remains unchanged.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
