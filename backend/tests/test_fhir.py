"""Kenya eClaims bundle builder, bundle checks, claim-state parsing and the SHA status stub."""

import copy

import httpx
import pytest

from config import config
from data.mock_claims import load_demo_claims
from fhir import sha_client as sha_client_module
from fhir.bundle_checks import check_bundle
from fhir.claim_state import parse_claim_state
from fhir.kenya_bundle_builder import build_kenya_eclaims_bundle
from tests.test_validation import _base_claim


def _demo(claim_id="SHA-CLM-2026-001"):
    return next(c for c in load_demo_claims() if c["id"] == claim_id)


def _resource(bundle, rtype):
    return next(e["resource"] for e in bundle["entry"] if e["resource"]["resourceType"] == rtype)


def test_demo_claim_bundle_passes_checks():
    assert check_bundle(build_kenya_eclaims_bundle(_demo())) == []


def test_every_demo_claim_with_practitioner_passes_structure_checks():
    for claim in load_demo_claims():
        if claim.get("practitioner_id") and claim.get("items"):
            ids = {i.check_id for i in check_bundle(build_kenya_eclaims_bundle(claim))}
            assert not ids - {"TOTAL_MATCHES_NET"}, (claim["id"], ids)


def test_bundle_shape():
    bundle = build_kenya_eclaims_bundle(_demo())
    types = [e["resource"]["resourceType"] for e in bundle["entry"]]
    assert bundle["type"] == "message" and types[0] == "MessageHeader"
    assert {"Claim", "Patient", "Coverage", "Organization", "Practitioner"} <= set(types)
    assert len({e["fullUrl"] for e in bundle["entry"]}) == len(bundle["entry"])


def test_message_header_can_be_switched_off(monkeypatch):
    monkeypatch.setattr(config, "SHA_BUNDLE_MESSAGE_HEADER", False)
    bundle = build_kenya_eclaims_bundle(_demo())
    assert "MessageHeader" not in [e["resource"]["resourceType"] for e in bundle["entry"]]
    assert check_bundle(bundle) == []


def test_missing_values_are_omitted_not_empty():
    claim = _resource(build_kenya_eclaims_bundle(_base_claim(items=[{"sequence": 1, "description": "x"}])), "Claim")
    assert claim["item"][0]["productOrService"] == {"text": "x"}
    patient = _resource(build_kenya_eclaims_bundle(_base_claim(patient_id="")), "Patient")
    assert "identifier" not in patient


def test_bundle_is_deterministic_per_claim():
    a, b = build_kenya_eclaims_bundle(_demo()), build_kenya_eclaims_bundle(_demo())
    assert [e["fullUrl"] for e in a["entry"]] == [e["fullUrl"] for e in b["entry"]]


def test_codings_use_terminology_base(monkeypatch):
    monkeypatch.setattr(config, "SHA_TERMINOLOGY_BASE", "https://example.test/fhir")
    claim = _resource(build_kenya_eclaims_bundle(_demo()), "Claim")
    assert claim["diagnosis"][0]["diagnosisCodeableConcept"]["coding"][0] == {
        "system": "https://example.test/fhir/CodeSystem/icd11-codes-cs",
        "code": "CA40.Z",
        "display": "Pneumonia, organism unspecified",
    }
    item = claim["item"][0]
    assert item["productOrService"]["coding"][0]["system"].endswith("/CodeSystem/KenyaSocialHealthAuthorityInterventionCS")
    assert item["category"]["coding"][0]["code"] == "1"
    assert item["servicedPeriod"]["start"] and item["net"]["value"] == 1500
    assert claim["meta"]["profile"][0] == "https://example.test/fhir/StructureDefinition/ke-eclaims-claimsubmission"


def test_inpatient_subtype_for_multi_day_stay():
    claim = _resource(build_kenya_eclaims_bundle(_demo("SHA-CLM-2026-003")), "Claim")
    assert claim["subType"]["coding"][0]["code"] == "inpatient"
    assert claim["billablePeriod"]["start"] < claim["billablePeriod"]["end"]


