"""Canonical demo claims, shared with the Supabase JavaScript seed script."""

import json
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any

_FIXTURE_PATH = Path(__file__).with_name("demo_claims.json")
_DATE_TOKEN = re.compile(r"^\{\{today(?P<offset>[+-]\d+)d\}\}$")


def _resolve_dates(value: Any) -> Any:
    if isinstance(value, str):
        match = _DATE_TOKEN.match(value)
        if match:
            return str(date.today() + timedelta(days=int(match.group("offset"))))
        return value
    if isinstance(value, list):
        return [_resolve_dates(item) for item in value]
    if isinstance(value, dict):
        return {key: _resolve_dates(item) for key, item in value.items()}
    return value


def load_demo_claims() -> list[dict]:
    """Return fresh, date-resolved copies of the canonical demo dataset."""
    with _FIXTURE_PATH.open(encoding="utf-8") as fixture:
        return _resolve_dates(json.load(fixture))


# Kept for legacy callers such as USSD. API routes now use Supabase.
MOCK_CLAIMS: list[dict] = load_demo_claims()
