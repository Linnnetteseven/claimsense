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


class FakeLookups:
    def __init__(self, patients=(), roster=()):
        self._patients, self._roster = list(patients), list(roster)

    def patient_ids(self, claim):
        return self._patients

    def practitioners(self, claim):
        return self._roster


ROSTER = [
    {"practitioner_id": "PUID-1", "practitioner_name": "Dr. Kamau"},
    {"practitioner_id": "PUID-2", "practitioner_name": "Dr. Mwangi"},
]


class TestIdentity:
    def _run(self, claim, lookups):
        result = validate(claim)
        enrich.apply(result, claim, enrich.plan(result, claim, lookups), {})
        return result

    def test_patient_id_from_single_earlier_claim(self):
        claim = _demo("SHA-CLM-2026-005")
        lookups = FakeLookups(patients=[{"patient_id": "SHA-PAT-7", "claim_number": "C-7", "facility_name": "Githurai"}])
        r = _result(self._run(claim, lookups), "MISSING_FIELDS")
        assert r["suggested_changes"] == {"patient_id": "SHA-PAT-7"}
        assert "same name and date of birth" in r["suggestion_source"]

    def test_several_patient_ids_become_a_pick_list(self):
        found = [{"patient_id": p, "claim_number": "C", "facility_name": "F"} for p in ("A-1", "B-2")]
        r = _result(self._run(_demo("SHA-CLM-2026-005"), FakeLookups(patients=found)), "MISSING_FIELDS")
        assert "suggested_changes" not in r and [c["changes"]["patient_id"] for c in r["suggested_choices"]] == ["A-1", "B-2"]

    def test_unknown_patient_gets_guidance_not_an_id(self):
        claim = {**_demo("SHA-CLM-2026-005"), "patient_name": "Unknown Patient"}
        r = _result(self._run(claim, FakeLookups(patients=[{"patient_id": "X", "claim_number": "C", "facility_name": "F"}])), "MISSING_FIELDS")
        assert "suggested_changes" not in r and "SHA card" in r["suggestion_note"]

    def test_typed_practitioner_name_matches_roster(self):
        r = _result(self._run(_demo("SHA-CLM-2026-005"), FakeLookups(roster=ROSTER)), "FHIR_BUNDLE_VALID")
        assert r["suggested_changes"] == {"practitioner_id": "PUID-1", "practitioner_name": "Dr. Kamau"}

    def test_no_name_shows_roster_to_choose_from(self):
        claim = {**_demo("SHA-CLM-2026-005"), "practitioner_name": ""}
        r = _result(self._run(claim, FakeLookups(roster=ROSTER)), "FHIR_BUNDLE_VALID")
        assert "suggested_changes" not in r and len(r["suggested_choices"]) == 2

    def test_empty_roster_gives_guidance(self):
        r = _result(self._run(_demo("SHA-CLM-2026-005"), FakeLookups()), "FHIR_BUNDLE_VALID")
        assert "PUID" in r["suggestion_note"]

    def test_identifiers_never_reach_the_prompt(self):
        from llm.explainer import build_prompt
        claim = _demo("SHA-CLM-2026-005")
        lookups = FakeLookups(patients=[{"patient_id": "SHA-PAT-7", "claim_number": "C-7", "facility_name": "G"}], roster=ROSTER)
        result = validate(claim)
        targets = enrich.plan(result, claim, lookups)
        prompt = build_prompt(result["errors"], claim, targets)
        assert "SHA-PAT-7" not in prompt and "PUID-1" not in prompt and "Wambui" not in prompt
        assert "Apply fix" in prompt

    def test_applying_both_fixes_clears_the_rules(self):
        claim = _demo("SHA-CLM-2026-005")
        lookups = FakeLookups(patients=[{"patient_id": "SHA-PAT-7", "claim_number": "C-7", "facility_name": "G"}], roster=ROSTER)
        result = self._run(claim, lookups)
        for rule_id in ("MISSING_FIELDS", "FHIR_BUNDLE_VALID", "EMPTY_ITEMS"):
            claim = {**claim, **_result(result, rule_id)["suggested_changes"]}
        after = validate(claim)
        assert after["error_count"] == 0, [r["rule_id"] for r in after["errors"]]


class TestMoreFixes:
    def test_phc_total_offers_both_ways_out(self):
        claim = _demo("SHA-CLM-2026-008")
        result = validate(claim)
        enrich.apply(result, claim, enrich.plan(result, claim), {})
        choices = _result(result, "PHC_ZERO_TOTAL")["suggested_choices"]
        zeroed = {**claim, **choices[0]["changes"]}
        assert validate(zeroed)["error_count"] == 0
        assert choices[1]["changes"] == {"fund": "SHIF"}

    def test_wrong_level_code_gets_a_replacement(self):
        # Consultation SHA-12-001 is levels 2-4; at a level 6 inpatient stay a per diem fits.
        claim = {**_demo("SHA-CLM-2026-001")}
        claim["items"] = [{**claim["items"][0], "service_code": "SHA-12-001"}]
        result = validate(claim)
        targets = enrich.plan(result, claim)
        assert targets["INTERVENTION_FACILITY_LEVEL"].candidates[0][0] == "SHA-07-001"
        # Weak wording match, so no automatic pick: Gemini chooses from the shortlist.
        enrich.apply(result, claim, targets, {"INTERVENTION_FACILITY_LEVEL": {"code": "SHA-07-001", "reason": "stay"}})
        fix = _result(result, "INTERVENTION_FACILITY_LEVEL")["suggested_changes"]["items"][0]
        assert fix["service_code"] == "SHA-07-001"
        assert run_rule(RULES_BY_ID["INTERVENTION_FACILITY_LEVEL"], {**claim, "items": [fix]}).passed
