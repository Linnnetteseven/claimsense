import { readFileSync } from "node:fs";

const demoClaims = JSON.parse(
  readFileSync(new URL("../../backend/data/demo_claims.json", import.meta.url), "utf-8"),
);

const DATE_TOKEN = /^\{\{today([+-]\d+)d\}\}$/;

export function resolveDates(value) {
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

// One claims-table row for a seeded claim. The template keeps its date tokens so
// the backend demo reset can re-resolve dates relative to the day of the reset.
export function seedRow(template) {
  return {
    claim_number: template.id,
    status: "draft",
    claim_data: resolveDates(template),
    seed_template: template,
    is_seed: true,
  };
}

export const demoSeedRows = () => demoClaims.map(seedRow);
