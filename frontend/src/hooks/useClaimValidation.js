import { useCallback, useState } from "react";
import { api } from "../api/client.js";

/** Drives persisted claim validation, correction, and submission actions. */
export function useClaimValidation(claim, onValidationComplete, onLifecycleChange) {
  const [state, setState] = useState("idle");
  const [validation, setValidation] = useState(null);
  const [edits, setEdits] = useState({});
  const [error, setError] = useState(null);
  const [submitResult, setSubmitResult] = useState(null);

  const reset = useCallback(() => {
    setState("idle");
    setValidation(null);
    setEdits({});
    setError(null);
    setSubmitResult(null);
  }, []);

  const validate = useCallback(async () => {
    setState("loading");
    setError(null);
    try {
      const result = await api.validateClaim(claim.id);
      setValidation(result);
      setEdits({});
      setState("results");
      onValidationComplete?.(claim.id, result);
      if (result.lifecycle) onLifecycleChange?.(claim.id, result.lifecycle);
      return result;
    } catch (validationError) {
      setState("idle");
      setError(validationError.message || "Validation could not be saved. Please retry.");
      return null;
    }
  }, [claim.id, onValidationComplete, onLifecycleChange]);

  const editField = useCallback((field, value) => {
    setEdits((previous) => ({ ...previous, [field]: value }));
  }, []);

  const revalidateWithEdits = useCallback(async (correctionReason = "") => {
    if (!validation) return null;
    const corrected = { ...claim, ...edits };
    setState("loading");
    setError(null);
    try {
      const saved = await api.correctClaim(claim.id, corrected, correctionReason);
      const result = saved.validation;
      setValidation(result);
      setEdits({});
      setState("results");
      onValidationComplete?.(claim.id, result, saved.claim);
      if (result.lifecycle) onLifecycleChange?.(claim.id, result.lifecycle);
      return result;
    } catch (correctionError) {
      setState("results");
      setError(correctionError.message || "Correction could not be saved and validated.");
      return null;
    }
  }, [claim, edits, validation, onValidationComplete, onLifecycleChange]);

  const submit = useCallback(async () => {
    setState("submitting");
    setError(null);
    try {
      const result = await api.submitClaim(claim.id);
      setSubmitResult(result);
      setState("submitted");
      if (result.lifecycle) onLifecycleChange?.(claim.id, result.lifecycle);
      return result;
    } catch (submitError) {
      setState("results");
      setError(submitError.message || "Claim submission failed.");
      return null;
    }
  }, [claim.id, onLifecycleChange]);

  return {
    state,
    validation,
    edits,
    error,
    submitResult,
    hasEdits: Object.keys(edits).length > 0,
    canSubmit: (validation?.error_count ?? 1) === 0 && Object.keys(edits).length === 0,
    validate,
    editField,
    revalidateWithEdits,
    submit,
    reset,
    setValidation,
  };
}
