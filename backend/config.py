import os
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))


class _Config:
    DB_BACKEND: str = os.getenv("DB_BACKEND", "redis").strip().lower() or "redis"
    OPENIMIS_URL: str = os.getenv("OPENIMIS_URL", "https://localhost")
    OPENIMIS_TOKEN: str = os.getenv("OPENIMIS_TOKEN", "")
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    DEBUG: bool = os.getenv("DEBUG", "true").lower() == "true"
    OPENIMIS_VERIFY_TLS: bool = os.getenv("OPENIMIS_VERIFY_TLS", "true").lower() != "false"
    ENABLE_SMS: bool = os.getenv("ENABLE_SMS", "false").lower() == "true"
    USSD_SHARED_SECRET: str = os.getenv("USSD_SHARED_SECRET", "")
    ALLOWED_ORIGINS: list[str] = [
        origin.strip().rstrip("/")
        for origin in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")
        if origin.strip()
    ]
    DEPLOYED_FRONTEND_URL: str = os.getenv("DEPLOYED_FRONTEND_URL", "").strip().rstrip("/")
    AVAX_RPC_URL: str = os.getenv("AVAX_RPC_URL", "https://api.avax-test.network/ext/bc/C/rpc")
    ANCHOR_CONTRACT_ADDRESS: str = os.getenv("ANCHOR_CONTRACT_ADDRESS", "")
    ANCHOR_PRIVATE_KEY: str = os.getenv("ANCHOR_PRIVATE_KEY", "")
    ANCHOR_API_SECRET: str = os.getenv("ANCHOR_API_SECRET", "")
    CHAIN_ID: int = int(os.getenv("CHAIN_ID", "43113"))
    ENABLE_SELECT_AI: bool = os.getenv("ENABLE_SELECT_AI", "false").strip().lower() == "true"

    @property
    def use_mock(self) -> bool:
        return not bool(self.OPENIMIS_TOKEN)

    @property
    def llm_enabled(self) -> bool:
        return bool(self.GEMINI_API_KEY)


config = _Config()
