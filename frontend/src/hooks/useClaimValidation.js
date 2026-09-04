import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client.js";

function simulateValidation(claim, edits = {}) {
  const mergedClaim = { ...claim, ...edits };

  const diagnosisCode = mergedClaim.diagnosis_code || "";
  const claimedAmount = Number(mergedClaim.claimed_amount || 0);

  const codePassed =
    diagnosisCode === "A09" ||
    diagnosisCode === "A09.9";

  const amountPassed = claimedAmount <= 10000;

  const results = [
    {
      rule_id: "SHA-R1",
      passed: codePassed,
      severity: "error",
      field: "diagnosis_code",
      message: codePassed
        ? "Diagnosis code matches the active ICD-10 registry"
        : `Invalid ICD-10 Diagnosis code "${diagnosisCode}"`,
      suggested_value: "A09",
    },
    {
      rule_id: "SHA-R2",
      passed: amountPassed,
      severity: "error",
      field: "claimed_amount",
      message: amountPassed
        ? `Claimed amount KES ${claimedAmount.toLocaleString()} is within reimbursement limits`
        : `Claimed amount KES ${claimedAmount.toLocaleString()} exceeds KES 10,000 limit`,
      suggested_value: 3500,
    },
    {
      rule_id: "SHA-R3",
      passed: true,
      severity: "warning",
      field: "visit_date",
      message: "Visit date is within active policy window",
    },
  ];

  const failedCount = results.filter((r) => !r.passed).length;

  const score =
    failedCount === 0
      ? 100
      : failedCount === 1
        ? 75
        : 45;

  let color = "red";
  let status = "High Risk";

  if (score >= 85) {
    color = "green";
    status = "Ready for Submission";
  } else if (score >= 60) {
    color = "amber";
    status = "Needs Review";
  }

  return {
    score,
    status,
    color,
    error_count: failedCount,
    warning_count: results.filter(
      (r) => !r.passed && r.severity === "warning"
    ).length,
    results,
    explanations: {
      "SHA-R1":
        "The diagnosis code does not match an active ICD-10 code. Use a valid clinical diagnosis code.",
      "SHA-R2":
        `The requested amount of KES ${claimedAmount.toLocaleString()} exceeds the standard pre-authorized limit of KES 10,000.`,
    },
    fhir_claim_response: {
      resourceType: "ClaimResponse",
      id: `fhir-${mergedClaim.id}`,
      status: "active",
      outcome: failedCount === 0 ? "complete" : "error",
      disposition:
        failedCount === 0
          ? "Claim accepted by validation"
          : "Fails SHA validator rules",
      patient: {
        reference: `Patient/${mergedClaim.patient_id || "PT-UNKNOWN"}`,
      },
      created: new Date().toISOString().split("T")[0],
    },
  };
}

export function useClaimValidation(claim, onValidationComplete) {
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
  }, [claim?.id]);

  const reset = useCallback(() => {
    setState("idle");
    setValidation(null);
    setEdits({});
    setError(null);
    setSubmitResult(null);
  }, []);

  const validate = useCallback(async () => {
    if (!claim?.id) return;

    setState("loading");
    setError(null);
    setEdits({});
    setSubmitResult(null);

    try {
      const result = await api.validateClaim(claim.id);

      setValidation(result);
      setCurrentClaim((prev) => ({
        ...prev,
        ...(result.claim ?? {}),
      }));
      setState("results");

      onValidationComplete?.(claim.id, result);
    } catch (err) {
      console.warn("Backend validation unavailable; using demo fallback:", err);

      const result = simulateValidation(claim);

      setValidation(result);
      setCurrentClaim(claim);
      setState("results");

      onValidationComplete?.(claim.id, result);
    }
  }, [claim, onValidationComplete]);

  const editField = useCallback((field, value) => {
    setEdits((prev) => ({
      ...prev,
      [field]: value,
    }));
  }, []);

  const revalidateWithEdits = useCallback(async () => {
    if (!claim?.id || !validation || Object.keys(edits).length === 0) {
      return;
    }

    setState("loading");
    setError(null);

    const correctedClaim = {
      ...currentClaim,
      ...edits,
    };

    try {
      const result = await api.correctClaim(
        claim.id,
        edits
      );

      const nextValidation =
        result.validation ?? result;

      setValidation(nextValidation);

      setCurrentClaim((prev) => ({
        ...prev,
        ...edits,
        ...(result.claim ?? {}),
      }));

      setEdits({});
      setState("results");

      // CRITICAL:
      // This updates the score/status shown in the left queue.
      onValidationComplete?.(
        claim.id,
        nextValidation
      );
    } catch (err) {
      console.warn(
        "Backend correction unavailable; using demo fallback:",
        err
      );

      const nextValidation = simulateValidation(
        correctedClaim
      );

      setValidation(nextValidation);

      setCurrentClaim(correctedClaim);

      setEdits({});
      setState("results");

      // Also update the left queue when running in fallback mode.
      onValidationComplete?.(
        claim.id,
        nextValidation
      );
    }
  }, [
    claim,
    currentClaim,
    edits,
    validation,
    onValidationComplete,
  ]);

  const submit = useCallback(async () => {
    if (
      !claim?.id ||
      !validation ||
      validation.error_count > 0 ||
      Object.keys(edits).length > 0
    ) {
      return;
    }

    setState("submitting");
    setError(null);

    try {
      const result = await api.submitClaim(claim.id);

      setSubmitResult({
        ...result,
        mode: "demo",
        score: result.score ?? validation.score,
        fhir_claim_response:
          result.fhir_claim_response ??
          validation.fhir_claim_response,
      });

      setState("submitted");
    } catch (err) {
      console.warn(
        "Backend submission unavailable; using demo result:",
        err
      );

      setSubmitResult({
        mode: "demo",
        score: validation.score,
        fhir_claim_response:
          validation.fhir_claim_response,
      });

      setState("submitted");
    }
  }, [claim?.id, validation, edits]);

  return {
    state,
    validation,
    edits,
    error,
    submitResult,
    currentClaim,

    hasEdits: Object.keys(edits).length > 0,

    canSubmit:
      Boolean(validation) &&
      validation.error_count === 0 &&
      Object.keys(edits).length === 0,

    validate,
    editField,
    revalidateWithEdits,
    submit,
    reset,
  };
}
