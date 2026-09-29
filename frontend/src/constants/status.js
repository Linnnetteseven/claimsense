// Single source of truth for status → color → label mapping.
// Every component (StatusBadge, ScoreGauge, ClaimList, ErrorCard) reads from
// here instead of maintaining its own copy of the same three colors.

export const STATUS_COLOR = {
  green: "green",
  amber: "amber",
  red: "red",
};

export const SCORE_THRESHOLDS = {
  READY: 85,
  NEEDS_REVIEW: 60,
};

export function scoreToColor(score) {
  if (score >= SCORE_THRESHOLDS.READY) return STATUS_COLOR.green;
  if (score >= SCORE_THRESHOLDS.NEEDS_REVIEW) return STATUS_COLOR.amber;
  return STATUS_COLOR.red;
}

export function scoreToLabel(score) {
  if (score >= SCORE_THRESHOLDS.READY) return "Ready for Submission";
  if (score >= SCORE_THRESHOLDS.NEEDS_REVIEW) return "Needs Review";
  return "High Risk";
}

// Hex values for SVG stroke attributes (Tailwind classes don't apply to SVG stroke).
export const HEX_BY_COLOR = {
  green: "#10b981",
  amber: "#f59e0b",
  red: "#ef4444",
};

// Tailwind class bundles keyed by semantic color, used across badge/pill UI.
export const BADGE_CLASSES = {
  green: "bg-emerald-100 text-emerald-700 border border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-400 dark:border-emerald-900/50",
  amber: "bg-amber-100 text-amber-700 border border-amber-200 dark:bg-amber-950/40 dark:text-amber-400 dark:border-amber-900/50",
  red: "bg-red-100 text-red-700 border border-red-200 dark:bg-red-950/40 dark:text-red-400 dark:border-red-900/50",
};

export const DOT_CLASSES = {
  green: "bg-emerald-500",
  amber: "bg-amber-500",
  red: "bg-red-500",
};

export const LIST_DOT_CLASSES = {
  green: "bg-emerald-500",
  amber: "bg-amber-500",
  red: "bg-red-500",
};

export const LIST_BADGE_CLASSES = {
  green: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400",
  amber: "bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-400",
  red: "bg-red-100 text-red-700 dark:bg-red-950/40 dark:text-red-400",
};

export const SEVERITY_STYLES = {
  error: {
    border: "border-red-200 dark:border-red-900/40",
    bg: "bg-red-50 dark:bg-red-950/10",
    badge: "bg-red-100 text-red-700 dark:bg-red-950/40 dark:text-red-400",
    icon: "text-red-500 dark:text-red-400",
  },
  warning: {
    border: "border-amber-200 dark:border-amber-900/40",
    bg: "bg-amber-50 dark:bg-amber-950/10",
    badge: "bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-400",
    icon: "text-amber-500 dark:text-amber-400",
  },
};

export const PASS_STYLE = {
  border: "border-emerald-200 dark:border-emerald-900/40",
  bg: "bg-emerald-50 dark:bg-emerald-950/10",
  badge: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400",
};

// Claim fields the officer can correct inline from a failing ErrorCard.
// Rule results name these in `fields`; "items" gets its own line-item editor.
export const FIELD_INPUTS = {
  patient_id: { label: "Patient / insuree ID", type: "text" },
  facility_code: { label: "Facility code", type: "text" },
  visit_date: { label: "Visit date", type: "date" },
  diagnosis_code: { label: "Diagnosis code", type: "text" },
  coverage_end_date: { label: "Coverage end date", type: "date" },
  claimed_amount: { label: "Claimed amount (KES)", type: "number" },
  billable_start: { label: "Claim period start", type: "date" },
  billable_end: { label: "Claim period end", type: "date" },
  fund: { label: "Fund", type: "select", options: ["SHIF", "PHC", "ECCIF"] },
  preauth_ref: { label: "Pre-authorization reference", type: "text" },
  partograph_id: { label: "Partograph record ID", type: "text" },
  postop_notes_attached: { label: "Post-op notes / discharge summary reference", type: "text" },
  sessions_this_week: { label: "Dialysis sessions this week", type: "number" },
  items: { label: "Service items", type: "items" },
};

// Coerce an input's string value to what the backend stores for that field.
export function coerceFieldValue(field, value) {
  if (FIELD_INPUTS[field]?.type === "number") {
    return value === "" || value === null || value === undefined ? "" : Number(value);
  }
  return value;
}
