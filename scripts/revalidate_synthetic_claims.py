"""Revalidate synthetic claims under the current Hakiki rule set.

Run from the repository root with DB_BACKEND=oracle and the normal Oracle
environment configured. The command is read-only unless --apply is supplied.
It refuses to write unless the existing full ledger verifies and only selects
claims carrying both the is_synthetic flag and a strict SYN identifier.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from audit.chain import verify_records  # noqa: E402
from db.factory import configured_backend, get_repository  # noqa: E402
from validation.engine import validate  # noqa: E402
from validation.rules import RULES_DATE, RULES_VERSION  # noqa: E402

_SYNTHETIC_CLAIM_ID = re.compile(r"SYN-CLM-[0-9]{6}\Z")
_SYNTHETIC_PATIENT_ID = re.compile(r"SYN-[0-9]{6}\Z")


def _is_synthetic(claim: dict) -> bool:
    """Require independent synthetic flag and reference checks before writes."""
    return (
        claim.get("is_synthetic") is True
        and bool(_SYNTHETIC_CLAIM_ID.fullmatch(str(claim.get("id") or "")))
        and bool(_SYNTHETIC_PATIENT_ID.fullmatch(str(claim.get("patient_id") or "")))
    )


def _already_current(latest: dict | None, lifecycle: dict) -> bool:
    return bool(
        latest
        and latest.get("rules_version") == RULES_VERSION
        and latest.get("rules_date") == RULES_DATE
        and int(latest.get("version") or 0) == int(lifecycle.get("version") or 0)
        and str(lifecycle.get("status") or "").lower() != "needs_revalidation"
    )


def _category(status: str | None) -> str:
    if status == "Ready for Submission":
        return "ready"
    if status == "Needs Review":
        return "review"
    return "blocked"


def revalidate_synthetic_claims(repository, *, apply: bool) -> dict:
    """Preflight, write fresh versions through record_validation, and verify."""
    before = verify_records(repository.all_ledger_records())
    if not before.get("verified"):
        raise RuntimeError(
            f"Ledger preflight failed at record {before.get('broken_at')}; no claims were changed"
        )

    synthetic = [claim for claim in repository.list_claims() if _is_synthetic(claim)]
    candidates: list[tuple[str, dict, dict]] = []
    skipped_submitted = 0
    already_current = 0
    for claim in synthetic:
        claim_id = str(claim["id"])
        saved = repository.get_claim(claim_id)
        lifecycle = (saved or {}).get("_lifecycle") or {}
        if str(lifecycle.get("status") or "").lower() == "submitted":
            # The ordinary validation route locks submitted claims. Preserve that rule.
            skipped_submitted += 1
            continue
        latest = repository.get_latest_validation(claim_id)
        if _already_current(latest, lifecycle):
            already_current += 1
            continue
        candidates.append((claim_id, saved or claim, lifecycle))

    for claim_id, claim, _lifecycle in candidates:
        if not apply:
            continue
        result = validate(claim)
        result.update({"rules_version": RULES_VERSION, "rules_date": RULES_DATE})
        # This is the same repository write used by POST /claims/{id}/validate
        # via audit.chain.record_validation: one immutable version, ledger event,
        # and validation_runs row in the repository's normal transaction.
        repository.record_validation(claim_id, claim, result)

    if apply:
        categories = {"ready": 0, "review": 0, "blocked": 0}
        submitted = 0
        for claim in synthetic:
            claim_id = str(claim["id"])
            lifecycle = repository.get_claim_lifecycle(claim_id) or {}
            latest = repository.get_latest_validation(claim_id)
            if str(lifecycle.get("status") or "").lower() == "submitted":
                continue
            if latest:
                categories[_category(latest.get("status"))] += 1

        after = verify_records(repository.all_ledger_records())
        if not after.get("verified"):
            raise RuntimeError(
                f"Ledger verification failed after writes at record {after.get('broken_at')}"
            )
    else:
        categories = {"ready": 0, "review": 0, "blocked": 0}
        submitted = skipped_submitted
        after = None

    return {
        "synthetic_claims": len(synthetic),
        "to_revalidate": len(candidates),
        "already_current": already_current,
        "submitted_locked": skipped_submitted,
        "applied": bool(apply),
        "rules_version": RULES_VERSION,
        "rules_date": RULES_DATE,
        "ready": categories["ready"],
        "review": categories["review"],
        "blocked": categories["blocked"],
        "submitted": submitted if apply else skipped_submitted,
        "ledger_before": before,
        "ledger_after": after,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true",
        help="write new validation versions (without this flag the command only previews)",
    )
    args = parser.parse_args()
    if configured_backend() != "oracle":
        parser.error("Set DB_BACKEND=oracle; this command must not write to Redis or mock mode")
    summary = revalidate_synthetic_claims(get_repository(), apply=args.apply)
    print(summary)
    if not args.apply:
        print("Preview only. Re-run with --apply to append versions and validation events.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
