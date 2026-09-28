import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client.js";

function toPreview(result) {
  return {
    score: result.score,
    status: result.status,
    color: result.color,
    error_count: result.error_count,
    warning_count: result.warning_count,
  };
}

/**
 * The claims queue. Single source of truth for the sidebar list and the
 * selected claim, so a correction in the workspace updates both at once.
 */
export function useClaims() {
  const [claims, setClaims] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getClaims({ page_size: 1000 });
      setClaims(data.claims ?? []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const addClaim = useCallback(async (claimData) => {
    const result = await api.createClaim(claimData);
    setClaims((prev) => [{ ...result.claim, _preview: result._preview }, ...prev]);
    return result.claim;
  }, []);

  // Replace one claim's data and/or score after a validation, correction or reset.
  const patchClaim = useCallback((claimId, { claim, validation } = {}) => {
    setClaims((prev) =>
      prev.map((c) =>
        c.id === claimId
          ? {
              ...c,
              ...(claim ?? {}),
              _preview: validation ? toPreview(validation) : c._preview,
            }
          : c
      )
    );
  }, []);

  const resetDemo = useCallback(async () => {
    const counts = await api.resetDemo();
    await load();
    return counts;
  }, [load]);

  return { claims, loading, error, reload: load, patchClaim, addClaim, resetDemo };
}
