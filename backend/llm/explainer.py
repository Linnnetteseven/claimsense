"""
Plain-language explanations of failed rules, from Gemini.

Gemini only explains; the score comes from the deterministic rules and never changes here.

- Model: GEMINI_MODEL, with one retry on GEMINI_FALLBACK_MODEL; GEMINI_TIMEOUT_SECONDS per call (API minimum 10 s).
- Structured output: a Pydantic schema passed as response_schema; read response.parsed.
- Privacy: the prompt carries rule results and non-identifying clinical context only. No
  patient name, patient or practitioner IDs, dates of birth or claim IDs (Kenya Data
  Protection Act 2019, Digital Health Act 2023).
- Cache: explanations are cached by (rule_id, message), see llm/cache.py.
- Fallback: on any failure the rule's own advice text is returned with ai_used False.
"""

import logging
from typing import Optional

from google import genai
from google.genai import types
from pydantic import BaseModel

from config import config
from llm import cache
from llm.sops import get_department_context

logger = logging.getLogger(__name__)

_client = None


class Explanation(BaseModel):
    rule_id: str
    plain_explanation: str
    fix_steps: list[str]


def _get_client():
    """Initialise the Gemini client on first use, not at import (serverless cold starts)."""
    global _client
    if _client is None:
        if not config.GEMINI_API_KEY:
            logger.warning("GEMINI_API_KEY not set; using rule advice text")
            return None
        try:
            _client = genai.Client(
                api_key=config.GEMINI_API_KEY,
                http_options=types.HttpOptions(timeout=int(config.GEMINI_TIMEOUT_SECONDS * 1000)),
            )
        except Exception as exc:
            logger.error("Failed to initialise Gemini client: %s", exc)
            return None
    return _client


def claim_context(claim: dict) -> str:
    """Non-identifying context for the prompt. Never add names, IDs or dates of birth here."""
    items = ", ".join(
        f"{i.get('service_code') or 'no code'} ({i.get('description') or 'no description'})"
        for i in claim.get("items") or []
    )
    lines = [
        f"Diagnosis: {claim.get('diagnosis_code', '')} {claim.get('diagnosis_description', '')}".strip(),
        f"Department: {claim.get('department') or 'unknown'}",
        f"Fund: {claim.get('fund') or 'unknown'}; facility level: {claim.get('facility_level') or 'unknown'}",
        f"Items: {items or 'none'}",
        get_department_context(claim.get("department")),
    ]
    return "\n".join(line for line in lines if line)


def build_prompt(errors: list[dict], claim: dict) -> str:
    failures = "\n".join(
        f'- rule_id="{e["rule_id"]}" | problem="{e["message"]}" | rule advice="{e["suggestion"]}"'
        for e in errors
    )
    return f"""You help hospital claims officers in Kenya fix claims before they go to the Social Health Authority (SHA).

For each failed check below, explain in plain language a non-technical clerk can act on:
- plain_explanation: 1-2 sentences on what is wrong and why SHA cares.
- fix_steps: 1-3 short, concrete steps.
Only use the facts given. Do not invent rules, limits, codes or amounts. No FHIR or coding jargon.

Claim context (no patient details are shared):
{claim_context(claim)}

Failed checks:
{failures}

Return one entry per rule_id."""


def _fallback(error: dict) -> dict:
    return {"text": error["suggestion"], "fix_steps": []}


def _ask_gemini(client, errors: list[dict], claim: dict) -> Optional[dict[str, Explanation]]:
    prompt = build_prompt(errors, claim)
    config_ = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=list[Explanation],
        temperature=0.2,
    )
    for model in dict.fromkeys([config.GEMINI_MODEL, config.GEMINI_FALLBACK_MODEL]):  # one retry
        if not model:
            continue
        try:
            response = client.models.generate_content(model=model, contents=prompt, config=config_)
            parsed = response.parsed or []
            return {e.rule_id: e for e in parsed if isinstance(e, Explanation)}
        except Exception as exc:
            logger.warning("Gemini %s failed: %s", model, str(exc)[:200])
    return None


def explain_errors(errors: list[dict], claim: dict) -> tuple[dict[str, dict], bool]:
    """
    Returns ({rule_id: {"text": str, "fix_steps": [str]}}, ai_used).
    ai_used is True only if every explanation came from Gemini (now or from the cache).
    """
    if not errors:
        return {}, False

    explanations: dict[str, dict] = {}
    missing = []
    for error in errors:
        hit = cache.get(cache.key_for(error["rule_id"], error["message"]))
        if hit:
            explanations[error["rule_id"]] = hit
        else:
            missing.append(error)

    ai_used = True
    if missing:
        client = _get_client()
        answers = _ask_gemini(client, missing, claim) if client else None
        for error in missing:
            answer = (answers or {}).get(error["rule_id"])
            if answer:
                value = {"text": answer.plain_explanation, "fix_steps": answer.fix_steps}
                cache.put(cache.key_for(error["rule_id"], error["message"]), value)
                explanations[error["rule_id"]] = value
            else:
                explanations[error["rule_id"]] = _fallback(error)
                ai_used = False
        if answers:
            logger.info("Gemini explained %d of %d failed check(s)", len(answers), len(missing))
    return explanations, ai_used
