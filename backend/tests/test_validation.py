"""
Unit tests for the validation rule registry and engine.
Run with: pytest -q

Every rule in REGISTRY has at least one passing and one failing case here.
The v1 tests for INVALID_ICD10 and the 5%-tolerance AMOUNT_MISMATCH were replaced:
SHA requires ICD-11 and an exact total (see CLAUDE_CODE_BRIEF.md, Phase 2).
"""

from datetime import date, timedelta

import pytest

from terminology import icd11
from validation.engine import validate
from validation.rules import REGISTRY, RULES_BY_ID, run_rule

YESTERDAY = str(date.today() - timedelta(days=1))
TWO_DAYS_AGO = str(date.today() - timedelta(days=2))
TOMORROW = str(date.today() + timedelta(days=1))


def _item(seq=1, code="SHA-12-001", price=1500, qty=1, start=YESTERDAY, end=None, **extra) -> dict:
    return {
        "sequence": seq, "service_code": code, "description": "Consultation",
        "quantity": qty, "unit_price": price, "service_start": start,
        "service_end": end if end is not None else start, **extra,
    }


def _base_claim(**overrides) -> dict:
    """A claim that passes every rule, optionally overriding specific fields."""
    claim = {
        "id": "TEST-001",
        "patient_id": "INS-TEST-001",
        "facility_code": "FAC-001",
        "facility_name": "Test Hospital",
        "visit_date": YESTERDAY,
        "diagnosis_code": "CA40.Z",
        "diagnosis_description": "Pneumonia, organism unspecified",
        "coverage_start_date": "2024-01-01",
        "coverage_end_date": "2099-01-01",
        "fund": "SHIF",
        "practitioner_id": "PUID-0000001-1",
        "practitioner_name": "Dr. Test",
        "items": [_item()],
        "claimed_amount": 1500,
    }
    claim.update(overrides)
    return claim


def check(rule_id: str, claim: dict):
    return run_rule(RULES_BY_ID[rule_id], claim)


def test_base_claim_passes_every_rule():
    failing = [r.rule_id for r in (run_rule(rule, _base_claim()) for rule in REGISTRY) if not r.passed]
    assert failing == []


def test_every_rule_has_metadata():
    for rule in REGISTRY:
        assert rule.severity in ("error", "warning")
        assert rule.version and rule.source_label and rule.fields


class TestRequiredFields:
    def test_fails_listing_each_missing_field(self):
        result = check("MISSING_FIELDS", _base_claim(patient_id="", facility_code=""))
        assert not result.passed and result.severity == "error"
        assert result.fields == ["patient_id", "facility_code"]


class TestICD11:
    @pytest.mark.parametrize("code", ["1A00", "CA40.Z", "DB10.02", "GB61.5", "5A11", "JB20.Z", "DA42.Z&XT5R", "NC72.2/XJ4NP"])
    def test_valid_codes(self, code):
        assert check("INVALID_ICD11", _base_claim(diagnosis_code=code)).passed

    @pytest.mark.parametrize("code", ["J18.9", "O80", "E11.9", "A09"])
    def test_icd10_codes_get_specific_message(self, code):
        result = check("INVALID_ICD11", _base_claim(diagnosis_code=code))
        assert not result.passed
        assert "ICD-10" in result.message and "ICD-11" in result.message

    @pytest.mark.parametrize("code", ["ZZZ999", "1I00", "CA4O", "INVALID", "CA40.Z&J18"])
    def test_invalid_codes(self, code):
        result = check("INVALID_ICD11", _base_claim(diagnosis_code=code))
        assert not result.passed and result.field == "diagnosis_code"

    def test_lookup_not_found_fails(self, monkeypatch):
        monkeypatch.setattr(icd11, "lookup", lambda code: False)
        assert not check("INVALID_ICD11", _base_claim(diagnosis_code="1A00")).passed

    def test_lookup_unavailable_falls_back_to_format(self, monkeypatch):
        monkeypatch.setattr(icd11, "lookup", lambda code: None)
        assert check("INVALID_ICD11", _base_claim(diagnosis_code="1A00")).passed


class TestVisitDate:
    def test_fails_for_future_date(self):
        result = check("VISIT_DATE", _base_claim(visit_date=TOMORROW))
        assert not result.passed and "future" in result.message.lower()

    def test_fails_for_wrong_format(self):
        assert not check("VISIT_DATE", _base_claim(visit_date="03/07/2026")).passed


class TestItemsPresent:
    def test_fails_with_no_items(self):
        assert not check("EMPTY_ITEMS", _base_claim(items=[])).passed

    def test_fails_when_item_missing_code(self):
        assert not check("EMPTY_ITEMS", _base_claim(items=[_item(code="")])).passed


