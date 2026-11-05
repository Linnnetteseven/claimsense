import { useState, useEffect, useMemo } from "react";
import PropTypes from "prop-types";
import ScoreGauge from "./ScoreGauge.jsx";
import StatusBadge from "./StatusBadge.jsx";
import ErrorCard from "./ErrorCard.jsx";
import { CheckIcon, SpinnerIcon } from "./icons.jsx";
import { useClaimValidation } from "../hooks/useClaimValidation.js";
import AuditTrailTab from "./AuditTrailTab.jsx";
import DeptGuideTab from "./DeptGuideTab.jsx";
import OutcomeFeedbackTab from "./OutcomeFeedbackTab.jsx";
import { DEPARTMENT_REVIEW_UPDATED, readDepartmentReview } from "../utils/departmentReview.js";
import { getOverallStatus } from "../utils/overallStatus.js";
import { api } from "../api/client.js";

const OVERALL_RULE_IDS = new Set([
  "MISSING_FIELDS", "INVALID_ICD10", "VISIT_DATE", "EMPTY_ITEMS",
  "COVERAGE_EXPIRED", "AMOUNT_MISMATCH", "AMOUNT_HIGH",
  "SHA-R1", "SHA-R2", "SHA-R3",
]);
const DEPARTMENT_RULE_IDS = {
  maternity: ["MISSING_PARTOGRAPH"],
  renal: ["IMPLAUSIBLE_FREQUENCY"],
  surgical: ["MISSING_POSTOP_NOTES"],
  outpatient: [],
};

/**
 * Main right workspace: patient profile header, claim checks, structured details and department workflow,
 * status timeline on the right edge, document upload/scan simulation, and action buttons.
 */
