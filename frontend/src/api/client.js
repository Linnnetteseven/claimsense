const BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8001";
const auditRequests = new Map();

async function request(path, options = {}) {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const error = new Error(body.detail || `HTTP ${res.status}`);
    error.status = res.status;
    throw error;
  }
  return res.json();
}

export const api = {
  getUiSettings: () => request("/settings/ui"),
  // Supports q (search), status (all|ready|review|error), page, page_size
  getClaims: (params = {}, options = {}) => {
    const qs = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== "" && v !== undefined)
    ).toString();
    return request(`/claims${qs ? `?${qs}` : ""}`, options);
  },
  getClaim: (id) => request(`/claims/${id}`),
  createClaim: (claimData) => request("/claims", { method: "POST", body: JSON.stringify(claimData) }),
  validateClaim: (id) => request(`/claims/${id}/validate`, { method: "POST" }),
  recheckClaim: (id) => request(`/claims/${id}/recheck`, { method: "POST" }),
  validateRaw: (claimData) =>
    request("/validate", { method: "POST", body: JSON.stringify(claimData) }),
  correctClaim: (id, correctedData, correctionReason = "") =>
    request(`/claims/${id}/correct`, {
      method: "POST",
      body: JSON.stringify({ claim: correctedData, correction_reason: correctionReason }),
    }),
  startCorrection: (id, reason = "") => request(`/claims/${id}/correction`, {
    method: "POST", body: JSON.stringify({ reason }),
  }),
  submitClaim: (id) => request(`/claims/${id}/submit`, { method: "POST" }),
  getClaimAudit: (id, { signal } = {}) => {
    let entry = auditRequests.get(id);
    if (!entry) {
      const controller = new AbortController();
      entry = { controller, subscribers: 0, settled: false };
      entry.promise = request(`/claims/${id}/audit`, { signal: controller.signal })
        .finally(() => {
          entry.settled = true;
          if (auditRequests.get(id) === entry) auditRequests.delete(id);
        });
      auditRequests.set(id, entry);
    }
    entry.subscribers += 1;
    return new Promise((resolve, reject) => {
      let released = false;
      const release = () => {
        if (released) return;
        released = true;
        entry.subscribers -= 1;
        if (!entry.settled && entry.subscribers === 0) entry.controller.abort();
      };
      const onAbort = () => {
        release();
        reject(new DOMException("Audit request aborted", "AbortError"));
      };
      if (signal?.aborted) return onAbort();
      signal?.addEventListener("abort", onAbort, { once: true });
      entry.promise.then(resolve, reject).finally(() => {
        signal?.removeEventListener("abort", onAbort);
        release();
      });
    });
  },
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
  getAnchorStatus: (rootHash) => request(`/ledger/anchor-status${rootHash ? `?root_hash=${encodeURIComponent(rootHash)}` : ""}`),
  checkAnchorStatus: (rootHash) => request(`/ledger/anchor-status/check${rootHash ? `?root_hash=${encodeURIComponent(rootHash)}` : ""}`, { method: "POST" }),
  verifyFullLedger: () => request("/ledger/verify-full", { method: "POST" }),
  getManagementAnalytics: () => request("/analytics/overview"),
  createEvidencePack: (claimId) => request(`/claims/${claimId}/evidence-pack`, { method: "POST" }),
  evidencePackFileUrl: (path) => `${BASE_URL}${path}`,
};