class TestServiceCodeFormat:
    @pytest.mark.parametrize("code", ["SHA-12-001", "SHA-16-001", "PMF-12-001", "SHA-06-033-SI-006"])
    def test_valid(self, code):
        assert check("SHA_SERVICE_CODE_FORMAT", _base_claim(items=[_item(code=code)])).passed

    @pytest.mark.parametrize("code", ["SHA-OPD-001", "SHA-CONS-001", "12-001", "SHA-12-01"])
    def test_invalid(self, code):
        assert not check("SHA_SERVICE_CODE_FORMAT", _base_claim(items=[_item(code=code)])).passed

    def test_chapter_code_is_explained(self):
        result = check("SHA_SERVICE_CODE_FORMAT", _base_claim(items=[_item(code="SHA-12")]))
        assert "chapter" in result.message


class TestServicedPeriodPresent:
    def test_fails_without_end_date(self):
        result = check("SERVICED_PERIOD_PRESENT", _base_claim(items=[_item(end="")]))
        assert not result.passed

    def test_single_day_claim_suggests_dates(self):
        result = check("SERVICED_PERIOD_PRESENT", _base_claim(items=[_item(start="", end="")]))
        assert result.suggested_value[0]["service_start"] == YESTERDAY
        assert result.suggested_value[0]["service_end"] == YESTERDAY

    def test_multi_day_claim_has_no_suggestion(self):
        claim = _base_claim(visit_date=TWO_DAYS_AGO, discharge_date=YESTERDAY, items=[_item(start="", end="")])
        assert check("SERVICED_PERIOD_PRESENT", claim).suggested_value is None


class TestServicedPeriodInBillable:
    def test_passes_inside_multi_day_period(self):
        claim = _base_claim(visit_date=TWO_DAYS_AGO, discharge_date=YESTERDAY,
                            items=[_item(start=TWO_DAYS_AGO, end=YESTERDAY)])
        assert check("SERVICED_PERIOD_IN_BILLABLE", claim).passed

    def test_time_part_is_ignored(self):
        claim = _base_claim(items=[_item(start=f"{YESTERDAY}T08:00:00", end=f"{YESTERDAY}T23:59:00")])
        assert check("SERVICED_PERIOD_IN_BILLABLE", claim).passed

    def test_fails_outside_period(self):
        assert not check("SERVICED_PERIOD_IN_BILLABLE", _base_claim(items=[_item(start=TWO_DAYS_AGO)])).passed

    def test_fails_when_end_before_start(self):
        claim = _base_claim(visit_date=TWO_DAYS_AGO, discharge_date=YESTERDAY,
                            items=[_item(start=YESTERDAY, end=TWO_DAYS_AGO)])
        assert "ends before it starts" in check("SERVICED_PERIOD_IN_BILLABLE", claim).message


class TestItemSequence:
    def test_repeated_code_with_unique_sequences_passes(self):
        items = [_item(seq=1, code="SHA-16-001"), _item(seq=2, code="SHA-16-001")]
        assert check("ITEM_SEQUENCE_VALID", _base_claim(items=items)).passed

    @pytest.mark.parametrize("seqs", [[1, 1], [1, 3], [None, 2], [0, 1]])
    def test_invalid_sequences(self, seqs):
        items = [_item(seq=s) for s in seqs]
        result = check("ITEM_SEQUENCE_VALID", _base_claim(items=items))
        assert not result.passed
        assert [i["sequence"] for i in result.suggested_value] == [1, 2]


class TestTotalEqualsNet:
    def test_fails_on_any_difference(self):
        result = check("TOTAL_EQUALS_NET_SUM", _base_claim(claimed_amount=1500.01))
        assert not result.passed and result.suggested_value == 1500

    def test_uses_explicit_net(self):
        claim = _base_claim(items=[_item(net=1200)], claimed_amount=1200)
        assert check("TOTAL_EQUALS_NET_SUM", claim).passed

    def test_non_numeric_amount_does_not_crash(self):
        assert not check("TOTAL_EQUALS_NET_SUM", _base_claim(claimed_amount="abc")).passed


class TestPHCZeroTotal:
    def test_non_phc_claims_ignored(self):
        assert check("PHC_ZERO_TOTAL", _base_claim()).passed

    def test_phc_with_zero_total_passes(self):
        assert check("PHC_ZERO_TOTAL", _base_claim(fund="PHC", items=[_item(price=0)], claimed_amount=0)).passed

    def test_phc_with_amount_fails(self):
        assert not check("PHC_ZERO_TOTAL", _base_claim(fund="PHC")).passed


class TestPreauth:
    def test_dialysis_without_preauth_warns(self):
        result = check("PREAUTH_REQUIRED", _base_claim(items=[_item(code="SHA-16-001")]))
        assert not result.passed and result.severity == "warning"

    def test_surgery_needs_preauth(self):
        result = check("PREAUTH_REQUIRED", _base_claim(items=[_item(code="SHA-19-119")]))
        assert not result.passed and "surgical" in result.message

    def test_dialysis_with_preauth_passes(self):
        claim = _base_claim(items=[_item(code="SHA-16-001")], preauth_ref="PA-123")
        assert check("PREAUTH_REQUIRED", claim).passed


