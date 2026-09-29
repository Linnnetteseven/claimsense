"""
SHA claim validation rules, as a registry.

Each rule is a Rule(id, version, severity, fields, source_url, check). check(claim)
returns None when the claim passes, or a Finding describing the failure. The engine
reads REGISTRY; severity and metadata live here, not inside the checks.

Claim fields used (internal claim shape, not FHIR):
  patient_id, facility_code, visit_date, diagnosis_code, coverage_end_date,
  claimed_amount, fund ("SHIF" | "PHC" | "ECCIF"), preauth_ref, facility_level ("2".."6"),
  gender, dob, discharge_date,
  billable_start / billable_end (default: visit_date / discharge_date or visit_date),
  practitioner_id (PUID), practitioner_name,
  items[]: sequence, service_code, description, quantity, unit_price, net,
           service_start, service_end

Adding a rule: write a check function, add a Rule to REGISTRY, add pass/fail tests.
"""

import re
from dataclasses import dataclass, field as dc_field
from datetime import date, datetime
from typing import Callable, Optional

from data.sha_tariffs import get_intervention
from terminology import icd11

AFYALINK = "https://afyalink.dha.go.ke/claim-integration"
OCL_INTERVENTIONS = "https://ilm-hie.dha.go.ke/ocl/orgs/MOH-KENYA/ValueSet/KenyaSocialHealthAuthorityInterventions/"


@dataclass
class Finding:
    """What a failing check reports. Metadata (severity, source) comes from the Rule."""
    message: str
    suggestion: str
    fields: Optional[list[str]] = None        # overrides the rule's default fields
    suggested_value: Optional[object] = None  # only when it can be computed exactly
    suggested_label: Optional[str] = None     # how to describe a non-scalar suggested_value


@dataclass(frozen=True)
class Rule:
    id: str
    version: str
    severity: str             # "error" deducts 20 points, "warning" 10
    fields: tuple[str, ...]   # claim fields the officer edits to clear the rule
    source_url: Optional[str]
    source_label: str
    check: Callable[[dict], Optional[Finding]]


@dataclass
class RuleResult:
    rule_id: str
    passed: bool
    severity: str
    field: Optional[str]   # first field, kept for older clients
    message: str
    suggestion: str        # advice text, never a field value
    fields: list[str] = dc_field(default_factory=list)
    suggested_value: Optional[object] = None
    suggested_label: Optional[str] = None
    rule_version: str = ""
    source_url: Optional[str] = None
    source_label: str = ""

    def to_dict(self) -> dict:
        out = {
            "rule_id": self.rule_id,
            "passed": self.passed,
            "severity": self.severity,
            "field": self.field,
            "fields": self.fields,
            "message": self.message,
            "suggestion": self.suggestion,
            "rule_version": self.rule_version,
            "source_url": self.source_url,
            "source_label": self.source_label,
        }
        if self.suggested_value is not None:
            out["suggested_value"] = self.suggested_value
            if self.suggested_label:
                out["suggested_label"] = self.suggested_label
        return out


