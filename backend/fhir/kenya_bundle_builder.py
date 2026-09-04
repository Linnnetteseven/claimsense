"""
Kenya eClaims Bundle builder.

Builds the provider-side Bundle described by the Kenya eClaims
implementation guidance.

The Bundle contains:
    Claim
    Patient
    Coverage
    Provider Organization
    SHA Organization
    Encounter
    Condition

This is a submission artifact.

It is NOT a ClaimResponse.
"""

from datetime import datetime, timezone
from uuid import uuid4


BASE_PROFILE = "https://fhir.dha.go.ke/claims/StructureDefinition"

CLAIM_PROFILE = (
    f"{BASE_PROFILE}/ke-eclaims-claimsubmission"
)

PATIENT_PROFILE = (
    f"{BASE_PROFILE}/ke-eclaims-patient"
)

COVERAGE_PROFILE = (
    f"{BASE_PROFILE}/ke-eclaims-coverage"
)

ORGANIZATION_PROFILE = (
    f"{BASE_PROFILE}/ke-eclaims-organization"
)

ENCOUNTER_PROFILE = (
    f"{BASE_PROFILE}/ke-eclaims-encounter"
)

CONDITION_PROFILE = (
    f"{BASE_PROFILE}/ke-eclaims-condition"
)


def _reference(resource_type: str, resource_id: str) -> dict:
    return {
        "reference": f"{resource_type}/{resource_id}"
    }


def _profile(profile_url: str) -> dict:
    return {
        "profile": [profile_url]
    }


