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

    # Explanations only; the score never depends on Gemini. Flash-lite answered fastest
    # and most reliably in testing (Sep 2026); the fallback is tried once on failure.
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
    GEMINI_FALLBACK_MODEL: str = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-3.1-flash-lite")
    # The Gemini API rejects deadlines under 10 s.
    GEMINI_TIMEOUT_SECONDS: float = max(10.0, float(os.getenv("GEMINI_TIMEOUT_SECONDS", "10")))

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

    # Base for IG code system, identifier and profile URLs. UAT prefix from the eClaims IG.
    SHA_TERMINOLOGY_BASE: str = os.getenv(
        "SHA_TERMINOLOGY_BASE",
        "https://nshr-uat.sha.go.ke/fhir",
    ).rstrip("/")

    # Diagnosis code system name under SHA_TERMINOLOGY_BASE. The IG examples use
    # icd11-codes-cs; nshr-uat also hosts the same list as ClaimDiagnosisCodeableConceptCS.
    SHA_DIAGNOSIS_SYSTEM: str = os.getenv("SHA_DIAGNOSIS_SYSTEM", "icd11-codes-cs")

    # FHIR requires a MessageHeader in a message Bundle (bdl-12); with it, demo bundles pass
    # UAT $validate with no errors. SHA's example mediator request omits it; set false to match.
    SHA_BUNDLE_MESSAGE_HEADER: bool = _env_bool("SHA_BUNDLE_MESSAGE_HEADER", default=True)

    # AfyaLink (SHR mediator) submission. Credentials are issued to facilities.
    AFYALINK_URL: str = os.getenv("AFYALINK_URL", "https://uat.dha.go.ke").rstrip("/")
    AFYALINK_USERNAME: str = os.getenv("AFYALINK_USERNAME", "")
    AFYALINK_PASSWORD: str = os.getenv("AFYALINK_PASSWORD", "")
    AFYALINK_CONSUMER_KEY: str = os.getenv("AFYALINK_CONSUMER_KEY", "")

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

    # Optional WHO ICD API credentials for live ICD-11 code lookup (https://icd.who.int/icdapi).
    ICD_API_CLIENT_ID: str = os.getenv("ICD_API_CLIENT_ID", "")
    ICD_API_CLIENT_SECRET: str = os.getenv("ICD_API_CLIENT_SECRET", "")
    ICD_API_RELEASE: str = os.getenv("ICD_API_RELEASE", "2024-01")

    # Browsers allowed to call the API. Exact origins, plus a pattern for Vercel preview
    # builds of this team's frontend. No cookies are used, so credentials stay off.
    CORS_ORIGINS: list[str] = [
        o.strip().rstrip("/") for o in os.getenv(
            "CORS_ORIGINS",
            "https://claimsense-frontend.vercel.app,http://localhost:5173,http://127.0.0.1:5173",
        ).split(",") if o.strip()
    ]
    CORS_ORIGIN_REGEX: str = os.getenv(
        "CORS_ORIGIN_REGEX",
        r"^https://claimsense-frontend-[a-z0-9-]+-mugwanjalk-gmailcoms-projects\.vercel\.app$",
    )

    # Where officers fix claims; shown in USSD screens and SMS.
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "claimsense-frontend.vercel.app")

    # USSD access: comma-separated E.164 numbers of registered officers. Empty = open (demo).
    USSD_ALLOWED_PHONES: set[str] = {
        p.strip() for p in os.getenv("USSD_ALLOWED_PHONES", "").split(",") if p.strip()
    }

    # How validated claims reach the hospital HIS: store | webhook | openimis (see his/handoff.py).
    HIS_DELIVERY: str = os.getenv("HIS_DELIVERY", "store").strip().lower()
    HIS_WEBHOOK_URL: str = os.getenv("HIS_WEBHOOK_URL", "")
    HIS_WEBHOOK_TOKEN: str = os.getenv("HIS_WEBHOOK_TOKEN", "")

    # Allows POST /claims/{id}/reset and POST /demo/reset. Turn off outside demos.
    DEMO_RESET_ENABLED: bool = _env_bool(
        "DEMO_RESET_ENABLED",
        default=True,
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
