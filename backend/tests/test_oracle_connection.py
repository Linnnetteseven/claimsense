from pathlib import Path
import asyncio
import sys
from types import SimpleNamespace

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from db import connection
from db.oracle_impl import _load_json
import main


def _configure(monkeypatch, tmp_path, wallet_dir=""):
    options = {}
    monkeypatch.setattr(connection, "_pool", None)
    monkeypatch.setitem(
        sys.modules,
        "oracledb",
        SimpleNamespace(create_pool=lambda **kwargs: options.update(kwargs) or object()),
    )
    monkeypatch.setenv("ORACLE_USER", "HAKIKI_APP")
    monkeypatch.setenv("ORACLE_PASSWORD", "test-password")
    monkeypatch.setenv("ORACLE_DSN", "(description=(address=(protocol=tcps)))")
    monkeypatch.setenv("ORACLE_WALLET_DIR", wallet_dir)
    monkeypatch.setenv("ORACLE_WALLET_PASSWORD", "test-wallet-password")
    return options


def test_walletless_tls_pool_omits_wallet_options(monkeypatch, tmp_path):
    options = _configure(monkeypatch, tmp_path)

    connection.get_pool()

    assert connection.connection_mode() == "walletless_tls"
    assert options["dsn"] == "(description=(address=(protocol=tcps)))"
    assert not {"config_dir", "wallet_location", "wallet_password"} & options.keys()


def test_wallet_mtls_pool_passes_wallet_options(monkeypatch, tmp_path):
    wallet_dir = tmp_path / "wallet"
    wallet_dir.mkdir()
    options = _configure(monkeypatch, tmp_path, str(wallet_dir))

    connection.get_pool()

    assert connection.connection_mode() == "wallet_mtls"
    assert options["config_dir"] == str(wallet_dir.resolve())
    assert options["wallet_location"] == str(wallet_dir.resolve())
    assert options["wallet_password"] == "test-wallet-password"


def test_db_health_reports_active_connection_mode(monkeypatch):
    class HealthyOracle:
        backend_name = "oracle"

        @staticmethod
        def health():
            return True

    monkeypatch.setattr(main, "get_repository", lambda: HealthyOracle())
    monkeypatch.setattr(main, "configured_backend", lambda: "oracle")
    monkeypatch.setattr(main, "oracle_connection_mode", lambda: "walletless_tls")

    response = asyncio.run(main.database_health())

    assert response["active_backend"] == "oracle"
    assert response["connection_mode"] == "walletless_tls"
    assert response["connected"] is True


def test_oracle_json_values_accept_text_and_lob_values():
    class FakeLob:
        @staticmethod
        def read():
            return '{"synthetic": true}'

    assert _load_json('{"synthetic": true}') == {"synthetic": True}
    assert _load_json(FakeLob()) == {"synthetic": True}
