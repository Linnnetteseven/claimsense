"""
Validate the SHA bundle for demo claims against the SHA UAT FHIR server ($validate).

    python scripts/uat_validate.py [CLAIM_ID ...]

$validate checks and stores nothing. The eClaims profiles are not loaded on UAT,
so this checks base FHIR plus the code systems UAT hosts; profile validation
needs scripts/validate_bundle.sh (HL7 validator + IG package).
"""

import collections
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import config  # noqa: E402
from data.mock_claims import load_demo_claims  # noqa: E402
from fhir.kenya_bundle_builder import build_kenya_eclaims_bundle  # noqa: E402

# Issues that are expected until SHA publishes profiles on UAT, or are FHIR best practice only.
KNOWN = ("has not been checked because it could not be found", "Failed to retrieve profile", "dom-6")


def main(claim_ids: list[str]) -> int:
    claims = [c for c in load_demo_claims() if not claim_ids or c["id"] in claim_ids]
    failed = 0
    for claim in claims:
        resp = httpx.post(
            f"{config.SHA_FHIR_URL}/Bundle/$validate",
            json=build_kenya_eclaims_bundle(claim),
            headers={"Accept": "application/fhir+json", "Content-Type": "application/fhir+json"},
            verify=config.SHA_FHIR_VERIFY_SSL,
            timeout=90,
        )
        issues = [
            i for i in resp.json().get("issue", [])
            if i.get("severity") in ("error", "fatal", "warning")
            and not any(k in i.get("diagnostics", "") for k in KNOWN)
        ]
        counts = collections.Counter(i["severity"] for i in issues)
        print(f"{claim['id']}: HTTP {resp.status_code} {dict(counts) or 'no issues'}")
        for i in issues:
            print(f"  [{i['severity']}] {(i.get('expression') or [''])[0]}: {i.get('diagnostics', '')[:200]}")
        failed += counts["error"] + counts["fatal"] > 0
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
