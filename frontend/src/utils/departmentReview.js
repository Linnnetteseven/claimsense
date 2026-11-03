const EMPTY_REVIEW = {
  completed: {},
  evidence: {},
  reviewer: "",
  note: "",
  signedOffAt: null,
  signedOffBy: "",
};

export const DEPARTMENT_REVIEW_UPDATED = "hakiki:department-review-updated";

export function departmentReviewStorageKey(claimId, department) {
  const departmentKey = (department || "").toLowerCase();
  return `hakiki:department-review:${claimId || "unassigned"}:${departmentKey}`;
}

export function readDepartmentReview(claimId, department) {
  const key = departmentReviewStorageKey(claimId, department);
  try {
    return { ...EMPTY_REVIEW, ...JSON.parse(window.localStorage.getItem(key) || "{}") };
  } catch {
    return { ...EMPTY_REVIEW };
  }
}
