import { DEPARTMENT_GUIDES } from "../data/departmentGuides.js";

export function getOverallStatus(validationResult, departmentReview) {
  const result = validationResult || {};
  const score = Number(result.score);
  const hasScore = Number.isFinite(score);
  const failedError = (result.results || []).some(
    (rule) => rule.passed === false && rule.severity === "error",
  ) || (result.errors || []).some((rule) => rule.severity === "error")
    || Number(result.error_count) > 0;

  if (result.status === "High Risk" || (hasScore && score < 60) || failedError) {
    return {
      status: "red",
      label: "Blocked",
      reason: failedError
        ? "One or more error-severity automated checks failed."
        : "The automated score is below 60.",
    };
  }

  if (result.status === "Needs Review" || (hasScore && score >= 60 && score <= 84)) {
    return {
      status: "amber",
      label: "Needs review",
      reason: "The automated score is in the 60–84 review band.",
    };
  }

  const isAutomatedReady = result.status === "Ready for Submission"
    || result.status === "Ready"
    || (hasScore && score >= 85);

  if (!isAutomatedReady) {
    return {
      status: "amber",
      label: "Needs review",
      reason: "Automated checks have not run yet.",
    };
  }

  const department = result.department || result.claim?.department;
  const guide = DEPARTMENT_GUIDES[(department || "").toLowerCase()];
  if (!guide) {
    return {
      status: "green",
      label: "Ready",
      reason: "No department checklist applies to this claim.",
    };
  }

  const requiredItems = guide.steps.filter((step) => step.required);
  const completedCount = requiredItems.filter((step) => departmentReview?.completed?.[step.title]).length;
  if (completedCount !== requiredItems.length) {
    return {
      status: "amber",
      label: "Awaiting department sign-off",
      reason: `${guide.label}: ${completedCount} of ${requiredItems.length} required items done.`,
    };
  }

  if (!departmentReview?.signedOffAt) {
    return {
      status: "amber",
      label: "Awaiting department sign-off",
      reason: `${guide.label}: all required items done; department sign-off is missing.`,
    };
  }

  return {
    status: "green",
    label: "Ready",
    reason: `${guide.label}: all required items are complete and signed off.`,
  };
}