export default function ValidationPanel({ claim, onValidationComplete, privacyMode = false }) {
  const [departmentReview, setDepartmentReview] = useState(() => (
    claim ? readDepartmentReview(claim.id, claim.department) : null
  ));
  const [officerName, setOfficerName] = useState("");
  const [officerDecision, setOfficerDecision] = useState("reviewed");
  const [officerReviewState, setOfficerReviewState] = useState("idle");
  const [officerReviewError, setOfficerReviewError] = useState("");
  const {
    state,
    validation,
    edits,
    error,
    submitResult,
    hasEdits,
    canSubmit,
    validate,
    editField,
    revalidateWithEdits,
    submit,
    reset,
  } = useClaimValidation(claim, onValidationComplete);

  useEffect(() => {
    console.log("ValidationPanel - Current State:", state);
    console.log("ValidationPanel - Validation Data:", privacyMode ? "********" : validation);
  }, [state, validation, privacyMode]);

  useEffect(() => {
    setDepartmentReview(claim ? readDepartmentReview(claim.id, claim.department) : null);
  }, [claim]);

  useEffect(() => {
    const refreshDepartmentReview = (event) => {
      const { claimId, department: reviewDepartment } = event.detail || {};
      if (claimId === claim?.id && reviewDepartment === (claim?.department || "").toLowerCase()) {
        setDepartmentReview(readDepartmentReview(claim.id, claim.department));
      }
    };
    window.addEventListener(DEPARTMENT_REVIEW_UPDATED, refreshDepartmentReview);
    return () => window.removeEventListener(DEPARTMENT_REVIEW_UPDATED, refreshDepartmentReview);
  }, [claim]);

  const [activeTab, setActiveTab] = useState("Claim Checks");
  const overallStatus = useMemo(() => getOverallStatus(
    { ...(validation || claim?._preview || {}), department: claim?.department },
    departmentReview,
  ), [claim, validation, departmentReview]);
  const overallChecks = validation?.results?.filter((result) => OVERALL_RULE_IDS.has(result.rule_id)) || [];
  const departmentChecks = validation?.results?.filter((result) => (DEPARTMENT_RULE_IDS[claim?.department] || []).includes(result.rule_id)) || [];

  const handleOfficerReview = async () => {
    if (!officerName.trim() || hasEdits) return;
    setOfficerReviewState("saving");
    setOfficerReviewError("");
    try {
      const response = await api.recordStaffReview(claim.id, {
        reviewer: officerName.trim(),
        decision: officerDecision,
      });
      if (!response.recorded) throw new Error("The audit event could not be saved.");
      setOfficerReviewState("saved");
    } catch (reviewError) {
      setOfficerReviewState("error");
      setOfficerReviewError(reviewError.message || "Could not record the officer review.");
    }
  };

  const handleEditField = (field, value) => {
    setOfficerReviewState("idle");
    editField(field, value);
  };

  const handleRevalidate = () => {
    setOfficerReviewState("idle");
    return revalidateWithEdits();
  };

  // Document scan simulation state
  const [scanState, setScanState] = useState("idle"); // "idle" | "scanning" | "done"
  const [extractedData, setExtractedData] = useState(null);
  const privateValue = (value) => privacyMode && value ? "********" : (value ?? "N/A");
  const maskFhirPayload = (payload) => {
    if (!privacyMode || !payload || typeof payload !== "object") return payload;
    const sensitiveKey = /(patient|subject|identifier|name|birth|address|telecom|phone|email|diagnos|condition|service|item|amount|price|date|reference|insurer|payee)/i;
    const visit = (value, key = "") => {
      if (Array.isArray(value)) return value.map((item) => visit(item, key));
      if (value && typeof value === "object") return Object.fromEntries(Object.entries(value).map(([childKey, child]) => [childKey, visit(child, childKey)]));
      return sensitiveKey.test(key) && value != null ? "********" : value;
    };
    return visit(payload);
  };

  if (!claim) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-slate-400 dark:text-slate-500 p-8 text-center bg-slate-50/50 dark:bg-slate-900/30">
        <svg className="w-12 h-12 mb-4 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01" /></svg>
        <p className="text-sm font-medium">Select a claim from the queue to start validation.</p>
      </div>
    );
  }
  // Handle simulated document drop/upload
  const handleFileUpload = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setScanState("scanning");

    setTimeout(() => {
      setScanState("done");
      setExtractedData({
        diagnosis_code: "A09",
        diagnosis_description: "Diarrhoea and gastroenteritis of infectious origin",
        visit_date: "2026-07-02",
        claimed_amount: 8500,
      });
    }, 2000);
  };

  const applyExtractedData = () => {
    if (!extractedData) return;
    Object.entries(extractedData).forEach(([field, value]) => {
      handleEditField(field, value);
    });
    setScanState("applied");
  };

  // Determine current timeline active step
  let activeStep = 0;
  if (state === "idle") {
    activeStep = 0;
  } else if (state === "loading") {
    activeStep = 1;
  } else if (state === "results") {
    activeStep = validation?.error_count > 0 ? 2 : 3;
  } else if (state === "submitted" || state === "submitting") {
    activeStep = 3;
  }

  if (state === "submitted" && submitResult) {
    return (
      <div className="flex-1 bg-slate-50 dark:bg-slate-900 p-8 overflow-y-auto">
        <div className="max-w-3xl mx-auto bg-white dark:bg-slate-950 border border-slate-200/80 dark:border-slate-850 rounded-2xl p-8 shadow-sm text-center">
          <div className="w-16 h-16 rounded-full bg-emerald-100 dark:bg-emerald-950/20 flex items-center justify-center mx-auto mb-5">
            <CheckIcon className="w-8 h-8 text-emerald-600 dark:text-emerald-400" />
          </div>
          <h2 className="text-2xl font-bold text-slate-800 dark:text-slate-100">Claim Successfully Submitted</h2>
          <p className="text-slate-500 dark:text-slate-400 text-sm mt-2 max-w-md mx-auto">
            {submitResult.mode === "mock"
              ? "Demo submission simulated. No claim was sent to a live openIMIS service."
              : "The claim was sent through the configured openIMIS connection."}
          </p>

          <div className="my-6 p-4 bg-slate-50 dark:bg-slate-900 border border-slate-200/60 dark:border-slate-800 rounded-xl max-w-sm mx-auto flex items-center justify-between">
            <span className="text-xs text-slate-500 dark:text-slate-400 font-semibold uppercase tracking-wider">Final Adjudication Score</span>
            <span className="text-lg font-bold text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-950/30 px-3 py-1 rounded-lg border border-emerald-100 dark:border-emerald-900/40">
              {submitResult.score}/100
            </span>
          </div>

          <div className="w-full text-left bg-slate-900 dark:bg-slate-950 border border-slate-800 dark:border-slate-850 rounded-xl p-5 overflow-hidden shadow-inner mb-6">
            <h3 className="text-xs font-bold text-slate-400 dark:text-slate-500 uppercase tracking-widest mb-3">FHIR R4 ClaimResponse Payload</h3>
            <pre className="text-xs text-emerald-400 dark:text-emerald-500 font-mono overflow-x-auto max-h-60">
              {JSON.stringify(privacyMode ? "********" : maskFhirPayload(submitResult.fhir_claim_response || validation?.fhir_claim_response), null, 2)}
            </pre>
          </div>

          <button
            type="button"
            onClick={reset}
            className="bg-teal-600 hover:bg-teal-700 active:scale-95 text-white font-semibold text-sm px-6 py-2.5 rounded-xl transition-all shadow-sm"
          >
            Validate Next Claim
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex overflow-hidden">
      {/* Dynamic workspace pane */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Patient Profile Header */}
        <div className="bg-white dark:bg-slate-950 border-b border-slate-200 dark:border-slate-850 px-5 py-4 flex-shrink-0">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="flex items-center gap-3 min-w-0">
              <div className="w-12 h-12 rounded-full bg-teal-50 dark:bg-teal-950/20 border border-teal-100 dark:border-teal-900/30 flex items-center justify-center text-teal-700 dark:text-teal-400 text-lg font-bold shadow-inner shrink-0">
                {privacyMode ? "**" : claim.patient_name ? claim.patient_name.split(" ").map(n => n[0]).join("") : "PT"}
              </div>
              <div className="min-w-0">
                <h2 className="text-lg font-bold text-slate-800 dark:text-slate-100 leading-tight break-words">
                    {privateValue(claim.patient_name)}
                </h2>
                <div className="flex flex-wrap items-center gap-x-2 gap-y-1 mt-2">
                  {import.meta.env.VITE_SYNTHETIC_LABEL === "full" && claim.is_synthetic && (
                    <span className="text-[10px] font-bold uppercase tracking-wide text-amber-700 dark:text-amber-300 bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-900 rounded px-1.5 py-0.5">
                      Synthetic demo data
                    </span>
                  )}
                  <StatusBadge status={overallStatus.label} color={overallStatus.status} small />
                  {(validation?.score ?? claim._preview?.score) !== undefined && (
                    <span className="text-xs text-slate-500 dark:text-slate-400" title="Automated score">
                      Automated score: <span className="font-semibold text-slate-700 dark:text-slate-300">{validation?.score ?? claim._preview.score}/100</span>
                    </span>
                  )}
                </div>
                <p className="text-xs text-slate-500 dark:text-slate-400 font-medium mt-2 break-words">
                  ID: <code className="font-mono bg-slate-50 dark:bg-slate-900 border border-slate-100 dark:border-slate-800 rounded px-1 text-slate-600 dark:text-slate-400">{privateValue(claim.id)}</code>
                  <span className="mx-2 text-slate-300 dark:text-slate-700">•</span>
                  Facility: <span className="text-slate-700 dark:text-slate-300">{claim.facility_name}</span>
                </p>
              </div>
            </div>
            <div className="flex flex-row sm:flex-col text-left sm:text-right gap-2 sm:gap-1 sm:self-end shrink-0">
              <span className="text-[10px] text-slate-400 dark:text-slate-500 font-bold uppercase tracking-wider">Policy/Visit Date</span>
              <span className="text-sm font-semibold text-slate-700 dark:text-slate-300">{privateValue(claim.visit_date)}</span>
            </div>
          </div>
        </div>

        {/* Tabbed Navigation Selector */}
        <div className="bg-white dark:bg-slate-950 border-b border-slate-200 dark:border-slate-850 px-4 flex-shrink-0">
          <nav className="grid grid-cols-2 lg:grid-cols-6 gap-x-2" aria-label="Tabs">
            {["Claim Checks", "Claim details", "Technical", "Audit Trail", "Department Workspace", "Outcome Feedback"].map((tab) => {
              const isActive = activeTab === tab;
              return (
                <button
                  key={tab}
                  type="button"
                  onClick={() => setActiveTab(tab)}
                  className={`min-w-0 py-3 px-1.5 font-semibold text-xs sm:text-sm leading-tight text-center border-b-2 transition-all ${
                    isActive
                      ? "border-teal-600 dark:border-teal-450 text-teal-600 dark:text-teal-450"
                      : "border-transparent text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200"
                  }`}
                >
                  {tab}
                </button>
              );
            })}
          </nav>
        </div>

        {/* Tab Content Canvas */}
        <div className="flex-1 overflow-y-auto p-6 bg-slate-50/50 dark:bg-slate-900/30">
          {error && (
            <div role="alert" className="mb-4 rounded-xl bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-900/30 p-4 text-sm text-red-700 dark:text-red-400 shadow-sm">
              {error}
            </div>
          )}

          {activeTab === "Claim Checks" && (
            <div className="flex flex-col gap-5">
              <div className="order-2 bg-white dark:bg-slate-950 border border-slate-200/80 dark:border-slate-850 rounded-2xl p-4 shadow-sm">
                <h3 className="text-sm font-bold text-slate-800 dark:text-slate-200 mb-2 flex items-center gap-2">
                  <svg className="w-5 h-5 text-teal-600 dark:text-teal-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                  Scan Claim Invoice/Document
                </h3>
                <p className="text-xs text-slate-500 dark:text-slate-400 mb-3">
                  Optional document scan. OCR extraction is simulated in this demo; it does not read the uploaded file.
                </p>

                {scanState === "idle" && (
                  <label className="border-2 border-dashed border-slate-200 dark:border-slate-800 hover:border-teal-500 dark:hover:border-teal-450 rounded-xl p-4 flex flex-col items-center justify-center cursor-pointer transition-all hover:bg-teal-50/20 dark:hover:bg-teal-950/5 group">
                    <svg className="w-8 h-8 text-slate-400 dark:text-slate-600 group-hover:text-teal-600 dark:group-hover:text-teal-400 mb-2 transition-colors" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                    </svg>
                    <span className="text-xs font-semibold text-slate-600 dark:text-slate-350 group-hover:text-teal-700 dark:group-hover:text-teal-400">Choose Invoice Document</span>
                    <span className="text-[10px] text-slate-400 dark:text-slate-500 mt-1">PDF, JPG, PNG (Max 5MB)</span>
                    <input type="file" className="hidden" accept=".pdf,.png,.jpg,.jpeg" onChange={handleFileUpload} />
                  </label>
                )}

                {scanState === "scanning" && (
                  <div className="border border-slate-100 dark:border-slate-800 rounded-xl p-5 flex flex-col items-center justify-center bg-slate-50 dark:bg-slate-900/60 relative overflow-hidden">
                    <div className="absolute top-0 left-0 right-0 h-0.5 bg-gradient-to-r from-teal-400 to-emerald-500 animate-[pulse_1.5s_infinite] shadow-lg shadow-teal-500" />
                    <SpinnerIcon className="w-8 h-8 text-teal-600 mb-2" />
                    <p className="text-xs font-semibold text-slate-700 dark:text-slate-200">Preparing sample extraction...</p>
                    <p className="text-[10px] text-slate-400 dark:text-slate-500 mt-1">Simulated OCR; no OCR service is connected.</p>
                  </div>
                )}

                {scanState === "done" && (
                  <div className="border border-teal-100 dark:border-teal-900/30 rounded-xl p-4 bg-teal-50/20 dark:bg-teal-950/10">
                    <div className="flex items-center justify-between mb-3">
                      <span className="text-xs font-bold text-teal-800 dark:text-teal-400 flex items-center gap-1.5">
                        <span className="w-2 h-2 rounded-full bg-teal-500" />
                        Sample extraction ready
                      </span>
                      <span className="text-[10px] text-slate-400 dark:text-slate-500">Simulated OCR</span>
                    </div>
                    <div className="grid grid-cols-2 gap-3 mb-4 bg-white dark:bg-slate-950 p-3 rounded-lg border border-slate-100 dark:border-slate-850 text-xs">
                      <div>
                        <span className="text-slate-400 dark:text-slate-500 block mb-0.5">ICD-10 Diagnosis</span>
                        <strong className="text-slate-700 dark:text-slate-200 font-semibold">{privateValue(`${extractedData.diagnosis_code} - ${extractedData.diagnosis_description}`)}</strong>
                      </div>
                      <div>
                        <span className="text-slate-400 dark:text-slate-500 block mb-0.5">Visit Date</span>
                        <strong className="text-slate-700 dark:text-slate-200 font-semibold">{privateValue(extractedData.visit_date)}</strong>
                      </div>
                      <div>
                        <span className="text-slate-400 dark:text-slate-500 block mb-0.5">Claimed Amount</span>
                        <strong className="text-slate-700 dark:text-slate-200 font-semibold">{privacyMode ? "********" : `KES ${extractedData.claimed_amount.toLocaleString()}`}</strong>
                      </div>
                    </div>

                    <div className="flex gap-2.5">
                      <button
                        type="button"
                        onClick={applyExtractedData}
                        className="bg-teal-600 hover:bg-teal-700 text-white font-semibold text-xs px-3.5 py-2 rounded-lg shadow-sm transition-all"
                      >
                        Apply Extracted Data
                      </button>
                      <button
                        type="button"
                        onClick={() => setScanState("idle")}
                        className="border border-slate-200 dark:border-slate-800 text-slate-500 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-900 font-semibold text-xs px-3 py-2 rounded-lg transition-all"
                      >
                        Clear
                      </button>
                    </div>
                  </div>
                )}

                {scanState === "applied" && (
                  <div className="border border-emerald-100 dark:border-emerald-900/30 rounded-xl p-4 bg-emerald-50/20 dark:bg-emerald-950/10 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="w-5 h-5 rounded-full bg-emerald-100 dark:bg-emerald-950/20 flex items-center justify-center text-emerald-700 dark:text-emerald-400 text-xs">✓</span>
                      <div>
                        <p className="text-xs font-bold text-slate-800 dark:text-slate-200">Extracted Data Applied</p>
                        <p className="text-[10px] text-slate-400 dark:text-slate-500 mt-0.5">Click &quot;Re-validate with corrections&quot; below to recheck rules.</p>
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => setScanState("idle")}
                      className="text-xs text-teal-600 dark:text-teal-400 hover:underline font-semibold"
                    >
                      Scan Another
                    </button>
                  </div>
                )}
              </div>

              {state === "idle" && (
                <div className="order-1 bg-white dark:bg-slate-950 border border-slate-200/80 dark:border-slate-850 rounded-2xl p-6 text-center shadow-sm">
                  <p className="text-slate-500 dark:text-slate-450 text-sm mb-4 font-medium">
                    This claim needs validation against SHA pre-submission policies.
                  </p>
                  <button
                    type="button"
                    onClick={validate}
                    className="bg-teal-600 text-white px-6 py-2.5 rounded-xl text-sm font-semibold hover:bg-teal-700 active:scale-95 transition-all shadow-sm"
                  >
                    Validate Claim
                  </button>
                </div>
              )}

              {state === "loading" && (
                <div className="order-1 bg-white dark:bg-slate-950 border border-slate-200/80 dark:border-slate-850 rounded-2xl p-10 flex flex-col items-center justify-center shadow-sm">
                  <SpinnerIcon />
                  <p className="text-sm font-semibold text-slate-700 dark:text-slate-200 mt-3">Running claim checks...</p>
                  <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">Generating plain English rule interpretations</p>
                </div>
              )}

              {(state === "results" || state === "submitting") && validation && (
                <>
                  <div className="flex flex-col md:flex-row items-center gap-6 bg-white dark:bg-slate-950 border border-slate-200/80 dark:border-slate-850 rounded-2xl p-6 shadow-sm">
                    <ScoreGauge score={validation.score} />
                    <div className="flex-1 text-center md:text-left">
                      <div className="flex flex-col md:flex-row md:items-center gap-2 justify-center md:justify-start">
                        <span className="text-2xl font-extrabold text-slate-800 dark:text-slate-100">
                          {validation.error_count === 0
                            ? "No errors found"
                            : `${validation.error_count} Rule Failure${
                                validation.error_count !== 1 ? "s" : ""
                              }`}
                        </span>
                        {validation.warning_count > 0 && (
                          <span className="text-xs font-bold text-amber-700 dark:text-amber-450 bg-amber-50 dark:bg-amber-950/20 border border-amber-100 dark:border-amber-900/30 px-2 py-0.5 rounded-md self-center">
                            {validation.warning_count} Warning{validation.warning_count !== 1 ? "s" : ""}
                          </span>
                        )}
                      </div>
                      <div className="grid grid-cols-2 gap-4 mt-4 pt-4 border-t border-slate-100 dark:border-slate-850 text-xs text-slate-500 dark:text-slate-400 font-medium">
                        <div>
                          <span className="text-[10px] text-slate-400 dark:text-slate-500 uppercase block">Diagnosis</span>
                          <span className="text-slate-800 dark:text-slate-200 font-semibold">{edits.diagnosis_code ?? claim.diagnosis_code} — {privateValue(claim.diagnosis_description)}</span>
                        </div>
                        <div>
                          <span className="text-[10px] text-slate-400 dark:text-slate-500 uppercase block">Claimed Amount</span>
                          <span className="text-slate-800 dark:text-slate-200 font-semibold">{privacyMode ? "********" : `KES ${Number(edits.claimed_amount ?? claim.claimed_amount).toLocaleString()}`}</span>
                        </div>
                      </div>
                    </div>
                  </div>

                  <div>
                    <h3 className="text-xs font-bold text-slate-400 dark:text-slate-500 uppercase tracking-widest mb-3">
                      Overall claim checks ({overallChecks.length})
                    </h3>
                    <div className="space-y-3">
                      {overallChecks.map((result) => (
                        <ErrorCard key={result.rule_id} result={result}
                          explanation={privacyMode ? "********" : validation.explanations?.[result.rule_id]}
                          fieldValue={privacyMode ? "********" : edits[result.field] ?? claim[result.field]}
                          onChange={!result.passed ? handleEditField : undefined} />
                      ))}
                    </div>
                    <h3 className="text-xs font-bold text-slate-400 dark:text-slate-500 uppercase tracking-widest mt-6 mb-3">
                      {claim.department ? `${claim.department} department rule checks` : "Department rule checks"}
                    </h3>
                    <div className="space-y-3">
                      {departmentChecks.length ? departmentChecks.map((result) => (
                        <ErrorCard key={result.rule_id} result={result}
                          explanation={privacyMode ? "********" : validation.explanations?.[result.rule_id]}
                          fieldValue={privacyMode ? "********" : edits[result.field] ?? claim[result.field]}
                          onChange={!result.passed ? handleEditField : undefined} />
                      )) : <p className="rounded-lg border border-slate-200 dark:border-slate-800 p-3 text-xs text-slate-500 dark:text-slate-400">
                        Department-specific review is completed in the Department Workspace checklist. These are staff checks with evidence references, not automatic SHA adjudication rules.
                      </p>}
                    </div>
                  </div>

                  <section className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950 p-4 space-y-3">
                    <div>
                      <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-200">Claims officer review</h3>
                      <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">Record that a staff member reviewed this saved claim version. The typed name is not verified against a staff account.</p>
                    </div>
                    <div className="flex flex-wrap items-end gap-3">
                      <label className="min-w-[180px] flex-1 text-xs font-semibold text-slate-600 dark:text-slate-400">
                        Reviewer name
                        <input value={privacyMode && officerName ? "********" : officerName} readOnly={privacyMode} onChange={(event) => setOfficerName(event.target.value)} className="mt-1.5 w-full rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-2.5 text-sm font-normal text-slate-700 dark:text-slate-200" placeholder="Name of claims officer" />
                      </label>
                      <label className="text-xs font-semibold text-slate-600 dark:text-slate-400">
                        Review outcome
                        <select value={officerDecision} onChange={(event) => setOfficerDecision(event.target.value)} className="mt-1.5 block rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-2.5 text-sm font-normal text-slate-700 dark:text-slate-200">
                          <option value="reviewed">Reviewed</option>
                          <option value="correction_requested">Correction requested</option>
                        </select>
                      </label>
                      <button type="button" onClick={handleOfficerReview} disabled={!officerName.trim() || hasEdits || officerReviewState === "saving"} className="rounded-lg bg-slate-800 px-4 py-2.5 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50">
                        {officerReviewState === "saving" ? "Recording…" : "Record review"}
                      </button>
                    </div>
                    {officerReviewState === "saved" && <p className="text-xs text-emerald-700 dark:text-emerald-400">Officer review recorded against this saved claim version.</p>}
                    {officerReviewError && <p role="alert" className="text-xs text-red-600 dark:text-red-400">{officerReviewError}</p>}
                  </section>

                  <div className="flex flex-wrap items-center gap-3 pt-2 bg-slate-50/50 dark:bg-slate-900/50 sticky bottom-0 z-10 py-4 border-t border-slate-200/50 dark:border-slate-850">
                    {hasEdits && (
                      <p className="w-full text-xs text-amber-700 dark:text-amber-400">
                        Corrections are not saved yet. Re-validate with the backend before submitting this claim version.
                      </p>
                    )}
                    {hasEdits && (
                      <button
                        type="button"
                        onClick={handleRevalidate}
                        className="flex-1 bg-slate-800 hover:bg-slate-900 dark:bg-slate-700 dark:hover:bg-slate-600 active:scale-95 text-white font-semibold text-sm py-3 rounded-xl transition-all shadow-md"
                      >
                        Re-validate with corrections
                      </button>
                    )}

                    <button
                      type="button"
                      onClick={submit}
                      disabled={!canSubmit || overallStatus.status !== "green" || state === "submitting"}
                      className={`flex-1 text-white font-semibold text-sm py-3 rounded-xl transition-all shadow-md active:scale-95 ${
                        canSubmit
                          ? "bg-teal-600 hover:bg-teal-700 cursor-pointer"
                          : "bg-slate-300 dark:bg-slate-800 cursor-not-allowed opacity-70"
                      }`}
                    >
                      {state === "submitting" ? "Submitting..." : "Submit claim →"}
                    </button>

                    <button
                      type="button"
                      onClick={reset}
                      className="px-5 py-3 border border-slate-200 dark:border-slate-800 rounded-xl text-sm font-semibold text-slate-600 dark:text-slate-400 bg-white dark:bg-slate-950 hover:bg-slate-50 dark:hover:bg-slate-900 active:scale-95 transition-all"
                    >
                      Reset
                    </button>
                  </div>
                </>
              )}
            </div>
          )}

          {activeTab === "Claim details" && (
            <div className="bg-white dark:bg-slate-950 border border-slate-200/80 dark:border-slate-850 rounded-2xl p-6 shadow-sm space-y-6">
              <h3 className="text-sm font-bold text-slate-800 dark:text-slate-200 border-b border-slate-100 dark:border-slate-850 pb-3">Patient Profile & Coverage</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-4 text-sm">
                <div>
                  <span className="text-xs text-slate-400 dark:text-slate-500 block">Full Name</span>
                  <span className="font-semibold text-slate-800 dark:text-slate-200">{privateValue(claim.patient_name)}</span>
                </div>
                <div>
                  <span className="text-xs text-slate-400 dark:text-slate-500 block">Policy ID Number</span>
                  <span className="font-semibold text-slate-800 dark:text-slate-200 font-mono">{privateValue(edits.patient_id ?? claim.patient_id)}</span>
                </div>
                <div>
                  <span className="text-xs text-slate-400 dark:text-slate-500 block">Policy Expiry / Coverage End Date</span>
                  <span className="font-semibold text-slate-800 dark:text-slate-200 font-mono">{privateValue(edits.coverage_end_date ?? claim.coverage_end_date)}</span>
                </div>
                <div>
                  <span className="text-xs text-slate-400 dark:text-slate-500 block">Insurance Scheme</span>
                  <span className="font-semibold text-slate-800 dark:text-slate-200">{privateValue("State Health Authority (SHA)")}</span>
                </div>
                <div>
                  <span className="text-xs text-slate-400 dark:text-slate-500 block">Coverage Status</span>
                  <span className="text-emerald-700 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-950/20 border border-emerald-100 dark:border-emerald-900/30 rounded-full px-2.5 py-0.5 text-xs font-semibold inline-block mt-1">
                    {privateValue("Active")}
                  </span>
                </div>
              </div>
            </div>
          )}

          {activeTab === "Claim details" && (
            <div className="bg-white dark:bg-slate-950 border border-slate-200/80 dark:border-slate-850 rounded-2xl p-6 shadow-sm space-y-6">
              <h3 className="text-sm font-bold text-slate-800 dark:text-slate-200 border-b border-slate-100 dark:border-slate-850 pb-3">Claim Details & Items</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-4 text-sm">
                <div>
                  <span className="text-xs text-slate-400 dark:text-slate-500 block">Claim ID</span>
                  <span className="font-semibold text-slate-800 dark:text-slate-200 font-mono">{privateValue(claim.id)}</span>
                </div>
                <div>
                  <span className="text-xs text-slate-400 dark:text-slate-500 block">Visit Date</span>
                  <span className="font-semibold text-slate-800 dark:text-slate-200 font-mono">{privateValue(edits.visit_date ?? claim.visit_date)}</span>
                </div>
                <div>
                  <span className="text-xs text-slate-400 dark:text-slate-500 block">Facility Name</span>
                  <span className="font-semibold text-slate-800 dark:text-slate-200">{claim.facility_name}</span>
                </div>
                <div>
                  <span className="text-xs text-slate-400 dark:text-slate-500 block">Admitting Diagnosis Code</span>
                  <span className="font-semibold text-slate-850 dark:text-slate-200 font-mono bg-slate-50 dark:bg-slate-900 border border-slate-100 dark:border-slate-800 rounded px-1">{privateValue(edits.diagnosis_code ?? claim.diagnosis_code)}</span>
                </div>
                <div>
                  <span className="text-xs text-slate-400 dark:text-slate-500 block">Diagnosis Description</span>
                  <span className="font-medium text-slate-700 dark:text-slate-300">{privateValue(claim.diagnosis_description)}</span>
                </div>
                <div>
                  <span className="text-xs text-slate-400 dark:text-slate-500 block">Total Claimed Amount</span>
                  <span className="font-extrabold text-slate-800 dark:text-slate-200">{privacyMode ? "********" : `KES ${Number(edits.claimed_amount ?? claim.claimed_amount).toLocaleString()}`}</span>
                </div>
              </div>

              <div className="mt-6 border-t border-slate-100 dark:border-slate-850 pt-5">
                <h4 className="text-xs font-bold text-slate-400 dark:text-slate-500 uppercase tracking-widest mb-3">Service Items Grid</h4>
                <div className="border border-slate-200/60 dark:border-slate-800 rounded-xl overflow-hidden text-xs">
                  <table className="w-full text-left">
                    <thead className="bg-slate-50 dark:bg-slate-900 border-b border-slate-200 dark:border-slate-800 text-slate-500 dark:text-slate-400 font-bold uppercase tracking-wider">
                      <tr>
                        <th className="p-3">Service Description</th>
                        <th className="p-3 text-right">Price (KES)</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 dark:divide-slate-850 text-slate-700 dark:text-slate-350">
                      <tr>
                        <td className="p-3">{privateValue("Standard Clinical Consultation Fee")}</td>
                        <td className="p-3 text-right font-medium">{privateValue("1,500")}</td>
                      </tr>
                      <tr>
                        <td className="p-3">{privateValue("Laboratory Investigation Panel (ICD Alignment Check)")}</td>
                        <td className="p-3 text-right font-medium">{privateValue("2,000")}</td>
                      </tr>
                      {Number(edits.claimed_amount ?? claim.claimed_amount) > 3500 && (
                        <tr>
                          <td className="p-3">{privateValue("Prescription Dispensation & Therapeutics")}</td>
                          <td className="p-3 text-right font-medium">
                            {privacyMode ? "********" : (Number(edits.claimed_amount ?? claim.claimed_amount) - 3500).toLocaleString()}
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {activeTab === "Technical" && (
            <div className="bg-white dark:bg-slate-950 border border-slate-200/80 dark:border-slate-850 rounded-2xl p-6 shadow-sm">
              <h3 className="text-sm font-bold text-slate-800 dark:text-slate-200 border-b border-slate-100 dark:border-slate-850 pb-3 mb-4">Technical details</h3>
              <details>
                <summary className="cursor-pointer text-sm font-semibold text-slate-600 dark:text-slate-300">FHIR-style preview (FHIR R4 ClaimResponse)</summary>
                <div className="pt-4">
                  {validation?.fhir_claim_response ? (
                    <pre className="text-xs text-slate-700 dark:text-slate-350 bg-slate-900 dark:bg-slate-950 border border-slate-800 dark:border-slate-850 rounded-xl p-4 overflow-auto font-mono text-emerald-400 dark:text-emerald-550 max-h-[450px]">
                      {JSON.stringify(privacyMode ? "********" : maskFhirPayload(validation.fhir_claim_response), null, 2)}
                    </pre>
                  ) : (
                    <div className="text-center py-10 text-slate-400 dark:text-slate-500 text-sm font-medium">
                      Please validate the claim first to compile the FHIR JSON schema.
                    </div>
                  )}
                </div>
              </details>
            </div>
          )}

          {activeTab === "Audit Trail" && (
            <AuditTrailTab claimId={claim.id} privacyMode={privacyMode} />
          )}

          {activeTab === "Department Workspace" && (
            <DeptGuideTab claimId={claim.id} department={claim.department} privacyMode={privacyMode} />
          )}
          {activeTab === "Outcome Feedback" && (
            <OutcomeFeedbackTab claim={claim} privacyMode={privacyMode} />
          )}
        </div>
      </div>

      {/* Right Edge: Persistent Timeline Tracker */}
      <div className="w-52 2xl:w-64 border-l border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950 flex flex-col flex-shrink-0 p-4 2xl:p-5">
        <h3 className="text-xs font-bold text-slate-400 dark:text-slate-500 uppercase tracking-widest mb-6 mt-1">Status Timeline</h3>
        <div className="relative pl-6 space-y-8 flex-1">
          <div className="absolute left-[30px] top-2 bottom-6 w-0.5 bg-slate-200 dark:bg-slate-800" />

          <div className="relative flex gap-3.5 items-start">
            <span className={`absolute left-0 w-3 h-3 rounded-full border-2 transform -translate-x-1.5 mt-1.5 transition-all duration-300 ${
              activeStep >= 0 ? "bg-teal-500 border-teal-500 scale-110 shadow-sm shadow-teal-500/50" : "bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-700"
            }`} />
            <div className="pl-3.5">
              <p className={`text-xs font-bold ${activeStep >= 0 ? "text-slate-800 dark:text-slate-200" : "text-slate-400 dark:text-slate-550"}`}>Claim Received</p>
              <p className="text-[10px] text-slate-400 dark:text-slate-500 mt-0.5">Registered in system</p>
            </div>
          </div>

          <div className="relative flex gap-3.5 items-start">
            <span className={`absolute left-0 w-3 h-3 rounded-full border-2 transform -translate-x-1.5 mt-1.5 transition-all duration-300 ${
              activeStep >= 1 ? "bg-teal-500 border-teal-500 scale-110 shadow-sm shadow-teal-500/50" : "bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-700"
            }`} />
            <div className="pl-3.5">
              <p className={`text-xs font-bold ${activeStep >= 1 ? "text-slate-800 dark:text-slate-200" : "text-slate-400 dark:text-slate-550"}`}>Claim checks</p>
              <p className="text-[10px] text-slate-400 dark:text-slate-500 mt-0.5">Rule checks with Gemini explanations</p>
            </div>
          </div>

          <div className="relative flex gap-3.5 items-start">
            <span className={`absolute left-0 w-3 h-3 rounded-full border-2 transform -translate-x-1.5 mt-1.5 transition-all duration-300 ${
              activeStep >= 2 ? "bg-teal-500 border-teal-500 scale-110 shadow-sm shadow-teal-500/50" : "bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-700"
            }`} />
            <div className="pl-3.5">
              <p className={`text-xs font-bold ${activeStep >= 2 ? "text-slate-800 dark:text-slate-200" : "text-slate-400 dark:text-slate-550"}`}>Pending Corrections</p>
              <p className="text-[10px] text-slate-400 dark:text-slate-500 mt-0.5">Live officer triage</p>
            </div>
          </div>

          <div className="relative flex gap-3.5 items-start">
            <span className={`absolute left-0 w-3 h-3 rounded-full border-2 transform -translate-x-1.5 mt-1.5 transition-all duration-300 ${
              activeStep >= 3 ? "bg-emerald-500 border-emerald-500 scale-110 shadow-sm shadow-emerald-500/50" : "bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-700"
            }`} />
            <div className="pl-3.5">
              <p className={`text-xs font-bold ${activeStep >= 3 ? "text-slate-800 dark:text-slate-200" : "text-slate-400 dark:text-slate-550"}`}>Ready to submit</p>
              <p className="text-[10px] text-slate-400 dark:text-slate-500 mt-0.5">Submission depends on connection mode</p>
            </div>
          </div>
        </div>

        <div className="border-t border-slate-100 dark:border-slate-850 pt-4 text-[10px] text-slate-400 dark:text-slate-500">
          <span className="font-semibold block text-slate-500 dark:text-slate-400">Validation Mode:</span>
          <span>Rule checks + Gemini explanations</span>
        </div>
      </div>
    </div>
  );
}

ValidationPanel.propTypes = {
  claim: PropTypes.shape({
    id: PropTypes.string.isRequired,
    patient_name: PropTypes.string,
    facility_name: PropTypes.string,
    visit_date: PropTypes.string,
    diagnosis_code: PropTypes.string,
    diagnosis_description: PropTypes.string,
    patient_id: PropTypes.string,
    coverage_end_date: PropTypes.string,
    claimed_amount: PropTypes.oneOfType([PropTypes.string, PropTypes.number]),
    department: PropTypes.string,
  }),
  onValidationComplete: PropTypes.func,
  privacyMode: PropTypes.bool,
};
