import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client.js";
import { coerceFieldValue } from "../constants/status.js";

/**
 * Validation workflow for one claim.
 *
 * state: "idle" | "loading" | "results" | "saving" | "submitting" | "submitted"
 * ("submitted" means handed off to the hospital HIS, which submits to SHA.)
 *
 * Corrections are saved to the backend (and so to Supabase) and re-validated
 * in one call; the backend re-runs every rule, so fixing one field can clear
 * or surface other errors. onUpdate(claimId, { claim, validation }) keeps the
 * queue in sync.
 */
export function useClaimValidation(claim, onUpdate) {
  const [state, setState] = useState("idle");
  const [validation, setValidation] = useState(null);
  const [edits, setEdits] = useState({});
  const [currentClaim, setCurrentClaim] = useState(claim);
  const [error, setError] = useState(null);
  const [submitResult, setSubmitResult] = useState(null);

  useEffect(() => {
    setCurrentClaim(claim);
    setState("idle");
    setValidation(null);
    setEdits({});
    setError(null);
    setSubmitResult(null);
    // Reset only when a different claim is selected, not on every refetch of the same one.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [claim?.id]);

  const claimId = claim?.id;

  const reset = useCallback(() => {
    setState("idle");
    setValidation(null);
    setEdits({});
    setError(null);
    setSubmitResult(null);
  }, []);

  const validate = useCallback(async () => {
    if (!claimId) return;
    setState("loading");
    setError(null);
    setEdits({});
    setSubmitResult(null);
    try {
      const result = await api.validateClaim(claimId);
      setValidation(result);
      setState("results");
      onUpdate?.(claimId, { validation: result });
    } catch (err) {
      setError(`Validation failed: ${err.message}`);
      setState(validation ? "results" : "idle");
    }
  }, [claimId, onUpdate, validation]);

  const editField = useCallback((field, value) => {
    setEdits((prev) => ({ ...prev, [field]: coerceFieldValue(field, value) }));
  }, []);

  const discardEdits = useCallback(() => setEdits({}), []);

  // Save pending edits (plus any extra ones) and re-validate the whole claim.
  const saveCorrections = useCallback(
    async (extra = {}) => {
      const changes = { ...edits, ...extra };
      if (!claimId || Object.keys(changes).length === 0) return;
      setState("saving");
      setError(null);
      try {
        const result = await api.correctClaim(claimId, changes);
        setCurrentClaim(result.claim);
        setValidation(result.validation);
        setEdits({});
        setState("results");
        onUpdate?.(claimId, { claim: result.claim, validation: result.validation });
      } catch (err) {
        // Keep the officer's edits so nothing typed is lost.
        setEdits(changes);
        setError(`Could not save corrections: ${err.message}`);
        setState("results");
      }
    },
    [claimId, edits, onUpdate]
  );

  const applyFix = useCallback(
    (field, value) => saveCorrections({ [field]: coerceFieldValue(field, value) }),
    [saveCorrections]
  );

  // Demo: put the claim back to its seeded state and validate it again.
  const restoreOriginal = useCallback(async () => {
    if (!claimId) return;
    setState("loading");
    setError(null);
    setEdits({});
    setSubmitResult(null);
    try {
      const restored = await api.resetClaim(claimId);
      const result = await api.validateClaim(claimId);
      setCurrentClaim(restored.claim);
      setValidation(result);
      setState("results");
      onUpdate?.(claimId, { claim: restored.claim, validation: result });
    } catch (err) {
      setError(`Could not restore the original claim: ${err.message}`);
      setState(validation ? "results" : "idle");
    }
  }, [claimId, onUpdate, validation]);

  const submit = useCallback(
    async (acknowledgeWarnings = false) => {
      if (!claimId || !validation || validation.error_count > 0 || Object.keys(edits).length > 0) {
        return;
      }
      setState("submitting");
      setError(null);
      try {
        const result = await api.handoffClaim(claimId, acknowledgeWarnings);
        setSubmitResult(result);
        setState("submitted");
        onUpdate?.(claimId, { claim: { _status: "handed_off" } });
      } catch (err) {
        setError(`Hand-off failed: ${err.message}`);
        setState("results");
      }
    },
    [claimId, validation, edits, onUpdate]
  );

  const hasEdits = Object.keys(edits).length > 0;

  return {
    state,
    validation,
    edits,
    error,
    submitResult,
    currentClaim,
    hasEdits,
    canSubmit: Boolean(validation) && validation.error_count === 0 && !hasEdits,
    validate,
    editField,
    discardEdits,
    saveCorrections,
    applyFix,
    restoreOriginal,
    submit,
    reset,
  };
}
