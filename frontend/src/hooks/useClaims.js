import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client.js";
import { formatSavedTime, readClaimsCache, retryDelayMs, writeClaimsCache } from "../utils/claimsCache.js";

const DEFAULT_MOCK_CLAIM = {
  id: "SYN-CLM-000001",
  is_synthetic: true,
  patient_id: "SYN-000001",
  facility_name: "Kerugoya Level 5 Hospital",
  department: "outpatient",
  visit_date: "2026-07-02",
  coverage_end_date: "2026-12-31",
  diagnosis_code: "INVALID_CODE",
  diagnosis_description: "Acute nasopharyngitis [common cold]",
  claimed_amount: 15000,
  _preview: {
    score: 45,
    status: "High Risk",
    color: "red",
    error_count: 2,
    warning_count: 0,
  },
};

/**
 * Loads the claims queue on mount and exposes a refresh function plus a
 * setter the ValidationPanel can use to patch a single claim's preview
 * in place after a (re)validation, without a full network refetch.
 */
export function useClaims() {
  const [claims, setClaims] = useState(() => readClaimsCache()?.claims ?? [DEFAULT_MOCK_CLAIM]);
  const [savedAt, setSavedAt] = useState(() => readClaimsCache()?.savedAt ?? null);
  const [loading, setLoading] = useState(() => !readClaimsCache());
  const [error, setError] = useState(null);
  const [offline, setOffline] = useState(false);
  const [retryAttempt, setRetryAttempt] = useState(0);
  const requestRef = useRef(null);

  const load = useCallback(async () => {
    if (requestRef.current) return requestRef.current;
    setLoading(true);
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 12_000);
    const request = (async () => {
      try {
        const data = await api.getClaims({}, { signal: controller.signal });
        const loadedClaims = data.claims ?? [];
        const savedTime = writeClaimsCache(loadedClaims);
        setClaims(loadedClaims);
        setSavedAt(savedTime);
        setError(null);
        setOffline(false);
        setRetryAttempt(0);
        return loadedClaims;
      } catch {
        const cached = readClaimsCache();
        const fallbackClaims = cached?.claims ?? [DEFAULT_MOCK_CLAIM];
        setClaims(fallbackClaims);
        setSavedAt(cached?.savedAt ?? null);
        setOffline(Boolean(cached));
        setError(cached
          ? `Database slow / unreachable. Offline: showing data saved at ${formatSavedTime(cached.savedAt)}.`
          : "Database slow / unreachable. Showing the built-in offline demo claim; it is not synced with Oracle.");
        setRetryAttempt((attempt) => attempt + 1);
        return fallbackClaims;
      } finally {
        window.clearTimeout(timeout);
        setLoading(false);
        requestRef.current = null;
      }
    })();
    requestRef.current = request;
    return request;
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Recover automatically while offline. Back off from 15s to at most 60s.
  useEffect(() => {
    if (!error) return undefined;
    const delay = retryDelayMs(retryAttempt);
    const timer = window.setTimeout(() => { load(); }, delay);
    return () => window.clearTimeout(timer);
  }, [error, load, retryAttempt]);

  /**
   * Submit a new claim to the backend and, on success, insert it into local
   * state immediately (with its returned preview) so the UI doesn't need a
   * full refetch to show it in the queue.
   */
  const addClaim = useCallback(async (claimData) => {
    try {
      const result = await api.createClaim(claimData);
      setClaims((prev) => [{ ...result.claim, _preview: result._preview }, ...prev]);
      return result.claim;
    } catch {
      // Offline fallback
      const mockNewClaim = {
        ...claimData,
        id: claimData.id || `SHA-CLM-MOCK-${Math.floor(Math.random() * 100000)}`,
        _preview: {
          score: 45,
          status: "High Risk",
          color: "red",
          error_count: 2,
          warning_count: 0,
        },
      };
      setClaims((prev) => [mockNewClaim, ...prev]);
      return mockNewClaim;
    }
  }, []);

  const patchPreview = useCallback((claimId, validationResult) => {
    setClaims((prev) =>
      prev.map((c) =>
        c.id === claimId
          ? {
              ...c,
              _preview: {
                score: validationResult.score,
                status: validationResult.status,
                color: validationResult.color,
                error_count: validationResult.error_count,
                warning_count: validationResult.warning_count,
              },
            }
          : c
      )
    );
  }, []);

  const markNeedsRevalidation = useCallback((claimId) => {
    setClaims((previous) => previous.map((claim) => claim.id === claimId ? {
      ...claim,
      _lifecycle: { ...(claim._lifecycle || {}), status: "needs_revalidation" },
      _preview: { ...(claim._preview || {}), status: "Needs revalidation", color: "amber" },
    } : claim));
  }, []);

  return { claims, loading, error, offline, savedAt, reload: load, patchPreview, markNeedsRevalidation, addClaim };
}

