"""
Kenya eClaims Claim Bundle builder.

Builds the provider-side submission Bundle from Hakiki's internal claim shape,
following the AfyaLink claim integration guide and the DHA Kenya eClaims FHIR IG
(KenyaClaimSubmission profile and its examples):

  - Bundle.type "message" with a MessageHeader first (FHIR bdl-12). Checked against SHA UAT
    $validate: no errors (scripts/uat_validate.py). SHA's own example request for the SHR
    mediator (POST /v1/shr-med/post-bundle) omits the MessageHeader and SHA has published no
    event code; SHA_BUNDLE_MESSAGE_HEADER=false drops it if the mediator rejects it.
  - fullUrl on every entry; every reference points at a fullUrl in the Bundle
  - Claim, Patient, Coverage, provider and insurer Organization, Practitioner
  - Claim.insurance -> Coverage, Claim.careTeam -> Practitioner
  - items with sequence, servicedPeriod, category, net and SHA intervention codes
  - diagnosis coded with the ICD-11 code system

Code system and identifier URLs are built from SHA_TERMINOLOGY_BASE (UAT prefix by default);
they match the code systems hosted on nshr-uat.sha.go.ke. The diagnosis system is
SHA_DIAGNOSIS_SYSTEM (IG example: icd11-codes-cs). Run fhir.bundle_checks.check_bundle()
before handing the bundle on.

It does not invent patient demographics or coverage details; missing inputs leave
the matching elements out so bundle_checks and the validation rules report them.
"""

from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from config import config
from data.sha_tariffs import get_intervention
from validation.rules import billable_period, item_net, net_total

HL7 = "http://terminology.hl7.org/CodeSystem"


def _base() -> str:
    return config.SHA_TERMINOLOGY_BASE.rstrip("/")


def code_system(name: str) -> str:
    return f"{_base()}/CodeSystem/{name}"


def identifier_system(name: str) -> str:
    return f"{_base()}/Identifier/{name}"


def profile(name: str) -> dict:
    return {"profile": [f"{_base()}/StructureDefinition/{name}"]}


def _full_url(claim_id: str, kind: str) -> str:
    """Stable urn:uuid per claim and resource, so rebuilding gives the same Bundle ids."""
    return f"urn:uuid:{uuid5(NAMESPACE_URL, f'hakiki/{claim_id}/{kind}')}"


def _ref(full_url: str) -> dict:
    return {"reference": full_url}


def _money(value) -> dict:
    return {"value": round(float(value or 0), 2), "currency": "KES"}


def _coding(system: str, code: str, display: str = "") -> dict:
    coding = {"system": system, "code": code}
    if display:
        coding["display"] = display
    return {"coding": [coding]}


def claim_subtype(claim: dict) -> str:
    """IG claim-subtype-cs code. Explicit claim_subtype wins; else inpatient if the stay spans days."""
    if claim.get("claim_subtype"):
        return str(claim["claim_subtype"])
    start, end = billable_period(claim)
    return "inpatient" if start and end and end > start else "outpatient"


