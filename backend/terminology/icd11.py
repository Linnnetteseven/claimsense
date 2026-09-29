"""
ICD-11 MMS code checks.

format_error() is always available. lookup() asks the WHO ICD API whether a
code exists, only when ICD_API_CLIENT_ID / ICD_API_CLIENT_SECRET are set.
Results are cached; after a network failure lookups are skipped for a while
so validation never waits on an unreachable API.

WHO ICD API: https://icd.who.int/icdapi (OAuth2 client credentials).
"""

import logging
import re
import time
from typing import Optional

import httpx

from config import config

logger = logging.getLogger(__name__)

# ICD-11 codes never use the letters I or O (to avoid confusion with 1 and 0).
_C = "0-9A-HJ-NP-Z"
# Stem code: chapter char, letter, digit, char, optional .1-2 char extension. E.g. 1A00, CA40.Z, DB10.02
_STEM = re.compile(rf"^[1-9A-HJ-NP-WYZ][A-HJ-NP-Z][0-9][{_C}](\.[{_C}]{{1,2}})?$")
# Extension codes (chapter X), used in postcoordination. E.g. XN0Y5, XK8G
_EXTENSION = re.compile(rf"^X[{_C}]{{3,5}}$")
_ICD10 = re.compile(r"^[A-Z][0-9]{2}(\.[0-9A-Z]{1,4})?$")

_TOKEN_URL = "https://icdaccessmanagement.who.int/connect/token"
_API_BASE = "https://id.who.int/icd/release/11"
_TIMEOUT = 3.0
_CACHE_TTL = 7 * 24 * 3600
_BACKOFF_AFTER_FAILURE = 300

_cache: dict[str, tuple[float, bool]] = {}
_token: tuple[float, str] | None = None
_skip_until = 0.0


def parts(code: str) -> list[str]:
    """Split a postcoordinated cluster ("DA42.Z&XT5R" or "NC72.2/XJ4NP") into codes."""
    return [p for p in re.split(r"[&/]", code.strip().upper()) if p]


def looks_like_icd10(code: str) -> bool:
    return bool(_ICD10.match(code.strip().upper()))


def format_error(code: str) -> Optional[str]:
    """Return a reason the code is not valid ICD-11 MMS, or None if the format is fine."""
    pieces = parts(code)
    if not pieces:
        return "empty code"
    if not _STEM.match(pieces[0]):
        return f'"{pieces[0]}" is not an ICD-11 stem code'
    for piece in pieces[1:]:
        if not (_STEM.match(piece) or _EXTENSION.match(piece)):
            return f'"{piece}" is not an ICD-11 stem or extension code'
    return None


def lookup_enabled() -> bool:
    return bool(config.ICD_API_CLIENT_ID and config.ICD_API_CLIENT_SECRET)


def _get_token() -> str:
    global _token
    if _token and _token[0] > time.time():
        return _token[1]
    resp = httpx.post(
        _TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "scope": "icdapi_access",
            "client_id": config.ICD_API_CLIENT_ID,
            "client_secret": config.ICD_API_CLIENT_SECRET,
        },
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    body = resp.json()
    _token = (time.time() + int(body.get("expires_in", 3600)) - 60, body["access_token"])
    return _token[1]


def _exists(code: str) -> bool:
    resp = httpx.get(
        f"{_API_BASE}/{config.ICD_API_RELEASE}/mms/codeinfo/{code}",
        headers={
            "Authorization": f"Bearer {_get_token()}",
            "Accept": "application/json",
            "Accept-Language": "en",
            "API-Version": "v2",
        },
        timeout=_TIMEOUT,
    )
    if resp.status_code == 404:
        return False
    resp.raise_for_status()
    return True


def lookup(code: str) -> Optional[bool]:
    """
    True if every part of the code exists in ICD-11 MMS, False if a part does not,
    None if the lookup is not configured or the WHO API could not be reached.
    """
    global _skip_until
    if not lookup_enabled() or time.time() < _skip_until:
        return None
    for piece in parts(code):
        cached = _cache.get(piece)
        if cached and cached[0] > time.time():
            found = cached[1]
        else:
            try:
                found = _exists(piece)
            except Exception as exc:
                logger.warning("WHO ICD API lookup failed (%s); format-only checks for %ss", exc, _BACKOFF_AFTER_FAILURE)
                _skip_until = time.time() + _BACKOFF_AFTER_FAILURE
                return None
            _cache[piece] = (time.time() + _CACHE_TTL, found)
        if not found:
            return False
    return True


def lookup_release() -> str:
    return f"release {config.ICD_API_RELEASE}"
