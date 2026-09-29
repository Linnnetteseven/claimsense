#!/usr/bin/env bash
# Run the HL7 FHIR validator against the SHA bundle generated for one demo claim.
#
#   scripts/validate_bundle.sh [CLAIM_ID]      (default SHA-CLM-2026-001)
#
# Needs Java 11+ and validator_cli.jar (https://github.com/hapifhir/org.hl7.fhir.core/releases);
# set FHIR_VALIDATOR_JAR to its path. The eClaims IG package id is ke.fhir.eclaims#0.1.0
# (the brief's fhir.kenyaClaimsIG#0.1.0 is not the published id).
set -euo pipefail
cd "$(dirname "$0")/.."
CLAIM_ID="${1:-SHA-CLM-2026-001}"
JAR="${FHIR_VALIDATOR_JAR:-validator_cli.jar}"
OUT="$(mktemp -d)/bundle-${CLAIM_ID}.json"

python - "$CLAIM_ID" "$OUT" <<'PY'
import json, sys
from data.mock_claims import load_demo_claims
from fhir.kenya_bundle_builder import build_kenya_eclaims_bundle
claim = next(c for c in load_demo_claims() if c["id"] == sys.argv[1])
json.dump(build_kenya_eclaims_bundle(claim), open(sys.argv[2], "w"), indent=2)
PY

echo "Validating $OUT"
java -jar "$JAR" "$OUT" -version 4.0.1 -ig ke.fhir.eclaims#0.1.0