class TestTariffCeiling:
    def test_price_above_sample_tariff_warns(self):
        result = check("TARIFF_CEILING", _base_claim(items=[_item(code="SHA-16-001", price=12000)]))
        assert not result.passed and result.severity == "warning"

    def test_price_within_tariff_passes(self):
        assert check("TARIFF_CEILING", _base_claim(items=[_item(code="SHA-16-001", price=10650)])).passed

    def test_codes_without_tariff_are_skipped(self):
        assert check("TARIFF_CEILING", _base_claim(items=[_item(price=999999)])).passed

    def test_official_level_tariff_used_when_level_known(self):
        # SHA-07-005 Post-partum complications: OCL level 4 tariff 3360 (per diem).
        claim = _base_claim(facility_level="4", items=[_item(code="SHA-07-005", price=4000)])
        result = check("TARIFF_CEILING", claim)
        assert not result.passed and "OCL level 4 tariff KES 3,360" in result.message
        assert check("TARIFF_CEILING", {**claim, "facility_level": "6"}).passed  # L6 tariff 4480


class TestCoverageActive:
    def test_fails_when_coverage_expired(self):
        claim = _base_claim(coverage_end_date=TWO_DAYS_AGO)
        result = check("COVERAGE_EXPIRED", claim)
        assert not result.passed and result.severity == "error"


class TestQuantity:
    def test_zero_quantity_warns(self):
        assert not check("ITEM_QUANTITY_VALID", _base_claim(items=[_item(qty=0)])).passed


class TestAmountHigh:
    def test_standard_threshold(self):
        assert not check("AMOUNT_HIGH", _base_claim(claimed_amount=60000)).passed

    def test_maternity_icd11_chapter_has_higher_threshold(self):
        assert check("AMOUNT_HIGH", _base_claim(claimed_amount=60000, diagnosis_code="JB20.Z")).passed


class TestDepartmentRules:
    def test_maternity_needs_partograph(self):
        assert not check("MISSING_PARTOGRAPH", _base_claim(diagnosis_code="JB20.Z")).passed
        assert check("MISSING_PARTOGRAPH", _base_claim(diagnosis_code="JB20.Z", partograph_id="PG-1")).passed

    def test_renal_frequency(self):
        assert not check("IMPLAUSIBLE_FREQUENCY", _base_claim(department="renal", sessions_this_week=5)).passed
        assert check("IMPLAUSIBLE_FREQUENCY", _base_claim(department="renal", sessions_this_week=3)).passed

    def test_surgical_postop_notes(self):
        claim = _base_claim(department="surgical", overnight_stay=True)
        assert not check("MISSING_POSTOP_NOTES", claim).passed
        assert check("MISSING_POSTOP_NOTES", {**claim, "postop_notes_attached": "DS-1"}).passed


class TestFhirBundleRule:
    def test_missing_practitioner_fails_with_fields(self):
        result = check("FHIR_BUNDLE_VALID", _base_claim(practitioner_id=""))
        assert not result.passed and "practitioner_id" in result.fields

    def test_total_mismatch_is_not_double_counted(self):
        # TOTAL_EQUALS_NET_SUM reports this; the bundle rule skips it.
        assert check("FHIR_BUNDLE_VALID", _base_claim(claimed_amount=1)).passed


class TestFixMetadata:
    def test_single_field_rules_default_fields(self):
        assert check("INVALID_ICD11", _base_claim(diagnosis_code="ZZZ999")).to_dict()["fields"] == ["diagnosis_code"]

    def test_advice_text_is_never_a_suggested_value(self):
        assert "suggested_value" not in check("INVALID_ICD11", _base_claim(diagnosis_code="ZZZ999")).to_dict()

    def test_results_carry_source(self):
        result = check("INVALID_ICD11", _base_claim(diagnosis_code="J18.9")).to_dict()
        assert result["source_url"].startswith("https://afyalink.dha.go.ke")
        assert result["rule_version"]


class TestEngine:
    def test_perfect_claim_scores_100(self):
        result = validate(_base_claim())
        assert result["score"] == 100 and result["passed"] is True and result["ruleset_version"]

    def test_broken_claim_scores_low(self):
        result = validate(_base_claim(patient_id="", diagnosis_code="INVALID", items=[]))
        assert result["score"] < 60 and result["error_count"] >= 2

    def test_score_never_goes_below_zero(self):
        broken = _base_claim(patient_id="", facility_code="", diagnosis_code="BAD", visit_date=TOMORROW,
                             coverage_end_date=TWO_DAYS_AGO, fund="PHC",
                             items=[_item(seq=None, code="BAD", qty=0, start="")], claimed_amount=60000)
        assert validate(broken)["score"] == 0

    def test_status_thresholds(self):
        assert validate(_base_claim())["color"] == "green"
        assert validate(_base_claim(claimed_amount=1000))["color"] == "amber"  # one error: 80
