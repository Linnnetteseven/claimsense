"""
Validation pipeline shared by the routers.

validate (deterministic rules) -> suggestions -> Gemini explanations -> FHIR
ClaimResponse -> audit chain. The score only ever comes from the rules.
"""

import logging

from audit import chain
from fhir.builder import build_claim_response
from fhir.bundle_checks import check_bundle
from fhir.kenya_bundle_builder import build_kenya_eclaims_bundle
from llm.explainer import explain_errors
from suggest.enrich import apply as suggest_apply, plan as suggest_plan
from validation.engine import validate

logger = logging.getLogger("hakiki.pipeline")


def preview(result: dict) -> dict:
    """The score summary shown in the claims queue."""
    return {key: result[key] for key in ("score", "status", "color", "error_count", "warning_count")}


def record_run(repository, claim_id: str, result: dict) -> None:
    """Keep the validation history; never fail a request over it."""
    try:
        repository.record_validation_run(claim_id, result)
    except Exception:
        logger.exception("Unable to record validation run for %s", claim_id)


def full_pipeline(claim: dict, lookups=None) -> dict:
    result = validate(claim)
    # Suggestions: a validated shortlist per rule; Gemini may pick, the rules re-check.
    targets = suggest_plan(result, claim, lookups)
    explained, ai_used = explain_errors(result["errors"] + result["warnings"], claim, targets)
    suggest_apply(result, claim, targets, {r: e["pick"] for r, e in explained.items() if e.get("pick")})
    result["explanations"] = {rule_id: e["text"] for rule_id, e in explained.items()}
    result["fix_steps"] = {rule_id: e["fix_steps"] for rule_id, e in explained.items() if e["fix_steps"]}
    result["ai_explanations_used"] = ai_used
    result["fhir_claim_response"] = build_claim_response(claim, result)
    try:
        chain.record_validation(claim.get("id"), result)
    except Exception:
        # The audit trail is optional; never fail validation over it.
        logger.exception("Audit chain write failed for %s", claim.get("id"))
    return result


def bundle_with_checks(claim: dict) -> dict:
    bundle = build_kenya_eclaims_bundle(claim)
    issues = check_bundle(bundle)
    return {
        "bundle": bundle,
        "checks_passed": not issues,
        "issues": [{"check_id": i.check_id, "message": i.message, "fields": i.fields} for i in issues],
    }
