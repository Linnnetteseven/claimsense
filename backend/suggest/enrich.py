"""
Attach "Apply fix" suggestions to failed rules that the rules themselves cannot compute.

  plan()  decides which failed rules get a suggestion and builds a validated shortlist:
          - EMPTY_ITEMS, SHA_SERVICE_CODE_FORMAT, INTERVENTION_KNOWN: SHA intervention
            codes that fit the claim (suggest/interventions.py)
          - INVALID_ICD11 when no WHO map entry exists: ICD-11 codes whose WHO title
            matches the diagnosis description
  apply() turns the chosen code (Gemini's pick, else a clear deterministic best match)
          into suggested_changes on the rule result.

Suggestions only fill fields; the claim is re-validated by the deterministic rules after
the officer applies one, so a bad suggestion can never raise a score on its own.
"""

from dataclasses import dataclass, field
from typing import Optional

from suggest.interventions import item_from, shortlist
from terminology import icd11
from validation.rules import _BILLABLE_CODE
from data.sha_tariffs import get_intervention

INTERVENTION_RULES = ("EMPTY_ITEMS", "SHA_SERVICE_CODE_FORMAT", "INTERVENTION_KNOWN")
# Rules where a valid code exists but does not fit this claim: offer a replacement.
REPLACEMENT_RULES = (
    "INTERVENTION_FACILITY_LEVEL",
    "INTERVENTION_ACCESS_POINT",
    "INTERVENTION_ELIGIBILITY",
    "INTERVENTION_DIAGNOSIS_MATCH",
)


@dataclass
class Target:
    rule_id: str
    kind: str                             # "intervention" | "icd11"
    candidates: list = field(default_factory=list)   # (code, prompt label) pairs
    item_index: Optional[int] = None      # 0-based item to fix; None = add a first item
    default: Optional[str] = None         # deterministic pick when Gemini gives none
    note: Optional[str] = None            # guidance when there is nothing valid to suggest
    ready: Optional[dict] = None          # identity suggestions, computed without Gemini
    hint: Optional[str] = None            # what Hakiki offers, for the prompt (no identifiers)
    _objects: dict = field(default_factory=dict)


def _bad_item(claim: dict, rule_id: str) -> Optional[int]:
    if rule_id in REPLACEMENT_RULES:
        from validation.rules import RULES_BY_ID, run_rule

        for i, item in enumerate(claim.get("items") or []):
            if not run_rule(RULES_BY_ID[rule_id], {**claim, "items": [item]}).passed:
                return i
        return None
    for i, item in enumerate(claim.get("items") or []):
        code = str(item.get("service_code", "")).strip().upper()
        if rule_id == "EMPTY_ITEMS" and not code:
            return i
        if rule_id == "SHA_SERVICE_CODE_FORMAT" and code and not _BILLABLE_CODE.match(code):
            return i
        if rule_id == "INTERVENTION_KNOWN" and _BILLABLE_CODE.match(code) and not get_intervention(code):
            return i
    return None