def build_kenya_eclaims_bundle(claim: dict) -> dict:
    claim_id = str(claim.get("id") or "draft")
    urls = {
        kind: _full_url(claim_id, kind)
        for kind in ("header", "claim", "patient", "coverage", "provider", "insurer", "practitioner")
    }
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    start, end = billable_period(claim)

    # --- Patient -----------------------------------------------------------
    patient = {"resourceType": "Patient", "meta": profile("ke-eclaims-patient"), "identifier": []}
    if claim.get("patient_id"):
        patient["identifier"].append({
            "type": _coding(code_system("identifier-types-cs"), "SHA-NUMBER", "SHA Number"),
            "system": identifier_system("sha-number"),
            "value": str(claim["patient_id"]),
        })
    if claim.get("patient_name"):
        patient["name"] = [{"text": claim["patient_name"]}]
    gender = {"F": "female", "M": "male"}.get(str(claim.get("gender", "")).upper())
    if gender:
        patient["gender"] = gender
    if claim.get("dob"):
        patient["birthDate"] = claim["dob"]

    # --- Organizations -----------------------------------------------------
    provider = {
        "resourceType": "Organization",
        "meta": profile("ke-eclaims-organization"),
        "active": True,
        "name": claim.get("facility_name") or "",
        "identifier": [],
    }
    if claim.get("facility_code"):
        provider["identifier"].append({
            "use": "official",
            "type": _coding(f"{HL7}/v2-0203", "PRN", "Provider number"),
            "value": str(claim["facility_code"]),
        })
    insurer = {
        "resourceType": "Organization",
        "meta": profile("ke-eclaims-organization"),
        "active": True,
        "name": "Social Health Authority",
    }

    # --- Practitioner (only when the claim names one) ----------------------
    practitioner = None
    if claim.get("practitioner_id"):
        practitioner = {
            "resourceType": "Practitioner",
            "meta": profile("ke-eclaims-practitioner"),
            "identifier": [{
                "type": _coding(code_system("identifier-types-cs"), "SHA-NUMBER", "SHA Number"),
                "system": identifier_system("provider-number"),
                "value": str(claim["practitioner_id"]),
            }],
        }
        if claim.get("practitioner_name"):
            practitioner["name"] = [{"text": claim["practitioner_name"]}]

    # --- Coverage ----------------------------------------------------------
    coverage = {
        "resourceType": "Coverage",
        "meta": profile("ke-eclaims-coverage"),
        "status": "active",
        "beneficiary": _ref(urls["patient"]),
        "payor": [_ref(urls["insurer"])],
    }
    if claim.get("patient_id"):
        coverage["identifier"] = [{
            "system": identifier_system("coverage-number"),
            "value": f"{claim['patient_id']}-sha-coverage",
        }]
    period = {k: v for k, v in (("start", claim.get("coverage_start_date")), ("end", claim.get("coverage_end_date"))) if v}
    if period:
        coverage["period"] = period

    # --- Claim -------------------------------------------------------------
    items = []
    for item in claim.get("items") or []:
        code = str(item.get("service_code", "")).strip().upper()
        official = get_intervention(code)
        # Display must be SHA's name for the code (UAT warns otherwise); the facility's own
        # wording goes in text.
        # A missing code is left out rather than sent empty (FHIR rejects empty values).
        product = _coding(
            code_system("KenyaSocialHealthAuthorityInterventionCS"),
            code,
            official.description if official else "",
        ) if code else {}
        if item.get("description"):
            product["text"] = item["description"]
        entry = {
            "sequence": item.get("sequence"),
            "productOrService": product,
            "category": _coding(f"{HL7}/ex-benefitcategory", "1", "Medical Care"),
            "quantity": {"value": float(item.get("quantity") or 0)},
            "unitPrice": _money(item.get("unit_price")),
            "net": _money(item_net(item)),
        }
        served = {k: item.get(f"service_{k}") for k in ("start", "end") if item.get(f"service_{k}")}
        if served:
            entry["servicedPeriod"] = served
        if practitioner:
            entry["careTeamSequence"] = [1]
        items.append(entry)

    claim_resource = {
        "resourceType": "Claim",
        "meta": profile("ke-eclaims-claimsubmission"),
        "identifier": [{"system": identifier_system("claim-number"), "value": claim_id}],
        "status": "active",
        "type": _coding(code_system("claim-type-cs"), "institutional", "Institutional"),
        "subType": _coding(code_system("claim-subtype-cs"), claim_subtype(claim)),
        "use": "claim",
        "patient": _ref(urls["patient"]),
        "created": now,
        "insurer": _ref(urls["insurer"]),
        "provider": _ref(urls["provider"]),
        "priority": _coding(f"{HL7}/processpriority", "normal", "Normal"),
        "payee": {"type": _coding(f"{HL7}/payeetype", "provider", "Provider")},
        "insurance": [{"sequence": 1, "focal": True, "coverage": _ref(urls["coverage"])}],
        "item": items,
        "total": _money(net_total(claim)),
        "extension": [{
            "url": f"{_base()}/StructureDefinition/eclaims-patient-invoice",
            "extension": [
                {"url": "invoiceNumber", "valueString": claim_id},
                {"url": "invoiceDate", "valueDate": now[:10]},
                {"url": "invoiceAmount", "valueMoney": _money(claim.get("claimed_amount"))},
            ],
        }],
    }
    if start and end:
        claim_resource["billablePeriod"] = {"start": start.isoformat(), "end": end.isoformat()}
    if practitioner:
        claim_resource["careTeam"] = [{
            "sequence": 1,
            "provider": _ref(urls["practitioner"]),
            "role": _coding(code_system("claim-care-team-role-cs"), "PRIMARY", "Primary provider"),
        }]
    if claim.get("diagnosis_code"):
        claim_resource["diagnosis"] = [{
            "sequence": 1,
            "diagnosisCodeableConcept": _coding(
                code_system(config.SHA_DIAGNOSIS_SYSTEM),
                str(claim["diagnosis_code"]).strip().upper(),
                claim.get("diagnosis_description", ""),
            ),
        }]
    if claim.get("preauth_ref"):
        claim_resource["insurance"][0]["preAuthRef"] = [str(claim["preauth_ref"])]

    # --- Bundle ------------------------------------------------------------
    resources = []
    if config.SHA_BUNDLE_MESSAGE_HEADER:
        resources.append(("header", {
            "resourceType": "MessageHeader",
            # SHA has not published a message event code; this one is Hakiki's own.
            "eventCoding": {"system": code_system("message-event"), "code": "claim-submission"},
            "source": {"endpoint": f"urn:hakiki:facility:{claim.get('facility_code') or 'unknown'}"},
            "sender": _ref(urls["provider"]),
            "focus": [_ref(urls["claim"])],
        }))
    resources += [
        ("claim", claim_resource),
        ("patient", patient),
        ("coverage", coverage),
        ("provider", provider),
        ("insurer", insurer),
    ]
    if practitioner:
        resources.append(("practitioner", practitioner))

    for _, resource in resources:
        # FHIR rejects empty arrays; drop any left empty by missing claim data.
        for key in [k for k, v in resource.items() if v == []]:
            del resource[key]

    entries = []
    for kind, resource in resources:
        resource["id"] = urls[kind].rsplit(":", 1)[-1]
        entries.append({"fullUrl": urls[kind], "resource": resource})

    return {
        "resourceType": "Bundle",
        "id": _full_url(claim_id, "bundle").rsplit(":", 1)[-1],
        "type": "message",
        "timestamp": now,
        "entry": entries,
    }
