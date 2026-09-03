import demoClaims from "../../backend/data/demo_claims.json" with { type: "json" };

const DATE_TOKEN = /^\{\{today([+-]\d+)d\}\}$/;

function resolveDates(value) {
  if (typeof value === "string") {
    const match = value.match(DATE_TOKEN);
    if (!match) return value;
    const date = new Date();
    date.setUTCHours(0, 0, 0, 0);
    date.setUTCDate(date.getUTCDate() + Number(match[1]));
    return date.toISOString().slice(0, 10);
  }
  if (Array.isArray(value)) return value.map(resolveDates);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, resolveDates(item)]));
  }
  return value;
}

export const resolvedDemoClaims = () => resolveDates(demoClaims);
export const demoClaimNumbers = () => demoClaims.map((claim) => claim.id);
