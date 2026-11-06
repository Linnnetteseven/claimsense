from pathlib import Path
import sys

from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import main


def test_ui_settings_reflect_department_mode(monkeypatch):
    client = TestClient(main.app)

    monkeypatch.setattr(main.config, "DEPARTMENTS_ENABLED", True)
    assert client.get("/settings/ui").json() == {"departments_enabled": True}

    monkeypatch.setattr(main.config, "DEPARTMENTS_ENABLED", False)
    assert client.get("/settings/ui").json() == {"departments_enabled": False}
