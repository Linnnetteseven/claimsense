"""Fix suggestions: WHO ICD-10->11 map, SHA intervention shortlists, Gemini picks within them."""

from data.mock_claims import load_demo_claims
from suggest import enrich
from suggest.interventions import shortlist
from terminology import icd11
from validation.engine import validate
from validation.rules import RULES_BY_ID, run_rule
from tests.test_validation import _base_claim, _item


def _demo(claim_id):
    return next(c for c in load_demo_claims() if c["id"] == claim_id)


def _result(result, rule_id):
    return next(r for r in result["results"] if r["rule_id"] == rule_id)


class TestIcd:
    def test_icd10_gets_who_mapped_suggestion(self):
        result = run_rule(RULES_BY_ID["INVALID_ICD11"], _base_claim(diagnosis_code="J18.9")).to_dict()
        assert result["suggested_changes"] == {
            "diagnosis_code": "CA40.Z", "diagnosis_description": "Pneumonia, organism unspecified",
        }
        assert result["suggestion_source"] == "WHO ICD-10 to ICD-11 map"

    def test_icd10_parent_fallback(self):
        assert icd11.from_icd10("N18.6") == ("GB61.Z", "Chronic kidney disease, stage unspecified")

    def test_well_formed_but_unknown_code_fails(self):
        result = run_rule(RULES_BY_ID["INVALID_ICD11"], _base_claim(diagnosis_code="CA4Z.9"))
        assert not result.passed and "not in the WHO ICD-11 release" in result.message

    def test_applying_the_suggestion_passes(self):
        claim = _base_claim(diagnosis_code="J18.9")
        changes = run_rule(RULES_BY_ID["INVALID_ICD11"], claim).to_dict()["suggested_changes"]
        assert run_rule(RULES_BY_ID["INVALID_ICD11"], {**claim, **changes}).passed


class TestShortlist:
    def test_uncoded_consultation_at_health_centre(self):
        claim = _demo("SHA-CLM-2026-005")
        assert shortlist(claim, claim["items"][0])[0].info.code == "SHA-12-001"

    def test_inpatient_stay_gets_per_diem_with_tariff(self):
        claim = {**_demo("SHA-CLM-2026-001"), "items": []}
        top = shortlist(claim)[0]
        assert top.info.code == "SHA-07-001" and top.unit_price == 4480 and top.quantity == 2

    def test_every_candidate_passes_catalogue_rules(self):
        for claim_id in ("SHA-CLM-2026-001", "SHA-CLM-2026-003", "SHA-CLM-2026-005", "SHA-CLM-2026-007"):
            claim = _demo(claim_id)
            for cand in shortlist(claim, claim["items"][0] if claim["items"] else None):
                trial = {**claim, "items": [{**_item(code=cand.info.code), "service_start": claim["visit_date"],
                                            "service_end": claim.get("discharge_date") or claim["visit_date"]}]}
                for rule_id in ("INTERVENTION_ELIGIBILITY", "INTERVENTION_FACILITY_LEVEL", "INTERVENTION_ACCESS_POINT"):
                    assert run_rule(RULES_BY_ID[rule_id], trial).passed, (claim_id, cand.info.code, rule_id)

    def test_female_only_codes_not_offered_to_men(self):
        claim = {**_demo("SHA-CLM-2026-003"), "gender": "M", "items": []}
        assert "SHA-08-005" not in [c.info.code for c in shortlist(claim)]


class TestEnrich:
    def test_deterministic_pick_without_ai(self):
        claim = _demo("SHA-CLM-2026-005")
        result = validate(claim)
        targets = enrich.plan(result, claim)
        enrich.apply(result, claim, targets, {})
        r = _result(result, "EMPTY_ITEMS")
        assert r["suggested_changes"]["items"][0]["service_code"] == "SHA-12-001"
        assert r["suggestion_source"] == "SHA catalogue best match"

    def test_ai_pick_outside_shortlist_is_ignored(self):
        claim = {**_demo("SHA-CLM-2026-001"), "items": []}
        result = validate(claim)
        targets = enrich.plan(result, claim)
        enrich.apply(result, claim, targets, {"EMPTY_ITEMS": {"code": "SHA-99-999", "reason": "made up"}})
        r = _result(result, "EMPTY_ITEMS")
        assert r.get("suggestion_source") != "Gemini, from a validated shortlist"
        assert "SHA-99-999" not in str(r.get("suggested_changes"))

    def test_ai_pick_inside_shortlist_is_used(self):
        claim = _demo("SHA-CLM-2026-005")
        result = validate(claim)
        targets = enrich.plan(result, claim)
        enrich.apply(result, claim, targets, {"EMPTY_ITEMS": {"code": "SHA-12-002", "reason": "Lab visit"}})
        r = _result(result, "EMPTY_ITEMS")
        assert r["suggested_changes"]["items"][0]["service_code"] == "SHA-12-002"
        assert r["suggestion_reason"] == "Lab visit" and r["suggestion_source"].startswith("Gemini")

    def test_no_fitting_code_gives_guidance(self):
        claim = {**_demo("SHA-CLM-2026-002"), "visit_date": "2026-01-01"}
        result = validate(claim)
        targets = enrich.plan(result, claim)
        enrich.apply(result, claim, targets, {})
        r = _result(result, "EMPTY_ITEMS")
        assert "suggested_changes" not in r and "PHC" in r["suggestion_note"]

    def test_applied_item_clears_the_rule(self):
        claim = _demo("SHA-CLM-2026-005")
        result = validate(claim)
        targets = enrich.plan(result, claim)
        enrich.apply(result, claim, targets, {})
        fixed = {**claim, **_result(result, "EMPTY_ITEMS")["suggested_changes"]}
        assert run_rule(RULES_BY_ID["EMPTY_ITEMS"], fixed).passed
