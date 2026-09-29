// Fields shown on each tab. An error card's "Show in claim" opens the tab that holds its field.
export const PATIENT_FIELDS = [
  ["patient_name", "Full name"],
  ["patient_id", "SHA number"],
  ["dob", "Date of birth"],
  ["gender", "Sex"],
  ["fund", "Fund"],
  ["coverage_start_date", "Coverage start"],
  ["coverage_end_date", "Coverage end"],
];
export const CLAIM_FIELDS = [
  ["id", "Claim ID"],
  ["facility_name", "Facility"],
  ["facility_code", "Facility code (FID)"],
  ["facility_level", "Facility level"],
  ["department", "Department"],
  ["visit_date", "Visit / admission date"],
  ["discharge_date", "Discharge date"],
  ["billable_start", "Claim period start"],
  ["billable_end", "Claim period end"],
  ["diagnosis_code", "Diagnosis (ICD-11)"],
  ["diagnosis_description", "Diagnosis description"],
  ["practitioner_name", "Treating practitioner"],
  ["practitioner_id", "Practitioner registry number (PUID)"],
  ["preauth_ref", "Pre-authorization reference"],
  ["partograph_id", "Partograph record ID"],
  ["postop_notes_attached", "Post-op notes reference"],
  ["sessions_this_week", "Dialysis sessions this week"],
  ["claimed_amount", "Claimed amount (KES)"],
];
// Shown even when empty; the rest only when the claim has a value.
export const ALWAYS_SHOWN = new Set([
  "patient_name", "patient_id", "dob", "gender", "fund", "coverage_end_date", "id", "facility_name",
  "facility_code", "facility_level", "visit_date", "diagnosis_code", "diagnosis_description",
  "practitioner_name", "practitioner_id", "claimed_amount",
]);

export function tabForField(field) {
  return PATIENT_FIELDS.some(([f]) => f === field) ? "Demographics" : "Claim Info";
}
