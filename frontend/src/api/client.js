const BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8001";

async function request(path, options = {}) {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    // Backend errors: {"error": {"code", "message", "details"}}
    const body = await res.json().catch(() => ({}));
    const err = new Error(body.error?.message || body.detail || `HTTP ${res.status}`);
    err.code = body.error?.code;
    err.details = body.error?.details;
    err.status = res.status;
    throw err;
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
  validateClaim: (id) => request(`/claims/${id}/validate`, { method: "POST" }),
  validateRaw: (claimData) =>
    request("/validate", { method: "POST", body: JSON.stringify(claimData) }),
  // source: "manual" or the suggestion applied, kept in the corrections audit.
  correctClaim: (id, correctedData, source = "manual") =>
    request(`/claims/${id}/correct?source=${encodeURIComponent(source)}`, {
      method: "POST",
      body: JSON.stringify(correctedData),
    }),
  createClaim: (claimData) =>
    request("/claims", { method: "POST", body: JSON.stringify(claimData) }),
  // Hand the validated SHA bundle back to the hospital HIS (Hakiki never submits to SHA).
  handoffClaim: (id, acknowledgeWarnings = false) =>
    request(`/claims/${id}/handoff`, {
      method: "POST",
      body: JSON.stringify({ acknowledge_warnings: acknowledgeWarnings }),
    }),
  getHandoff: (id) => request(`/claims/${id}/handoff`),
  // Demo only: restore a claim, or every seeded claim, to its original state.
  resetClaim: (id) => request(`/claims/${id}/reset`, { method: "POST" }),
  resetDemo: () => request("/demo/reset", { method: "POST" }),
  // Code search for the claim form.
  searchIcd11: (q) => request(`/terminology/icd11?q=${encodeURIComponent(q)}&limit=8`),
  searchInterventions: (q, level = "") =>
    request(`/terminology/interventions?q=${encodeURIComponent(q)}&level=${encodeURIComponent(level)}&limit=8`),
  getClaimAudit: (id) => request(`/claims/${id}/audit`),
  verifyAuditChain: () => request(`/audit/verify`),
};
