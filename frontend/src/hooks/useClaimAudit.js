import { useCallback, useState } from "react";
import { api } from "../api/client.js";

export function useClaimAudit() {
  const [state, setState] = useState("idle");
  const [history, setHistory] = useState([]);
  const [error, setError] = useState(null);

  const load = useCallback(async (claimId) => {
    setState("loading");
    setError(null);
    try {
      const result = await api.getClaimAudit(claimId);
      setHistory(result.history || []);
      setState("loaded");
    } catch (err) {
      setError(err.message);
      setState("error");
    }
  }, []);

  return { state, history, error, load };
}