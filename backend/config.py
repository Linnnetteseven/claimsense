import os
from dotenv import load_dotenv


# Load .env from the backend directory
load_dotenv(
    dotenv_path=os.path.join(os.path.dirname(__file__), ".env")
)


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


class _Config:
    # ---------------------------------------------------------
    # Legacy / openIMIS
    # ---------------------------------------------------------
    OPENIMIS_URL: str = os.getenv(
        "OPENIMIS_URL",
        "https://localhost",
    )

    OPENIMIS_TOKEN: str = os.getenv(
        "OPENIMIS_TOKEN",
        "",
    )

    # ---------------------------------------------------------
    # Gemini
    # ---------------------------------------------------------
    GEMINI_API_KEY: str = os.getenv(
        "GEMINI_API_KEY",
        "",
    )

    # ---------------------------------------------------------
    # Supabase
    # ---------------------------------------------------------
    SUPABASE_URL: str = os.getenv(
        "SUPABASE_URL",
        "",
    )

    SUPABASE_SERVICE_ROLE_KEY: str = os.getenv(
        "SUPABASE_SERVICE_ROLE_KEY",
        "",
    )

    # ---------------------------------------------------------
    # Application
    # ---------------------------------------------------------
    DEBUG: bool = _env_bool(
        "DEBUG",
        default=True,
    )

    # ---------------------------------------------------------
    # SHA Kenya FHIR
    # ---------------------------------------------------------
    SHA_FHIR_URL: str = os.getenv(
        "SHA_FHIR_URL",
        "https://nshr-uat.sha.go.ke/fhir",
    ).rstrip("/")

    SHA_FHIR_TOKEN: str = os.getenv(
        "SHA_FHIR_TOKEN",
        "",
    )

    SHA_FHIR_VERIFY_SSL: bool = _env_bool(
        "SHA_FHIR_VERIFY_SSL",
        default=True,
    )

    SHA_FHIR_TIMEOUT: float = float(
        os.getenv(
            "SHA_FHIR_TIMEOUT",
            "20",
        )
    )

    # ---------------------------------------------------------
    # Demo / data source
    # ---------------------------------------------------------
    USE_SUPABASE: bool = _env_bool(
        "USE_SUPABASE",
        default=False,
    )

    # ---------------------------------------------------------
    # Derived configuration
    # ---------------------------------------------------------
    @property
    def use_mock(self) -> bool:
        return not bool(self.OPENIMIS_TOKEN)

    @property
    def llm_enabled(self) -> bool:
        return bool(self.GEMINI_API_KEY)

    @property
    def supabase_configured(self) -> bool:
        return bool(
            self.SUPABASE_URL
            and self.SUPABASE_SERVICE_ROLE_KEY
        )


config = _Config()
