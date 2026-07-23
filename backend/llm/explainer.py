"""
Generates plain-English error explanations using Google Gemini 2.0 Flash.

Falls back to built-in rule suggestion text if:
  - GEMINI_API_KEY is not set in .env
  - The API call fails for any reason
  - The response cannot be parsed as JSON
"""

import json
import logging
from google import genai
from config import config
from llm.sops import get_department_context

logger = logging.getLogger(__name__)

# Lazy init — not at import time, avoids cold-start env var timing issues
_client = None


def _get_client():
    """Initialize Gemini client on first call, not at module import."""
    global _client
    if _client is None:
        if not config.GEMINI_API_KEY:
            logger.warning("GEMINI_API_KEY not set — Gemini disabled, using fallback")
            return None
        try:
            _client = genai.Client(api_key=config.GEMINI_API_KEY)
            logger.info("Gemini client initialized OK")
        except Exception as exc:
            logger.error("Failed to initialize Gemini client: %s", exc)
            return None
    return _client


def explain_errors(errors: list[dict], claim: dict) -> tuple[dict[str, str], bool]:
    """
    Returns (explanations_dict, ai_was_used).
    explanations_dict maps rule_id -> plain-English explanation.
    ai_was_used = True if Gemini responded, False if using fallback.
    """
    if not errors:
        return {}, False

    client = _get_client()

    if not client:
        return {e["rule_id"]: e["suggestion"] for e in errors}, False

    error_lines = "\n".join(
        f'rule_id="{e["rule_id"]}" | issue="{e["message"]}" | hint="{e["suggestion"]}"'
        for e in errors
    )

    dept_context = get_department_context(claim.get("department"))

    context = (
        f"Claim ID: {claim.get('id', 'unknown')}\n"
        f"Patient: {claim.get('patient_name', 'Unknown')}\n"
        f"Facility: {claim.get('facility_name', 'Unknown')}\n"
        f"Diagnosis: {claim.get('diagnosis_code', '')} — "
        f"{claim.get('diagnosis_description', '')}\n"
        f"{dept_context}\n"
    )

    prompt = f"""You are ClaimSense, helping hospital claims officers at SHA Kenya fix insurance claims.

Explain each validation failure below in simple, direct language a non-technical hospital clerk can act on.
No jargon. No FHIR, ICD-10 subcode, adjudication. Write as if speaking to someone at a hospital reception desk.

Claim context:
{context}

Errors to explain:
{error_lines}

Respond ONLY with a valid JSON object. One key per rule_id, value is 2-3 sentences explaining
what went wrong, why SHA cares, and what to do.

Example:
{{
  "MISSING_FIELDS": "The patient ID is missing. SHA cannot process a claim without knowing who was treated. Ask the patient for their SHA membership card and enter the number shown on it."
}}"""

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
        )

        raw = response.text.strip()

        if raw.startswith("```"):
            parts = raw.split("```")
            raw = parts[1].lstrip("json").strip() if len(parts) >= 2 else raw

        parsed = json.loads(raw)

        for e in errors:
            if e["rule_id"] not in parsed:
                parsed[e["rule_id"]] = e["suggestion"]

        logger.info("Gemini explained %d error(s) successfully", len(errors))
        return parsed, True

    except json.JSONDecodeError as exc:
        logger.warning("Gemini response not valid JSON (%s) — using fallback", exc)
        return {e["rule_id"]: e["suggestion"] for e in errors}, False

    except Exception as exc:
        logger.error("Gemini API call failed: %s", exc)
        return {e["rule_id"]: e["suggestion"] for e in errors}, False
