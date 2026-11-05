export const CLAIMS_CACHE_KEY = "hakiki:claims-cache:v1";

export function readClaimsCache(storage = globalThis.localStorage) {
  try {
    const value = JSON.parse(storage?.getItem(CLAIMS_CACHE_KEY) || "null");
    if (Array.isArray(value?.claims) && value.savedAt) return value;
  } catch { /* Malformed or unavailable storage means there is no cache. */ }
  return null;
}

export function writeClaimsCache(claims, savedAt = new Date().toISOString(), storage = globalThis.localStorage) {
  try {
    storage?.setItem(CLAIMS_CACHE_KEY, JSON.stringify({ claims, savedAt }));
  } catch { /* The in-memory app remains usable when storage is unavailable. */ }
  return savedAt;
}

export function formatSavedTime(savedAt) {
  return new Date(savedAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export function retryDelayMs(attempt) {
  return Math.min(15_000 * (2 ** Math.max(0, attempt - 1)), 60_000);
}
