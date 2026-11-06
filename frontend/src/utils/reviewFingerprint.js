function sortObjectKeys(value) {
  if (Array.isArray(value)) return value.map(sortObjectKeys);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.keys(value).sort().map((key) => [key, sortObjectKeys(value[key])]),
    );
  }
  return value;
}

export async function fingerprintDepartmentReview(department, review) {
  const snapshot = {
    department,
    completed: review.completed || {},
    evidence: review.evidence || {},
    reviewer: review.reviewer || "",
    note: review.note || "",
    signedOffAt: review.signedOffAt || null,
    signedOffBy: review.signedOffBy || "",
  };
  const canonical = JSON.stringify(sortObjectKeys(snapshot));
  const bytes = new TextEncoder().encode(canonical);
  const digest = await window.crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}