def test_preauth_ref_on_insurance():
    claim = _resource(build_kenya_eclaims_bundle(_base_claim(preauth_ref="PA-1")), "Claim")
    assert claim["insurance"][0]["preAuthRef"] == ["PA-1"]


class TestChecks:
    def _bundle(self):
        return build_kenya_eclaims_bundle(_base_claim())

    def test_missing_practitioner(self):
        ids = {i.check_id for i in check_bundle(build_kenya_eclaims_bundle(_base_claim(practitioner_id="")))}
        assert {"REQUIRED_RESOURCES", "CARETEAM_PRACTITIONER"} <= ids

    def test_unresolved_reference(self):
        bundle = self._bundle()
        _resource(bundle, "Claim")["patient"]["reference"] = "Patient/nowhere"
        assert "REFERENCES_RESOLVE" in {i.check_id for i in check_bundle(bundle)}

    def test_missing_full_url(self):
        bundle = self._bundle()
        del bundle["entry"][2]["fullUrl"]
        assert "FULLURL_PRESENT" in {i.check_id for i in check_bundle(bundle)}

    def test_total_mismatch(self):
        bundle = self._bundle()
        _resource(bundle, "Claim")["total"]["value"] = 1
        assert "TOTAL_MATCHES_NET" in {i.check_id for i in check_bundle(bundle)}

    def test_insurance_must_point_at_coverage(self):
        bundle = self._bundle()
        claim = _resource(bundle, "Claim")
        claim["insurance"][0]["coverage"] = copy.deepcopy(claim["patient"])
        assert "INSURANCE_COVERAGE" in {i.check_id for i in check_bundle(bundle)}

    def test_wrong_bundle_type(self):
        bundle = self._bundle()
        bundle["type"] = "collection"
        assert "BUNDLE_TYPE" in {i.check_id for i in check_bundle(bundle)}


class TestClaimState:
    @staticmethod
    def _response(code, system="https://nshr-uat.sha.go.ke/fhir/CodeSystem/claim-state-cs",
                  url="https://nshr-uat.sha.go.ke/fhir/StructureDefinition/eclaim-state-extension"):
        return {"resourceType": "ClaimResponse", "extension": [
            {"url": url, "valueCodeableConcept": {"coding": [{"system": system, "code": code}]}}
        ]}

    @pytest.mark.parametrize("code,state", [
        ("queued", "queued"), ("approved", "approved"), ("rejected", "rejected"),
        ("in-review", "in_review"), ("clinical-review", "clinical_review"),
        ("sent-for-payment-processing", "payment_processing"), ("sent-to-surveillance", "surveillance"),
        ("payment-completed", "paid"), ("payment-declined", "payment_declined"),
        ("sent-back", "sent_back"), ("canceled", "cancelled"), ("pending", "queued"), ("under-review", "in_review"),
    ])
    def test_known_states(self, code, state):
        parsed = parse_claim_state(self._response(code))
        assert parsed["state"] == state and parsed["sha_code"] == code

    def test_sent_back_needs_action(self):
        assert parse_claim_state(self._response("sent-back"))["action_needed"] is True

    def test_alternative_extension_url(self):
        resp = self._response("approved", url="https://fhir.sha.go.ke/fhir/StructureDefinition/claim-state-extension")
        assert parse_claim_state(resp)["state"] == "approved"

    def test_unknown_code_is_flagged(self):
        parsed = parse_claim_state(self._response("something-new"))
        assert parsed["state"] == "unknown" and "something-new" in parsed["label"]

    def test_no_extension(self):
        assert parse_claim_state({"resourceType": "ClaimResponse"}) is None


def test_claim_status_stub_parses_state(monkeypatch):
    body = {"resourceType": "Bundle", "entry": [{"resource": TestClaimState._response("sent-back")}]}

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None):
            assert url.endswith("/ClaimResponse") and params["request"] == "Claim/C-1"
            return httpx.Response(200, json=body, request=httpx.Request("GET", url))

    monkeypatch.setattr(sha_client_module.httpx, "AsyncClient", FakeClient)
    import asyncio
    result = asyncio.run(sha_client_module.sha_client.claim_status("C-1"))
    assert result["ok"] and result["claim_state"]["state"] == "sent_back"
