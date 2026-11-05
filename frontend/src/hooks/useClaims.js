import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client.js";

const DEFAULT_MOCK_CLAIM = {
  id: "SHA-CLM-90210",
  patient_name: "Jane Doe",
  patient_id: "PT-88301-SHA",
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
  const [claims, setClaims] = useState([DEFAULT_MOCK_CLAIM]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getClaims();
      const loadedClaims = data.claims ?? [];
      // Use server claims when available; Jane Doe is only an offline fallback.
      setClaims(loadedClaims.length ? loadedClaims : [DEFAULT_MOCK_CLAIM]);
      return loadedClaims;
    } catch {
      // Keep the historic offline fallback, but make the missing database visible.
      setError("Database slow / unreachable. Showing the built-in offline demo claim; it is not synced with Oracle.");
      setClaims([DEFAULT_MOCK_CLAIM]);
      return [DEFAULT_MOCK_CLAIM];
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

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

  return { claims, loading, error, reload: load, patchPreview, addClaim };
}