def plan(result: dict, claim: dict, lookups=None) -> dict[str, Target]:
    targets: dict[str, Target] = {}
    failed = {r["rule_id"]: r for r in result["results"] if not r["passed"]}

    if lookups is not None:
        from suggest.identity import patient_suggestion, practitioner_suggestion, prompt_hint

        missing = failed.get("MISSING_FIELDS")
        if missing and "patient_id" in missing.get("fields", []):
            update = patient_suggestion(claim, lookups)
            targets["MISSING_FIELDS"] = Target("MISSING_FIELDS", "identity", ready=update, hint=prompt_hint(update))
        bundle = failed.get("FHIR_BUNDLE_VALID")
        if bundle and "practitioner_id" in bundle.get("fields", []):
            update = practitioner_suggestion(claim, lookups)
            targets["FHIR_BUNDLE_VALID"] = Target("FHIR_BUNDLE_VALID", "identity", ready=update, hint=prompt_hint(update))

    for rule_id in INTERVENTION_RULES + REPLACEMENT_RULES:
        if rule_id not in failed or failed[rule_id].get("suggested_changes"):
            continue
        index = _bad_item(claim, rule_id)
        if index is None and claim.get("items"):
            continue
        item = (claim.get("items") or [])[index] if index is not None else None
        cands = shortlist(claim, item)
        target = Target(rule_id, "intervention", item_index=index)
        target.candidates = [(c.info.code, c.as_prompt_line()) for c in cands]
        target._objects = {c.info.code: c for c in cands}
        # A clear best match (diagnosis link or wording) is safe to offer without AI.
        if cands and cands[0].score >= 2 and (len(cands) == 1 or cands[0].score > cands[1].score):
            target.default = cands[0].info.code
        if not cands:
            target.note = (
                "No SHA intervention fits this claim as entered (facility level, inpatient/outpatient "
                "setting, fund and patient). Check the facility level and fund: outpatient primary care "
                "at levels 2-4 is claimed on the PHC fund."
            )
        targets[rule_id] = target

    # PHC and capitation: two valid ways out, the officer knows which is true.
    for rule_id in ("PHC_ZERO_TOTAL", "CAPITATION_PAYMENT"):
        if rule_id in failed:
            zeroed = [{**i, "unit_price": 0, **({"net": 0} if "net" in i else {})} for i in claim.get("items") or []]
            choices = [{"label": "It is a PHC claim: set the fund to PHC and all prices to 0",
                        "changes": {"fund": "PHC", "items": zeroed, "claimed_amount": 0}}]
            if rule_id == "PHC_ZERO_TOTAL":
                choices.append({"label": "It is not a PHC claim: set the fund to SHIF",
                                "changes": {"fund": "SHIF"}})
            update = {"suggested_choices": choices, "suggestion_source": "SHA payment rules"}
            targets[rule_id] = Target(rule_id, "identity", ready=update,
                                      hint="Hakiki shows a short list to choose from; tell the officer to pick the correct one.")

    icd = failed.get("INVALID_ICD11")
    if icd and not icd.get("suggested_changes") and claim.get("diagnosis_description"):
        cands = icd11.search(claim["diagnosis_description"])
        if cands:
            targets["INVALID_ICD11"] = Target(
                "INVALID_ICD11", "icd11", candidates=[(c, f"{c}: {t}") for c, t in cands]
            )
    return targets


def _intervention_changes(target: Target, code: str, claim: dict) -> dict:
    candidate = target._objects[code]
    items = [dict(i) for i in claim.get("items") or []]
    if target.item_index is None:
        items = [item_from(candidate, claim, 1)]
    else:
        items[target.item_index] = item_from(candidate, claim, target.item_index + 1, items[target.item_index])
    return {"items": items}


def apply(result: dict, claim: dict, targets: dict[str, Target], picks: dict[str, dict]) -> None:
    """Write suggestions into result["results"] (and the errors/warnings copies)."""
    by_rule = {}
    for section in ("results", "errors", "warnings"):
        for r in result.get(section, []):
            by_rule.setdefault(r["rule_id"], []).append(r)

    for rule_id, target in targets.items():
        if target.kind == "identity":
            for r in by_rule.get(rule_id, []):
                r.update(target.ready or {})
            continue
        pick = picks.get(rule_id) or {}
        valid = {code for code, _ in target.candidates}
        code = pick.get("code") if pick.get("code") in valid else None
        source = "Gemini, from a validated shortlist" if code else None
        if not code and target.default:
            code, source = target.default, "SHA catalogue best match"
        update: dict = {}
        if code and target.kind == "intervention":
            info = target._objects[code].info
            where = f"item {target.item_index + 1}" if target.item_index is not None else "a first item"
            update = {
                "suggested_changes": _intervention_changes(target, code, claim),
                "suggested_label": f"use {code} ({info.description}) for {where}",
                "suggestion_source": source,
            }
        elif code and target.kind == "icd11":
            update = {
                "suggested_changes": {"diagnosis_code": code, "diagnosis_description": icd11.title(code) or ""},
                "suggested_label": f"use ICD-11 {code}: {icd11.title(code)}",
                "suggestion_source": source,
            }
        if pick.get("reason") and update:
            update["suggestion_reason"] = pick["reason"]
        if target.note and not update:
            update = {"suggestion_note": target.note}
        for r in by_rule.get(rule_id, []):
            r.update(update)


def candidate_block(targets: dict[str, Target]) -> str:
    """Prompt lines listing the allowed choices per rule."""
    lines = []
    for rule_id, t in targets.items():
        if t.hint:
            lines.append(f"Help for {rule_id}: {t.hint}")
        if not t.candidates:
            continue
        what = "an SHA intervention code" if t.kind == "intervention" else "an ICD-11 code"
        lines.append(f"Choices for {rule_id} ({what}; pick one exactly as written, or none if none fits):")
        lines += [f"  - {label}" for _, label in t.candidates]
    return "\n".join(lines)


def cache_suffix(target: Optional[Target]) -> str:
    if not target:
        return ""
    return "|" + ",".join(code for code, _ in target.candidates) + "|" + (target.hint or "")


