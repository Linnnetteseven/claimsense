"""Gemini explainer with the client mocked: structured output, retry, fallback, cache, privacy."""

import pytest

from llm import cache
from llm import explainer
from llm.explainer import Explanation, build_prompt, explain_errors
from tests.test_validation import _base_claim

ERRORS = [
    {"rule_id": "VISIT_DATE", "message": "Visit date is 5 day(s) in the future", "suggestion": "Correct the date."},
    {"rule_id": "INVALID_ICD11", "message": '"J18.9" looks like an ICD-10 code', "suggestion": "Use ICD-11."},
]


class _Response:
    def __init__(self, parsed):
        self.parsed = parsed


class FakeModels:
    def __init__(self, behaviour):
        self.behaviour, self.calls = behaviour, []

    def generate_content(self, model, contents, config):
        self.calls.append(model)
        outcome = self.behaviour(model, contents)
        if isinstance(outcome, Exception):
            raise outcome
        return _Response(outcome)


class FakeClient:
    def __init__(self, behaviour):
        self.models = FakeModels(behaviour)


def _answers(errors):
    return [Explanation(rule_id=e["rule_id"], plain_explanation=f"AI: {e['rule_id']}", fix_steps=["Do X"]) for e in errors]


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.delenv("UPSTASH_REDIS_REST_URL", raising=False)
    monkeypatch.delenv("UPSTASH_REDIS_REST_TOKEN", raising=False)
    monkeypatch.setattr(cache, "_memory", {})
    monkeypatch.setattr(explainer.config, "GEMINI_MODEL", "primary")
    monkeypatch.setattr(explainer.config, "GEMINI_FALLBACK_MODEL", "fallback")


def _use(monkeypatch, behaviour):
    client = FakeClient(behaviour)
    monkeypatch.setattr(explainer, "_get_client", lambda: client)
    return client


def test_no_errors():
    assert explain_errors([], _base_claim()) == ({}, False)


def test_structured_answers(monkeypatch):
    _use(monkeypatch, lambda model, prompt: _answers(ERRORS))
    out, ai_used = explain_errors(ERRORS, _base_claim())
    assert ai_used is True
    assert out["VISIT_DATE"] == {"text": "AI: VISIT_DATE", "fix_steps": ["Do X"]}


def test_retries_on_fallback_model(monkeypatch):
    client = _use(monkeypatch, lambda model, prompt: RuntimeError("503") if model == "primary" else _answers(ERRORS))
    out, ai_used = explain_errors(ERRORS, _base_claim())
    assert ai_used is True and client.models.calls == ["primary", "fallback"]


def test_both_models_fail_uses_rule_text(monkeypatch):
    _use(monkeypatch, lambda model, prompt: RuntimeError("503"))
    out, ai_used = explain_errors(ERRORS, _base_claim())
    assert ai_used is False
    assert out["VISIT_DATE"] == {"text": "Correct the date.", "fix_steps": []}


def test_missing_answer_falls_back_for_that_rule(monkeypatch):
    _use(monkeypatch, lambda model, prompt: _answers(ERRORS[:1]))
    out, ai_used = explain_errors(ERRORS, _base_claim())
    assert ai_used is False
    assert out["VISIT_DATE"]["text"] == "AI: VISIT_DATE" and out["INVALID_ICD11"]["text"] == "Use ICD-11."


def test_no_api_key(monkeypatch):
    monkeypatch.setattr(explainer, "_get_client", lambda: None)
    out, ai_used = explain_errors(ERRORS, _base_claim())
    assert ai_used is False and out["INVALID_ICD11"]["text"] == "Use ICD-11."


def test_cache_skips_gemini_on_repeat(monkeypatch):
    client = _use(monkeypatch, lambda model, prompt: _answers(ERRORS))
    explain_errors(ERRORS, _base_claim())
    out, ai_used = explain_errors(ERRORS, _base_claim(patient_name="Someone Else"))
    assert ai_used is True and client.models.calls == ["primary"]
    assert out["INVALID_ICD11"]["text"] == "AI: INVALID_ICD11"


def test_fallback_text_is_not_cached(monkeypatch):
    _use(monkeypatch, lambda model, prompt: RuntimeError("503"))
    explain_errors(ERRORS, _base_claim())
    assert cache._memory == {}


def test_prompt_has_no_patient_identifiers():
    claim = _base_claim(
        id="SHA-CLM-SECRET-9", patient_name="Grace Wanjiru Njoroge", patient_id="INS-KE-44218",
        dob="1989-03-14", practitioner_id="PUID-0034512-1", practitioner_name="Dr. Wairimu Kinyua",
    )
    prompt = build_prompt(ERRORS, claim)
    for secret in ("SHA-CLM-SECRET-9", "Grace", "Njoroge", "INS-KE-44218", "1989-03-14", "PUID-0034512-1", "Wairimu"):
        assert secret not in prompt
    assert "NC72.5" in prompt and "VISIT_DATE" in prompt
