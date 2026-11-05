import assert from "node:assert/strict";
import { CLAIMS_CACHE_KEY, readClaimsCache, retryDelayMs, writeClaimsCache } from "./claimsCache.js";

const values = new Map();
const storage = {
  getItem: (key) => values.get(key) ?? null,
  setItem: (key, value) => values.set(key, value),
};
const claims = [{ id: "SYN-CLM-000001" }];

writeClaimsCache(claims, "2026-11-05T08:30:00.000Z", storage);
assert.deepEqual(readClaimsCache(storage), { claims, savedAt: "2026-11-05T08:30:00.000Z" });
assert.equal(values.has(CLAIMS_CACHE_KEY), true);
assert.equal(retryDelayMs(1), 15_000);
assert.equal(retryDelayMs(2), 30_000);
assert.equal(retryDelayMs(3), 60_000);
assert.equal(retryDelayMs(8), 60_000);

const malformedStorage = { getItem: () => "not json" };
assert.equal(readClaimsCache(malformedStorage), null);
