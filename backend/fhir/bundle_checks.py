"""
Structural checks on a Kenya eClaims Bundle, run before any submission.

Mirrors the AfyaLink claim integration checklist for bundle structure:
  - every entry has a fullUrl, and every reference resolves to one
  - Patient, Coverage, Organization, Practitioner and Claim are present
  - Claim.insurance points at a Coverage; Claim.careTeam at a Practitioner
  - Claim.total equals the sum of item net amounts
  - every item has a servicedPeriod

check_bundle() returns a list of BundleIssue; empty means the bundle passed.
"""

from dataclasses import dataclass, field
from typing import Iterator

REQUIRED_TYPES = ("Claim", "Patient", "Coverage", "Organization", "Practitioner")


@dataclass
class BundleIssue:
    check_id: str
    message: str
    fields: list[str] = field(default_factory=list)  # claim fields that fix it, for the UI


def _references(node) -> Iterator[str]:
    """Every Reference.reference string anywhere in a resource."""
    if isinstance(node, dict):
        if isinstance(node.get("reference"), str):
            yield node["reference"]
        for value in node.values():
            yield from _references(value)
    elif isinstance(node, list):
        for value in node:
            yield from _references(value)


def check_bundle(bundle: dict) -> list[BundleIssue]:
    issues: list[BundleIssue] = []
    entries = bundle.get("entry") or []

    if bundle.get("type") != "message":
        issues.append(BundleIssue("BUNDLE_TYPE", f'Bundle.type is "{bundle.get("type")}", SHA expects "message"'))
    if not entries or (entries[0].get("resource") or {}).get("resourceType") != "MessageHeader":
        issues.append(BundleIssue("MESSAGE_HEADER", "A message Bundle must start with a MessageHeader"))

    missing_full_url = [i for i, e in enumerate(entries) if not e.get("fullUrl")]
    if missing_full_url:
        issues.append(BundleIssue("FULLURL_PRESENT", f"Entries {missing_full_url} have no fullUrl"))

    by_url = {e["fullUrl"]: e.get("resource") or {} for e in entries if e.get("fullUrl")}
    types = [(e.get("resource") or {}).get("resourceType") for e in entries]

    unresolved = sorted({
        ref for e in entries for ref in _references(e.get("resource")) if ref not in by_url
    })
    if unresolved:
        issues.append(BundleIssue("REFERENCES_RESOLVE", f"References not found in the Bundle: {', '.join(unresolved)}"))

    for rtype in REQUIRED_TYPES:
        if rtype not in types:
            fields = ["practitioner_id"] if rtype == "Practitioner" else []
            issues.append(BundleIssue("REQUIRED_RESOURCES", f"No {rtype} resource in the Bundle", fields))

    claims = [r for r in by_url.values() if r.get("resourceType") == "Claim"]
    if not claims:
        return issues
    claim = claims[0]

    coverages = [
        by_url.get(ins.get("coverage", {}).get("reference"), {}).get("resourceType")
        for ins in claim.get("insurance") or []
    ]
    if "Coverage" not in coverages:
        issues.append(BundleIssue("INSURANCE_COVERAGE", "Claim.insurance does not reference a Coverage in the Bundle"))

    care_team = [
        by_url.get(member.get("provider", {}).get("reference"), {}).get("resourceType")
        for member in claim.get("careTeam") or []
    ]
    if "Practitioner" not in care_team:
        issues.append(BundleIssue(
            "CARETEAM_PRACTITIONER",
            "No treating practitioner: Claim.careTeam must reference a Practitioner in the Bundle",
            ["practitioner_id"],
        ))

    items = claim.get("item") or []
    net_sum = round(sum((i.get("net") or {}).get("value", 0) for i in items), 2)
    total = (claim.get("total") or {}).get("value")
    if total is None or round(total, 2) != net_sum:
        issues.append(BundleIssue("TOTAL_MATCHES_NET", f"Claim.total {total} does not equal the item net sum {net_sum}"))

    no_period = [i.get("sequence") for i in items if not (i.get("servicedPeriod") or {}).get("start") or not (i.get("servicedPeriod") or {}).get("end")]
    if no_period:
        issues.append(BundleIssue("ITEM_SERVICED_PERIOD", f"Items {no_period} have no complete servicedPeriod"))

    if not claim.get("billablePeriod"):
        issues.append(BundleIssue("BILLABLE_PERIOD", "Claim.billablePeriod is missing"))

    return issues


# Checks that repeat a claim-level validation rule. They still block submission,
# but the FHIR_BUNDLE_VALID rule skips them so a claim is not penalised twice.
COVERED_BY_CLAIM_RULES = {"TOTAL_MATCHES_NET", "ITEM_SERVICED_PERIOD", "BILLABLE_PERIOD"}
