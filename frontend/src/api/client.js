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
  validateClaim: (id) => request(`/claims/${id}/validate`, { method: "POST" }),
  validateRaw: (claimData) =>
    request("/validate", { method: "POST", body: JSON.stringify(claimData) }),
  correctClaim: (id, correctedData) =>
    request(`/claims/${id}/correct`, {
      method: "POST",
      body: JSON.stringify(correctedData),
    }),
  submitClaim: (id) => request(`/claims/${id}/submit`, { method: "POST" }),
};
