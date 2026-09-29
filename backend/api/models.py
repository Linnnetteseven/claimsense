"""
Request and response models.

Claims keep Hakiki's flexible internal shape (department extras vary), so the claim
models type the common fields and allow others. Responses type what clients rely on.
"""

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class Flexible(BaseModel):
    model_config = ConfigDict(extra="allow")


# --- Requests --------------------------------------------------------------

class ItemIn(Flexible):
    sequence: Optional[int] = None
    service_code: Optional[str] = None
    description: Optional[str] = None
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    service_start: Optional[str] = None
    service_end: Optional[str] = None


class ClaimIn(Flexible):
    """A claim in Hakiki's internal shape. Every field is optional; the rules report what is missing."""
    id: Optional[str] = None
    patient_id: Optional[str] = None
    patient_name: Optional[str] = None
    dob: Optional[str] = None
    gender: Optional[str] = None
    facility_code: Optional[str] = None
    facility_name: Optional[str] = None
    facility_level: Optional[str] = None
    fund: Optional[str] = None
    visit_date: Optional[str] = None
    discharge_date: Optional[str] = None
    diagnosis_code: Optional[str] = None
    diagnosis_description: Optional[str] = None
    practitioner_id: Optional[str] = None
    practitioner_name: Optional[str] = None
    preauth_ref: Optional[str] = None
    claimed_amount: Optional[float] = None
    items: Optional[list[ItemIn]] = None

    def as_claim(self) -> dict:
        """Only the fields the client sent, as a plain dict."""
        return self.model_dump(exclude_unset=True)


class HandoffRequest(BaseModel):
    acknowledge_warnings: bool = False


# --- Responses -------------------------------------------------------------

class Preview(BaseModel):
    score: int
    status: str
    color: str
    error_count: int
    warning_count: int


class ClaimList(BaseModel):
    count: int
    page: int
    page_size: int
    total_pages: int
    claims: list[dict]


class ClaimWithPreview(BaseModel):
    claim: dict
    preview: Preview = Field(serialization_alias="_preview")


class Validation(Flexible):
    """Rule results plus explanations and suggestions; extra keys (fhir_claim_response...) pass through."""
    claim_id: Optional[str] = None
    ruleset_version: str
    score: int
    status: str
    color: str
    passed: bool
    error_count: int
    warning_count: int
    results: list[dict]
    errors: list[dict]
    warnings: list[dict]
    explanations: dict[str, str] = {}
    fix_steps: dict[str, list[str]] = {}
    ai_explanations_used: bool = False


class CorrectionResult(BaseModel):
    claim: dict
    validation: Validation


class BundleIssue(BaseModel):
    check_id: str
    message: str
    fields: list[str]


class BundleResult(BaseModel):
    bundle: dict
    checks_passed: bool
    issues: list[BundleIssue]


class HandoffResult(BaseModel):
    handed_off: bool
    claim_id: str
    handoff_id: str
    created_at: str
    score: int
    ruleset_version: str
    warnings_acknowledged: list[str]
    delivery: str
    delivery_status: str
    delivery_response: Optional[Any] = None
    sha_bundle: dict


class History(BaseModel):
    claim_id: str
    validation_runs: list[Any]
    corrections: list[Any]


class ResetCounts(BaseModel):
    restored: int
    removed: int


class Check(BaseModel):
    ok: Optional[bool]  # None = not configured, so not checked
    required: bool = False
    detail: Optional[str] = None
    ms: Optional[int] = None


class Health(BaseModel):
    ok: bool
    version: str
    ruleset_version: str
    checks: dict[str, Check]


class ErrorBody(BaseModel):
    code: str
    message: str
    details: Optional[Any] = None


class ErrorResponse(BaseModel):
    error: ErrorBody
