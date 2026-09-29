"""WHO ICD API lookup with httpx mocked; no network."""

import httpx
import pytest

from terminology import icd11


class _Resp:
    def __init__(self, status, body=None):
        self.status_code, self._body = status, body or {}

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=None, response=None)


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    monkeypatch.setattr(icd11.config, "ICD_API_CLIENT_ID", "id")
    monkeypatch.setattr(icd11.config, "ICD_API_CLIENT_SECRET", "secret")
    monkeypatch.setattr(icd11, "_cache", {})
    monkeypatch.setattr(icd11, "_token", None)
    monkeypatch.setattr(icd11, "_skip_until", 0.0)
    monkeypatch.setattr(icd11.httpx, "post", lambda *a, **k: _Resp(200, {"access_token": "t", "expires_in": 3600}))


def test_disabled_without_credentials(monkeypatch):
    monkeypatch.setattr(icd11.config, "ICD_API_CLIENT_ID", "")
    assert icd11.lookup("1A00") is None


def test_found_and_cached(monkeypatch):
    calls = []
    monkeypatch.setattr(icd11.httpx, "get", lambda url, **k: calls.append(url) or _Resp(200))
    assert icd11.lookup("1A00") is True
    assert icd11.lookup("1A00") is True
    assert len(calls) == 1 and calls[0].endswith("/mms/codeinfo/1A00")


def test_not_found(monkeypatch):
    monkeypatch.setattr(icd11.httpx, "get", lambda url, **k: _Resp(404))
    assert icd11.lookup("1A00") is False


def test_postcoordinated_checks_each_part(monkeypatch):
    monkeypatch.setattr(icd11.httpx, "get", lambda url, **k: _Resp(404 if url.endswith("XT5R") else 200))
    assert icd11.lookup("DA42.Z&XT5R") is False


def test_network_failure_backs_off(monkeypatch):
    def boom(*a, **k):
        raise httpx.ConnectError("down")
    monkeypatch.setattr(icd11.httpx, "get", boom)
    assert icd11.lookup("1A00") is None
    monkeypatch.setattr(icd11.httpx, "get", lambda url, **k: _Resp(200))
    assert icd11.lookup("1A00") is None  # still backing off