def build_kenya_eclaims_bundle(claim: dict) -> dict:
    """
    Convert ClaimSense's internal claim representation into
    a self-contained Kenya eClaims collection Bundle.

    The function intentionally keeps unknown fields conservative.
    It does not invent patient demographics or coverage details.
    """

    claim_id = claim.get("id") or f"CLM-{uuid4()}"

    patient_id = claim.get("patient_id") or f"patient-{claim_id}"
    facility_id = (
        claim.get("facility_code")
        or f"provider-{claim_id}"
    )

    encounter_id = (
        claim.get("encounter_id")
        or f"enc-{claim_id}"
    )

    condition_id = (
        claim.get("condition_id")
        or f"condition-{claim_id}"
    )

    coverage_id = (
        claim.get("coverage_id")
        or f"coverage-{claim_id}"
    )

    sha_org_id = (
        claim.get("insurer_id")
        or "sha"
    )

    provider_org_id = facility_id

    visit_date = (
        claim.get("visit_date")
        or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    )

    patient_name = claim.get(
        "patient_name",
        "Unknown Patient",
    )

    facility_name = claim.get(
        "facility_name",
        "Unknown Facility",
    )

    diagnosis_code = claim.get(
        "diagnosis_code",
        "",
    )

    diagnosis_description = claim.get(
        "diagnosis_description",
        "",
    )

    # ---------------------------------------------------------
    # Patient
    # ---------------------------------------------------------

    patient = {
        "resourceType": "Patient",
        "id": patient_id,
        "meta": _profile(PATIENT_PROFILE),
        "identifier": [],
        "name": [
            {
                "text": patient_name,
            }
        ],
    }

    # Preserve SHA/NATIONAL ID if supplied by the draft.
    if claim.get("sha_number"):
        patient["identifier"].append(
            {
                "type": {
                    "coding": [
                        {
                            "system": (
                                "https://fhir.dha.go.ke/"
                                "claims/CodeSystem/"
                                "identifier-type"
                            ),
                            "code": "SHA-NUMBER",
                        }
                    ]
                },
                "value": claim["sha_number"],
            }
        )

    elif claim.get("national_id"):
        patient["identifier"].append(
            {
                "type": {
                    "coding": [
                        {
                            "system": (
                                "https://fhir.dha.go.ke/"
                                "claims/CodeSystem/"
                                "identifier-type"
                            ),
                            "code": "NATIONAL-ID",
                        }
                    ]
                },
                "value": claim["national_id"],
            }
        )

    if claim.get("gender"):
        patient["gender"] = claim["gender"]

    if claim.get("dob"):
        patient["birthDate"] = claim["dob"]

    # ---------------------------------------------------------
    # Provider Organization
    # ---------------------------------------------------------

    provider = {
        "resourceType": "Organization",
        "id": provider_org_id,
        "meta": _profile(ORGANIZATION_PROFILE),
        "active": True,
        "identifier": [],
        "name": facility_name,
    }

    if claim.get("facility_code"):
        provider["identifier"].append(
            {
                "value": claim["facility_code"],
            }
        )

    # ---------------------------------------------------------
    # SHA Organization
    # ---------------------------------------------------------

    insurer = {
        "resourceType": "Organization",
        "id": sha_org_id,
        "meta": _profile(ORGANIZATION_PROFILE),
        "active": True,
        "name": "Social Health Authority Kenya",
    }

    # ---------------------------------------------------------
    # Encounter
    # ---------------------------------------------------------

    encounter = {
        "resourceType": "Encounter",
        "id": encounter_id,
        "meta": _profile(ENCOUNTER_PROFILE),
        "status": "finished",
        "class": {
            "system": (
                "http://terminology.hl7.org/"
                "CodeSystem/v3-ActCode"
            ),
            "code": "AMB",
            "display": "ambulatory",
        },
        "subject": _reference(
            "Patient",
            patient_id,
        ),
        "period": {
            "start": visit_date,
            "end": visit_date,
        },
        "serviceProvider": _reference(
            "Organization",
            provider_org_id,
        ),
    }

    # ---------------------------------------------------------
    # Condition
    # ---------------------------------------------------------

    condition = {
        "resourceType": "Condition",
        "id": condition_id,
        "meta": _profile(CONDITION_PROFILE),
        "clinicalStatus": {
            "coding": [
                {
                    "system": (
                        "http://terminology.hl7.org/"
                        "CodeSystem/condition-clinical"
                    ),
                    "code": "active",
                }
            ]
        },
        "verificationStatus": {
            "coding": [
                {
                    "system": (
                        "http://terminology.hl7.org/"
                        "CodeSystem/condition-ver-status"
                    ),
                    "code": "confirmed",
                }
            ]
        },
        "code": {
            "coding": [],
            "text": diagnosis_description,
        },
        "subject": _reference(
            "Patient",
            patient_id,
        ),
        "encounter": _reference(
            "Encounter",
            encounter_id,
        ),
    }

    if diagnosis_code:
        condition["code"]["coding"].append(
            {
                "code": diagnosis_code,
                "display": diagnosis_description,
            }
        )

    # ---------------------------------------------------------
    # Coverage
    # ---------------------------------------------------------

    coverage = {
        "resourceType": "Coverage",
        "id": coverage_id,
        "meta": _profile(COVERAGE_PROFILE),
        "status": "active",
        "beneficiary": _reference(
            "Patient",
            patient_id,
        ),
        "payor": [
            _reference(
                "Organization",
                sha_org_id,
            )
        ],
    }

    if claim.get("coverage_start_date"):
        coverage["period"] = {
            "start": claim["coverage_start_date"],
        }

        if claim.get("coverage_end_date"):
            coverage["period"]["end"] = (
                claim["coverage_end_date"]
            )

    if claim.get("scheme_code"):
        coverage["class"] = [
            {
                "type": {
                    "coding": [
                        {
                            "code": "plan",
                        }
                    ]
                },
                "value": claim["scheme_code"],
            }
        ]

    # ---------------------------------------------------------
    # Claim
    # ---------------------------------------------------------

    claim_resource = {
        "resourceType": "Claim",
        "id": claim_id,
        "meta": _profile(CLAIM_PROFILE),
        "identifier": [
            {
                "system": (
                    claim.get("claim_identifier_system")
                    or "https://claimsense.ke/claim"
                ),
                "value": claim_id,
            }
        ],
        "status": "active",
        "type": {
            "coding": [
                {
                    "system": (
                        "http://terminology.hl7.org/"
                        "CodeSystem/claim-type"
                    ),
                    "code": "professional",
                }
            ]
        },
        "use": "claim",
        "patient": _reference(
            "Patient",
            patient_id,
        ),
        "created": datetime.now(
            timezone.utc
        ).strftime("%Y-%m-%d"),
        "provider": _reference(
            "Organization",
            provider_org_id,
        ),
        "insurer": _reference(
            "Organization",
            sha_org_id,
        ),
        "priority": {
            "coding": [
                {
                    "system": (
                        "http://terminology.hl7.org/"
                        "CodeSystem/processpriority"
                    ),
                    "code": "normal",
                }
            ]
        },
        "insurance": [
            {
                "sequence": 1,
                "focal": True,
                "coverage": _reference(
                    "Coverage",
                    coverage_id,
                ),
            }
        ],
        "billablePeriod": {
            "start": visit_date,
            "end": visit_date,
        },
        "diagnosis": [],
        "item": [],
        "total": {
            "value": float(
                claim.get("claimed_amount", 0)
            ),
            "currency": "KES",
        },
    }

    if diagnosis_code:
        claim_resource["diagnosis"].append(
            {
                "sequence": 1,
                "diagnosisCodeableConcept": {
                    "coding": [
                        {
                            "code": diagnosis_code,
                            "display": diagnosis_description,
                        }
                    ]
                },
            }
        )

    for index, item in enumerate(
        claim.get("items", []),
        start=1,
    ):
        service_code = item.get(
            "service_code",
            "",
        )

        item_resource = {
            "sequence": index,
            "productOrService": {
                "coding": [
                    {
                        "code": service_code,
                        "display": item.get(
                            "description",
                            "",
                        ),
                    }
                ]
            },
            "quantity": {
                "value": float(
                    item.get("quantity", 1)
                )
            },
            "unitPrice": {
                "value": float(
                    item.get("unit_price", 0)
                ),
                "currency": "KES",
            },
        }

        claim_resource["item"].append(
            item_resource
        )

    # ---------------------------------------------------------
    # Bundle
    # ---------------------------------------------------------

    resources = [
        claim_resource,
        patient,
        coverage,
        provider,
        insurer,
        encounter,
        condition,
    ]

    bundle = {
        "resourceType": "Bundle",
        "id": f"B-{claim_id}",
        "type": "collection",
        "timestamp": datetime.now(
            timezone.utc
        ).isoformat(),
        "entry": [
            {
                "fullUrl": (
                    f"urn:uuid:{uuid4()}"
                ),
                "resource": resource,
            }
            for resource in resources
        ],
    }

    return bundle