def run_rule(rule: "Rule", claim: dict) -> RuleResult:
    finding = rule.check(claim)
    if finding is None:
        return RuleResult(
            rule.id, True, rule.severity, None, "Check passed", "",
            rule_version=rule.version, source_url=rule.source_url, source_label=rule.source_label,
        )
    fields = finding.fields or list(rule.fields)
    return RuleResult(
        rule.id, False, rule.severity, fields[0] if fields else None,
        finding.message, finding.suggestion, fields,
        finding.suggested_value, finding.suggested_label,
        rule.version, rule.source_url, rule.source_label,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _parse_date(value) -> Optional[date]:
    """Date part only; SHA ignores time. Accepts YYYY-MM-DD or an ISO datetime."""
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _items(claim: dict) -> list[dict]:
    items = claim.get("items") or []
    return items if isinstance(items, list) else []


def item_net(item: dict) -> float:
    """Item net amount: explicit net, else quantity x unit price."""
    if item.get("net") not in (None, ""):
        return _to_float(item.get("net"))
    return _to_float(item.get("quantity")) * _to_float(item.get("unit_price"))


def net_total(claim: dict) -> float:
    return round(sum(item_net(i) for i in _items(claim)), 2)


def billable_period(claim: dict) -> tuple[Optional[date], Optional[date]]:
    start = _parse_date(claim.get("billable_start") or claim.get("visit_date"))
    end = _parse_date(
        claim.get("billable_end") or claim.get("discharge_date") or claim.get("visit_date")
    )
    return start, end


def _is_maternity(claim: dict) -> bool:
    # ICD-11 chapter 18 (pregnancy, childbirth, puerperium) codes start with JA or JB.
    diagnosis = str(claim.get("diagnosis_code", "")).strip().upper()
    return str(claim.get("department", "")).strip().lower() == "maternity" or diagnosis[:2] in ("JA", "JB")


def _describe(item: dict, idx: int) -> str:
    return f'item {idx} ("{item.get("description") or item.get("service_code") or "unnamed"}")'


def _capitalize(text: str) -> str:
    return text[:1].upper() + text[1:]


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

_REQUIRED = {
    "patient_id": "Patient / client registry ID",
    "facility_code": "Health facility code (FID)",
    "visit_date": "Date of visit",
    "diagnosis_code": "ICD-11 diagnosis code",
}


def check_required_fields(claim: dict) -> Optional[Finding]:
    missing = [k for k in _REQUIRED if not str(claim.get(k, "")).strip()]
    if not missing:
        return None
    return Finding(
        f"Required fields are empty: {', '.join(_REQUIRED[k] for k in missing)}",
        "Fill in all highlighted fields. SHA rejects any claim missing these values.",
        fields=missing,
    )


def check_icd11(claim: dict) -> Optional[Finding]:
    code = str(claim.get("diagnosis_code", "")).strip()
    if not code:
        return None  # reported by MISSING_FIELDS
    reason = icd11.format_error(code)
    if reason and icd11.looks_like_icd10(code):
        return Finding(
            f'"{code}" looks like an ICD-10 code. SHA requires ICD-11 on every claim',
            "Find the matching ICD-11 code in the WHO ICD-11 browser (for example pneumonia "
            "is CA40.Z in ICD-11, J18.9 in ICD-10) and enter that instead.",
        )
    if reason:
        return Finding(
            f'"{code}" is not a valid ICD-11 code: {reason}',
            "ICD-11 codes look like 1A00, CA40.Z or DB10.02 and never use the letters I or O. "
            "Check the WHO ICD-11 browser.",
        )
    if icd11.lookup(code) is False:
        return Finding(
            f'"{code}" has a valid ICD-11 format but was not found in WHO ICD-11 ({icd11.lookup_release()})',
            "Check the code in the WHO ICD-11 browser; it may be a typo or a retired code.",
        )
    return None


def check_visit_date(claim: dict) -> Optional[Finding]:
    raw = str(claim.get("visit_date", "")).strip()
    if not raw:
        return None  # reported by MISSING_FIELDS
    visit = _parse_date(raw)
    if visit is None:
        return Finding(
            f'Visit date "{raw}" is not in YYYY-MM-DD format',
            "Use the format YYYY-MM-DD, for example 2026-07-03.",
        )
    if visit > date.today():
        return Finding(
            f"Visit date {raw} is {(visit - date.today()).days} day(s) in the future",
            "SHA only accepts claims for services already rendered. Correct the date.",
        )
    return None


def check_items_present(claim: dict) -> Optional[Finding]:
    items = _items(claim)
    if not items:
        return Finding(
            "No service items are listed on this claim",
            "Add at least one service item with a SHA intervention code.",
        )
    for idx, item in enumerate(items, start=1):
        if not str(item.get("service_code", "")).strip():
            return Finding(
                f"{_capitalize(_describe(item, idx))} has no intervention code",
                "Every item must carry a SHA intervention code (productOrService).",
            )
    return None


# SHA-NN-NNN intervention, optionally a -SI-NNN sub-intervention (e.g. oncology medicines).
_BILLABLE_CODE = re.compile(r"^(SHA|PMF)-\d{2}-\d{3}(-SI-\d{3})?$")
_CHAPTER_CODE = re.compile(r"^(SHA|PMF)-\d{2}(-SC-\d{2})?$")


def check_service_code_format(claim: dict) -> Optional[Finding]:
    bad = []
    for idx, item in enumerate(_items(claim), start=1):
        code = str(item.get("service_code", "")).strip().upper()
        if code and not _BILLABLE_CODE.match(code):
            kind = (
                "a benefit chapter, not a billable intervention"
                if _CHAPTER_CODE.match(code)
                else "not a SHA intervention code"
            )
            bad.append(f'{_describe(item, idx)}: "{code}" is {kind}')
    if not bad:
        return None
    return Finding(
        _capitalize("; ".join(bad)),
        "SHA intervention codes look like SHA-12-001 (chapter 12, intervention 001). "
        "Use the code from the SHA benefits and tariffs list.",
    )


def check_quantity(claim: dict) -> Optional[Finding]:
    for idx, item in enumerate(_items(claim), start=1):
        if _to_float(item.get("quantity")) <= 0:
            return Finding(
                f"{_capitalize(_describe(item, idx))} has a quantity of {item.get('quantity')}",
                "Quantity must be a positive number.",
            )
    return None


def check_serviced_period_present(claim: dict) -> Optional[Finding]:
    items = _items(claim)
    missing = [
        idx for idx, item in enumerate(items, start=1)
        if not (_parse_date(item.get("service_start")) and _parse_date(item.get("service_end")))
    ]
    if not missing:
        return None
    finding = Finding(
        f"Item(s) {', '.join(map(str, missing))} have no complete service period (start and end date)",
        "Enter the date each service started and ended. SHA uses these dates to check the claim period.",
    )
    start, end = billable_period(claim)
    # A single-day claim leaves only one possible service date, so the fix is exact.
    if start and start == end:
        day = start.isoformat()
        finding.suggested_value = [
            {
                **item,
                "service_start": item.get("service_start") or day,
                "service_end": item.get("service_end") or day,
            }
            for item in items
        ]
        finding.suggested_label = f"fill missing service dates with {day}"
    return finding


def check_serviced_period_in_billable(claim: dict) -> Optional[Finding]:
    start, end = billable_period(claim)
    if not start or not end:
        return None  # nothing to compare against; the visit date rules report this
    outside = []
    for idx, item in enumerate(_items(claim), start=1):
        s, e = _parse_date(item.get("service_start")), _parse_date(item.get("service_end"))
        if not s or not e:
            continue  # reported by SERVICED_PERIOD_PRESENT
        if s > e:
            outside.append(f"item {idx} ends before it starts")
        elif s < start or e > end:
            outside.append(f"item {idx} ({s} to {e})")
    if not outside:
        return None
    return Finding(
        f"Service dates fall outside the claim period {start} to {end}: {'; '.join(outside)}",
        "Each item's service dates must fall within the claim's billable period (dates only, time "
        "is ignored). Correct the item dates or the claim period.",
        fields=["items", "billable_start", "billable_end"],
    )


def check_item_sequence(claim: dict) -> Optional[Finding]:
    items = _items(claim)
    if not items:
        return None
    try:
        seqs = [int(item.get("sequence")) for item in items]
    except (TypeError, ValueError):
        seqs = None
    if seqs is not None and sorted(seqs) == list(range(1, len(items) + 1)):
        return None
    if seqs is None:
        problem = "some items have no sequence number"
    elif len(set(seqs)) != len(seqs):
        problem = "sequence numbers are repeated"
    else:
        problem = f"sequence numbers {sorted(seqs)} are not 1 to {len(items)} without gaps"
    return Finding(
        f"Item sequence is invalid: {problem}",
        "Number the items 1, 2, 3 ... with no gaps or repeats. The same intervention code may "
        "appear more than once as long as each has its own sequence number.",
        suggested_value=[{**item, "sequence": n} for n, item in enumerate(items, start=1)],
        suggested_label=f"renumber items 1 to {len(items)} in their current order",
    )


def check_total_equals_net(claim: dict) -> Optional[Finding]:
    if not _items(claim):
        return None
    total = net_total(claim)
    claimed = round(_to_float(claim.get("claimed_amount")), 2)
    if claimed == total:
        return None
    return Finding(
        f"Claim total KES {claimed:,.2f} does not equal the sum of item net amounts KES {total:,.2f}",
        "SHA requires the claim total to match the item amounts exactly. Correct the total or the items.",
        suggested_value=total,
    )


def check_phc_zero_total(claim: dict) -> Optional[Finding]:
    if str(claim.get("fund", "")).strip().upper() != "PHC":
        return None
    claimed = _to_float(claim.get("claimed_amount"))
    if claimed == 0 and net_total(claim) == 0:
        return None
    return Finding(
        f"Primary Health Care (PHC) claims must have a zero total; this one totals KES {claimed:,.2f}",
        "PHC services are paid by capitation. Set item prices and the claim total to 0, "
        "or change the fund if this is not a PHC claim.",
        fields=["claimed_amount", "items", "fund"],
    )


def check_preauth(claim: dict) -> Optional[Finding]:
    if str(claim.get("preauth_ref", "")).strip():
        return None
    needing = sorted({
        f"{info.code} ({info.description}; {', '.join(info.preauth)} pre-authorization)"
        for item in _items(claim)
        if (info := get_intervention(item.get("service_code", ""))) and info.requires_preauth
    })
    if not needing:
        return None
    return Finding(
        f"No pre-authorization reference, but {', '.join(needing)} require(s) pre-authorization",
        "Request pre-authorization from SHA and enter the reference before submitting.",
    )


def check_tariff_ceiling(claim: dict) -> Optional[Finding]:
    over = []
    level = str(claim.get("facility_level") or "").strip() or None
    for idx, item in enumerate(_items(claim), start=1):
        info = get_intervention(item.get("service_code", ""))
        if not info:
            continue
        tariff, source = info.tariff_for(level)
        price = _to_float(item.get("unit_price"))
        if tariff is not None and price > tariff:
            over.append(
                f"{_describe(item, idx)} unit price KES {price:,.0f} exceeds the {source} KES {tariff:,.0f}"
            )
    if not over:
        return None
    return Finding(
        _capitalize("; ".join(over)),
        "SHA pays up to the tariff for each intervention; amounts above it will not be reimbursed. "
        "Tariffs come from the MOH OCL catalogue where set (see data/sha_interventions.csv).",
    )


def _catalogued_items(claim: dict):
    """(index, item, Intervention) for items whose code is in the SHA catalogue."""
    for idx, item in enumerate(_items(claim), start=1):
        info = get_intervention(item.get("service_code", ""))
        if info:
            yield idx, item, info


def _age_on(dob, on) -> Optional[int]:
    if not dob or not on:
        return None
    return on.year - dob.year - ((on.month, on.day) < (dob.month, dob.day))


def check_intervention_known(claim: dict) -> Optional[Finding]:
    unknown = [
        f'{_describe(item, idx)}: "{item.get("service_code")}"'
        for idx, item in enumerate(_items(claim), start=1)
        if _BILLABLE_CODE.match(str(item.get("service_code", "")).strip().upper())
        and not get_intervention(item.get("service_code", ""))
    ]
    if not unknown:
        return None
    return Finding(
        f"Not an active code in the SHA intervention catalogue: {'; '.join(unknown)}",
        "Check the code against the current SHA benefits list. Retired or inactive codes are rejected.",
    )


def check_intervention_eligibility(claim: dict) -> Optional[Finding]:
    gender = {"F": "FEMALE", "M": "MALE"}.get(str(claim.get("gender", "")).strip().upper()[:1])
    age = _age_on(_parse_date(claim.get("dob")), _parse_date(claim.get("visit_date")))
    problems = []
    for idx, item, info in _catalogued_items(claim):
        if info.gender in ("FEMALE", "MALE") and gender and gender != info.gender:
            problems.append(f"{info.code} ({info.description}) is for {info.gender.lower()} patients only")
        if age is not None and info.min_age is not None and age < info.min_age:
            problems.append(f"{info.code} ({info.description}) needs age {info.min_age}+, patient is {age}")
        if age is not None and info.max_age is not None and age > info.max_age:
            problems.append(f"{info.code} ({info.description}) is for ages up to {info.max_age}, patient is {age}")
    if not problems:
        return None
    return Finding(
        "; ".join(problems),
        "SHA limits some interventions by sex and age. Check the patient details or the intervention code.",
        fields=["gender", "dob", "items"],
    )


def check_facility_level(claim: dict) -> Optional[Finding]:
    level = str(claim.get("facility_level") or "").strip()
    if not level:
        return None  # unknown level: nothing to check against
    wrong = [
        f"{info.code} ({info.description}) is billable at levels {', '.join(info.levels)}"
        for _, _, info in _catalogued_items(claim)
        if not info.allowed_at_level(level)
    ]
    if not wrong:
        return None
    return Finding(
        f"Not billable at a level {level} facility: {'; '.join(wrong)}",
        "SHA pays each intervention only at certain facility levels. Use the intervention for this level, "
        "or correct the facility level.",
        fields=["items", "facility_level"],
    )


def check_diagnosis_match(claim: dict) -> Optional[Finding]:
    code = str(claim.get("diagnosis_code", "")).strip()
    if not code or icd11.format_error(code):
        return None  # reported by the diagnosis rules
    unmatched = [
        f"{info.code} ({info.description})"
        for _, _, info in _catalogued_items(claim)
        if info.diagnosis_matches(code) is False
    ]
    if not unmatched:
        return None
    return Finding(
        f"Diagnosis {code} is not on SHA's list of diagnoses for: {'; '.join(unmatched)}",
        "SHA links each intervention to the ICD-11 diagnoses it covers. Check the diagnosis is the one "
        "that justifies the service. (SHA's lists have some typos, so this is a warning.)",
        fields=["diagnosis_code", "items"],
    )


def check_access_point(claim: dict) -> Optional[Finding]:
    from fhir.kenya_bundle_builder import claim_subtype  # avoid a circular import

    setting = "IP" if claim_subtype(claim) == "inpatient" else "OP"
    wrong = [
        f"{info.code} ({info.description}) is {'inpatient' if info.access_point == 'IP' else 'outpatient'} only"
        for _, _, info in _catalogued_items(claim)
        if info.access_point in ("IP", "OP") and info.access_point != setting
    ]
    if not wrong:
        return None
    return Finding(
        f"This is an {'inpatient' if setting == 'IP' else 'outpatient'} claim but {'; '.join(wrong)}",
        "Check the claim period (admission and discharge dates) or use the intervention for this setting.",
        fields=["items", "billable_start", "billable_end"],
    )


def check_capitation_payment(claim: dict) -> Optional[Finding]:
    if str(claim.get("fund", "")).strip().upper() == "PHC":
        return None  # PHC_ZERO_TOTAL covers capitated claims
    priced = [
        f"{info.code} ({info.description})"
        for _, item, info in _catalogued_items(claim)
        if info.payment_mechanism == "CAPITATION" and item_net(item) > 0
    ]
    if not priced:
        return None
    return Finding(
        f"SHA pays these by capitation, not per claim: {'; '.join(priced)}",
        "Capitated primary care is claimed on the PHC fund with a zero price. Change the fund to PHC "
        "and set the price to 0, or use a fee-for-service intervention.",
        fields=["fund", "items"],
    )


def check_coverage_active(claim: dict) -> Optional[Finding]:
    end_date = _parse_date(claim.get("coverage_end_date"))
    visit_date = _parse_date(claim.get("visit_date"))
    if not end_date or not visit_date or visit_date <= end_date:
        return None
    return Finding(
        f"Coverage expired {(visit_date - end_date).days} day(s) before the visit date "
        f"(expired {claim.get('coverage_end_date')})",
        "Confirm the patient renewed their SHA cover before the visit. Check the SHA portal.",
    )


def check_fhir_bundle(claim: dict) -> Optional[Finding]:
    # Imported here: the bundle builder uses helpers from this module.
    from fhir.bundle_checks import COVERED_BY_CLAIM_RULES, check_bundle
    from fhir.kenya_bundle_builder import build_kenya_eclaims_bundle

    issues = [
        i for i in check_bundle(build_kenya_eclaims_bundle(claim))
        if i.check_id not in COVERED_BY_CLAIM_RULES
    ]
    if not issues:
        return None
    fields = sorted({f for i in issues for f in i.fields})
    if "practitioner_id" in fields:
        fields.append("practitioner_name")
    return Finding(
        "; ".join(i.message for i in issues),
        "SHA rejects claim bundles whose parts do not link up. For a missing practitioner, enter the "
        "treating practitioner's registry number (PUID) and name.",
        fields=fields or None,
    )


def check_amount_reasonable(claim: dict) -> Optional[Finding]:
    claimed = _to_float(claim.get("claimed_amount"))
    maternity = _is_maternity(claim)
    threshold = 150_000 if maternity else 50_000
    if claimed <= threshold:
        return None
    return Finding(
        f"Claimed KES {claimed:,.0f} exceeds the {'maternity' if maternity else 'standard'} "
        f"review threshold of KES {threshold:,.0f}",
        "Attach supporting documentation. SHA may flag this for manual review.",
    )


def check_partograph(claim: dict) -> Optional[Finding]:
    if not _is_maternity(claim) or str(claim.get("partograph_id", "")).strip():
        return None
    return Finding(
        "Maternity claim has no linked partograph reference",
        "Attach the partograph record ID before submitting. Required under facility SOP for maternity claims.",
    )


def check_renal_frequency(claim: dict) -> Optional[Finding]:
    if str(claim.get("department", "")).strip().lower() != "renal":
        return None
    sessions = claim.get("sessions_this_week")
    if sessions is None or _to_float(sessions) <= 3:
        return None
    return Finding(
        f"{sessions} dialysis sessions this week exceeds the typical 3x/week pattern",
        "Add a clinical note explaining the increased frequency, or correct the session count.",
    )


def check_postop_notes(claim: dict) -> Optional[Finding]:
    if str(claim.get("department", "")).strip().lower() != "surgical" or not claim.get("overnight_stay"):
        return None
    if str(claim.get("postop_notes_attached", "")).strip():
        return None
    return Finding(
        "This procedure included an overnight stay but has no post-op notes attached",
        "Attach the discharge summary before submission.",
    )


# ---------------------------------------------------------------------------
# Registry, in display order: errors first.
# ---------------------------------------------------------------------------

_LOCAL = "Hakiki local check"
_SOP = "Facility SOP (local)"

REGISTRY: list[Rule] = [
    Rule("MISSING_FIELDS", "2", "error", ("patient_id", "facility_code", "visit_date", "diagnosis_code"),
         AFYALINK, "AfyaLink: patient, facility and diagnosis are required", check_required_fields),
    Rule("INVALID_ICD11", "1", "error", ("diagnosis_code",),
         AFYALINK, "AfyaLink: ICD-11 is required on all claims", check_icd11),
    Rule("VISIT_DATE", "1", "error", ("visit_date",), None, _LOCAL, check_visit_date),
    Rule("EMPTY_ITEMS", "2", "error", ("items",),
         AFYALINK, "AfyaLink: items need a SHA intervention code", check_items_present),
    Rule("SHA_SERVICE_CODE_FORMAT", "1", "error", ("items",),
         OCL_INTERVENTIONS, "MOH OCL: SHA intervention catalogue", check_service_code_format),
    Rule("SERVICED_PERIOD_PRESENT", "1", "error", ("items",),
         AFYALINK, "AfyaLink: each item needs servicedPeriod start and end", check_serviced_period_present),
    Rule("SERVICED_PERIOD_IN_BILLABLE", "1", "error", ("items",),
         AFYALINK, "AfyaLink: item dates within the billablePeriod", check_serviced_period_in_billable),
    Rule("ITEM_SEQUENCE_VALID", "1", "error", ("items",),
         AFYALINK, "AfyaLink: unique item sequence numbers", check_item_sequence),
    Rule("TOTAL_EQUALS_NET_SUM", "1", "error", ("claimed_amount",),
         AFYALINK, "AfyaLink: claim total equals the sum of item net", check_total_equals_net),
    Rule("PHC_ZERO_TOTAL", "1", "error", ("claimed_amount",),
         AFYALINK, "AfyaLink: PHC claims have a zero total", check_phc_zero_total),
    Rule("FHIR_BUNDLE_VALID", "1", "error", ("practitioner_id", "practitioner_name"),
         AFYALINK, "AfyaLink: bundle references resolve; care team names a Practitioner", check_fhir_bundle),
    Rule("INTERVENTION_ELIGIBILITY", "1", "error", ("items",),
         OCL_INTERVENTIONS, "MOH OCL: intervention sex and age limits", check_intervention_eligibility),
    Rule("INTERVENTION_FACILITY_LEVEL", "1", "error", ("items", "facility_level"),
         OCL_INTERVENTIONS, "MOH OCL: facility levels per intervention", check_facility_level),
    Rule("COVERAGE_EXPIRED", "1", "error", ("coverage_end_date",), None, _LOCAL, check_coverage_active),
    Rule("MISSING_PARTOGRAPH", "1", "error", ("partograph_id",), None, _SOP, check_partograph),
    Rule("MISSING_POSTOP_NOTES", "1", "error", ("postop_notes_attached",), None, _SOP, check_postop_notes),
    Rule("ITEM_QUANTITY_VALID", "1", "warning", ("items",), None, _LOCAL, check_quantity),
    Rule("INTERVENTION_KNOWN", "1", "warning", ("items",),
         OCL_INTERVENTIONS, "MOH OCL: active SHA intervention codes", check_intervention_known),
    Rule("INTERVENTION_DIAGNOSIS_MATCH", "1", "warning", ("diagnosis_code", "items"),
         OCL_INTERVENTIONS, "MOH OCL: diagnoses linked to each intervention", check_diagnosis_match),
    Rule("INTERVENTION_ACCESS_POINT", "1", "warning", ("items",),
         OCL_INTERVENTIONS, "MOH OCL: outpatient / inpatient interventions", check_access_point),
    Rule("CAPITATION_PAYMENT", "1", "warning", ("fund", "items"),
         OCL_INTERVENTIONS, "MOH OCL: payment mechanism per intervention", check_capitation_payment),
    Rule("PREAUTH_REQUIRED", "2", "warning", ("preauth_ref",),
         OCL_INTERVENTIONS, "MOH OCL: pre-authorization flags per intervention", check_preauth),
    Rule("TARIFF_CEILING", "2", "warning", ("items",),
         OCL_INTERVENTIONS, "MOH OCL: intervention tariffs by facility level", check_tariff_ceiling),
    Rule("AMOUNT_HIGH", "1", "warning", ("claimed_amount",), None, _LOCAL, check_amount_reasonable),
    Rule("IMPLAUSIBLE_FREQUENCY", "1", "warning", ("sessions_this_week",), None, _SOP, check_renal_frequency),
]

RULES_BY_ID = {rule.id: rule for rule in REGISTRY}
# Bump when any rule changes; returned with every validation result.
RULESET_VERSION = "2026.09-v4"
