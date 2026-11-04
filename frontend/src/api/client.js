const BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8001";

async function request(path, options = {}) {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export const api = {
  // Supports q (search), status (all|ready|review|error), page, page_size
  getClaims: (params = {}) => {
    const qs = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== "" && v !== undefined)
    ).toString();
    return request(`/claims${qs ? `?${qs}` : ""}`);
  },
  getClaim: (id) => request(`/claims/${id}`),
  createClaim: (claimData) => request("/claims", { method: "POST", body: JSON.stringify(claimData) }),
  validateClaim: (id) => request(`/claims/${id}/validate`, { method: "POST" }),
  validateRaw: (claimData) =>
    request("/validate", { method: "POST", body: JSON.stringify(claimData) }),
  correctClaim: (id, correctedData) =>
    request(`/claims/${id}/correct`, {
      method: "POST",
      body: JSON.stringify(correctedData),
    }),
  getClaimAudit: (id) => request(`/claims/${id}/audit`),
  recordDepartmentReview: (id, event) =>
    request(`/claims/${id}/department-review`, { method: "POST", body: JSON.stringify(event) }),
  getDepartmentReview: (id, department) =>
    request(`/claims/${id}/department-review?department=${encodeURIComponent(department)}`),
  saveDepartmentReview: (id, department, review) =>
    request(`/claims/${id}/department-review`, {
      method: "PUT", body: JSON.stringify({ department, review }),
    }),
  getOutcomes: (claimId) => request(`/outcomes${claimId ? `?claim_id=${encodeURIComponent(claimId)}` : ""}`),
  saveOutcome: (outcome) => request("/outcomes", { method: "POST", body: JSON.stringify(outcome) }),
  recordStaffReview: (id, event) =>
    request(`/claims/${id}/staff-review`, { method: "POST", body: JSON.stringify(event) }),
  verifyAuditChain: () => request(`/audit/verify`),
  anchorLedger: (secret) => request("/ledger/anchor", { method: "POST", headers: { "X-Anchor-Secret": secret } }),
  verifyLedgerAnchor: () => request("/ledger/verify-anchor"),
  getManagementAnalytics: () => request("/analytics/overview"),
};
