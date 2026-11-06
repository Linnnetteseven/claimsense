import { useState, useEffect, useMemo } from "react";
import PropTypes from "prop-types";
import ScoreGauge from "./ScoreGauge.jsx";
import StatusBadge from "./StatusBadge.jsx";
import ErrorCard from "./ErrorCard.jsx";
import { SpinnerIcon } from "./icons.jsx";
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
export default function ValidationPanel({ claim, onValidationComplete, onLifecycleChange, onLocalEdit, privacyMode = false, departmentsEnabled = true }) {
  const [lifecycle, setLifecycle] = useState(() => claim?._lifecycle || {});
  const [correctionReason, setCorrectionReason] = useState("");
  const [correctionMode, setCorrectionMode] = useState(false);
  const [correctionBusy, setCorrectionBusy] = useState(false);
  const [recheckBusy, setRecheckBusy] = useState(false);
  const [recheckResult, setRecheckResult] = useState(null);
  const [outcomeSaved, setOutcomeSaved] = useState(null);
  const [lifecycleError, setLifecycleError] = useState("");
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
  } = useClaimValidation(claim, onValidationComplete, onLifecycleChange);

  const isSubmitted = String(lifecycle.status || "").toLowerCase() === "submitted" && !correctionMode;
  const isStale = String(lifecycle.status || "").toLowerCase() === "needs_revalidation";

  useEffect(() => {
    console.log("ValidationPanel - Current State:", state);
    console.log("ValidationPanel - Validation Data:", privacyMode ? "********" : validation);
  }, [state, validation, privacyMode]);

  useEffect(() => {
    setDepartmentReview(claim ? readDepartmentReview(claim.id, claim.department) : null);
  }, [claim]);

  useEffect(() => {
    if (validation?.lifecycle) setLifecycle(validation.lifecycle);
  }, [validation?.lifecycle]);

  useEffect(() => {
    setLifecycle(claim?._lifecycle || {});
    setCorrectionMode(false);
    setCorrectionReason("");
    setRecheckResult(null);
  }, [claim?.id, claim?._lifecycle]);

  useEffect(() => {
    const refreshDepartmentReview = (event) => {
      const { claimId, department: reviewDepartment } = event.detail || {};
      if (claimId === claim?.id && reviewDepartment === (claim?.department || "").toLowerCase()) {
        setDepartmentReview(readDepartmentReview(claim.id, claim.department));
        if (String(lifecycle.status || "").toLowerCase() !== "submitted") {
          setLifecycle((current) => ({ ...current, status: "needs_revalidation" }));
          onLocalEdit?.(claim.id);
        }
      }
    };
    window.addEventListener(DEPARTMENT_REVIEW_UPDATED, refreshDepartmentReview);
    return () => window.removeEventListener(DEPARTMENT_REVIEW_UPDATED, refreshDepartmentReview);
  }, [claim, lifecycle.status, onLocalEdit]);

  const [activeTab, setActiveTab] = useState("Checks");
  const overallStatus = useMemo(() => getOverallStatus(
    { ...(validation || claim?._preview || {}), department: claim?.department },
    departmentReview,
  ), [claim, validation, departmentReview]);
  const displayedStatus = (hasEdits || isStale) && !isSubmitted
    ? { status: "amber", label: "Needs revalidation", reason: "Unsaved edits must be validated before submission." }
    : isSubmitted
      ? { status: "green", label: "Submitted, locked", reason: "This submitted version is locked." }
      : overallStatus;
  const correctionAvailable = ["returned", "rejected"].includes(
    String(outcomeSaved?.outcome || lifecycle.latest_outcome || "").toLowerCase(),
  ) || Boolean(correctionReason.trim());
  const overallChecks = validation?.results?.filter((result) => OVERALL_RULE_IDS.has(result.rule_id)) || [];
  const departmentChecks = validation?.results?.filter((result) => (DEPARTMENT_RULE_IDS[claim?.department] || []).includes(result.rule_id)) || [];
  const tabs = departmentsEnabled ? ["Checks", "Details", "Departments", "Audit", "Outcome"] : ["Checks", "Details", "Audit", "Outcome"];

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
    if (isSubmitted) return;
    setOfficerReviewState("idle");
    editField(field, value);
    onLocalEdit?.(claim.id);
  };

  const handleRevalidate = () => {
    if (isSubmitted) return;
    setOfficerReviewState("idle");
    return revalidateWithEdits();
  };

  const handleReadOnlyRecheck = async () => {
    setRecheckBusy(true);
    setLifecycleError("");
    try {
      const response = await api.recheckClaim(claim.id);
      setRecheckResult(response.validation);
    } catch (recheckError) {
      setLifecycleError(recheckError.message || "Read-only re-check failed.");
    } finally {
      setRecheckBusy(false);
    }
  };

  const handleCreateCorrection = async () => {
    setCorrectionBusy(true);
    setLifecycleError("");
    try {
      const response = await api.startCorrection(claim.id, correctionReason);
      setLifecycle(response.lifecycle || response.correction);
      setCorrectionMode(true);
      setCorrectionReason("");
      setRecheckResult(null);
      reset();
      onLifecycleChange?.(claim.id, response.lifecycle || response.correction, response.correction?.claim);
    } catch (correctionError) {
      setLifecycleError(correctionError.message || "Could not create a correction version.");
    } finally {
      setCorrectionBusy(false);
    }
  };

  const handleOutcomeSaved = (record) => {
    setOutcomeSaved(record);
    const normalized = String(record?.outcome || "").toLowerCase();
    if (["returned", "rejected"].includes(normalized)) {
      setLifecycle((current) => ({ ...current, latest_outcome: normalized, latest_outcome_reason: record.reasonCategory }));
    }
  };

  const handleSubmit = async () => {
    const result = await submit();
    if (result?.lifecycle) setLifecycle(result.lifecycle);
  };

  // Document scan simulation state
  const [scanState, setScanState] = useState("idle"); // "idle" | "scanning" | "done"
  const [scanExpanded, setScanExpanded] = useState(false);
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
      <div className="flex flex-col items-center justify-center h-full text-slate-500 dark:text-slate-400 p-8 text-center bg-slate-50/50 dark:bg-slate-900/30">
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
  } else if (isSubmitted || state === "submitted" || state === "submitting") {
    activeStep = 3;
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
                  <StatusBadge status={displayedStatus.label} color={displayedStatus.status} small />
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
              <span className="text-[10px] text-slate-500 dark:text-slate-400 font-bold uppercase tracking-wider">Policy/Visit Date</span>
              <span className="text-sm font-semibold text-slate-700 dark:text-slate-300">{privateValue(claim.visit_date)}</span>
            </div>
          </div>
        </div>

        {/* Compact workflow stepper */}
        <ol aria-label="Claim workflow progress" className="grid shrink-0 grid-cols-4 gap-2 border-b border-slate-200 bg-white px-4 py-2.5 text-[10px] sm:text-xs dark:border-slate-800 dark:bg-slate-950">
          {["Received", "Checks", "Corrections", "Ready"].map((step, index) => (
            <li key={step} className={`flex min-w-0 items-center gap-1.5 ${activeStep >= index ? "font-semibold text-slate-900 dark:text-slate-100" : "text-slate-600 dark:text-slate-400"}`}>
              <span aria-hidden="true" className={`h-2 w-2 shrink-0 rounded-full ${index === 3 && activeStep >= index ? "bg-teal-700 dark:bg-teal-400" : activeStep >= index ? "bg-teal-700 dark:bg-teal-400" : "border border-slate-500 dark:border-slate-400"}`} />
              <span className="truncate">{step}</span>
            </li>
          ))}
        </ol>

        {/* Five primary workflow tabs */}
        <div className="bg-white dark:bg-slate-950 border-b border-slate-200 dark:border-slate-850 px-4 flex-shrink-0">
          <nav className="grid grid-cols-5 gap-1" aria-label="Claim sections">
            {tabs.map((tab) => {
              const isActive = activeTab === tab;
              return (
                <button
                  key={tab}
                  type="button"
                  onClick={() => setActiveTab(tab)}
                  className={`min-w-0 rounded-t px-1 py-2.5 font-semibold text-[10px] sm:text-xs leading-tight text-center border-b-2 transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-teal-700 ${
                    isActive
                      ? "border-teal-800 text-teal-900 dark:border-teal-400 dark:text-teal-200"
                      : "border-transparent text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800"
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

          {activeTab === "Checks" && (
            <div className="flex flex-col gap-5">
              <button type="button" onClick={() => setScanExpanded((open) => !open)} aria-expanded={scanExpanded} className="order-2 flex w-full items-center justify-between rounded-lg border border-slate-300 bg-white px-4 py-3 text-left text-sm font-semibold text-slate-800 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-teal-700 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100 dark:hover:bg-slate-900">
                <span>Scan claim invoice or document <span className="font-normal text-slate-600 dark:text-slate-300">· optional, OCR simulated</span></span><span aria-hidden="true">{scanExpanded ? "−" : "+"}</span>
              </button>
              {scanExpanded && <div className="order-2 rounded-lg border border-slate-300 bg-white p-4 dark:border-slate-700 dark:bg-slate-950">
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
                    <span className="text-[10px] text-slate-500 dark:text-slate-400 mt-1">PDF, JPG, PNG (Max 5MB)</span>
                    <input type="file" className="hidden" accept=".pdf,.png,.jpg,.jpeg" onChange={handleFileUpload} />
                  </label>
                )}

                {scanState === "scanning" && (
                  <div className="border border-slate-100 dark:border-slate-800 rounded-xl p-5 flex flex-col items-center justify-center bg-slate-50 dark:bg-slate-900/60 relative overflow-hidden">
                    <div className="absolute top-0 left-0 right-0 h-0.5 bg-gradient-to-r from-teal-400 to-emerald-500 animate-[pulse_1.5s_infinite] shadow-lg shadow-teal-500" />
                    <SpinnerIcon className="w-8 h-8 text-teal-600 mb-2" />
                    <p className="text-xs font-semibold text-slate-700 dark:text-slate-200">Preparing sample extraction...</p>
                    <p className="text-[10px] text-slate-500 dark:text-slate-400 mt-1">Simulated OCR; no OCR service is connected.</p>
                  </div>
                )}

                {scanState === "done" && (
                  <div className="border border-teal-100 dark:border-teal-900/30 rounded-xl p-4 bg-teal-50/20 dark:bg-teal-950/10">
                    <div className="flex items-center justify-between mb-3">
                      <span className="text-xs font-bold text-teal-800 dark:text-teal-400 flex items-center gap-1.5">
                        <span className="w-2 h-2 rounded-full bg-teal-500" />
                        Sample extraction ready
                      </span>
                      <span className="text-[10px] text-slate-500 dark:text-slate-400">Simulated OCR</span>
                    </div>
                    <div className="grid grid-cols-2 gap-3 mb-4 bg-white dark:bg-slate-950 p-3 rounded-lg border border-slate-100 dark:border-slate-850 text-xs">
                      <div>
                        <span className="text-slate-500 dark:text-slate-400 block mb-0.5">ICD-10 Diagnosis</span>
                        <strong className="text-slate-700 dark:text-slate-200 font-semibold">{privateValue(`${extractedData.diagnosis_code} - ${extractedData.diagnosis_description}`)}</strong>
                      </div>
                      <div>
                        <span className="text-slate-500 dark:text-slate-400 block mb-0.5">Visit Date</span>
                        <strong className="text-slate-700 dark:text-slate-200 font-semibold">{privateValue(extractedData.visit_date)}</strong>
                      </div>
                      <div>
                        <span className="text-slate-500 dark:text-slate-400 block mb-0.5">Claimed Amount</span>
                        <strong className="text-slate-700 dark:text-slate-200 font-semibold">{privacyMode ? "********" : `KES ${extractedData.claimed_amount.toLocaleString()}`}</strong>
                      </div>
                    </div>

                    <div className="flex gap-2.5">
                      <button
                        type="button"
                        onClick={applyExtractedData}
                        className="bg-teal-700 hover:bg-teal-800 text-white font-semibold text-xs px-3.5 py-2 rounded-lg shadow-sm transition-all"
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
                        <p className="text-[10px] text-slate-500 dark:text-slate-400 mt-0.5">Click &quot;Re-validate with corrections&quot; below to recheck rules.</p>
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
              </div>}

              {isSubmitted && (
                <section className="order-1 space-y-4 rounded-lg border border-slate-300 bg-white p-5 dark:border-slate-700 dark:bg-slate-950" aria-label="Submitted claim lock">
                  <div>
                    <h3 className="text-base font-bold text-slate-900 dark:text-slate-100">Submitted, locked</h3>
                    <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
                      Submitted version {lifecycle.version ?? "unknown"}. Its fingerprint is recorded with the submission event.
                    </p>
                    <code className="mt-2 block break-all text-xs text-slate-600 dark:text-slate-300">{lifecycle.version_fingerprint || "Fingerprint unavailable"}</code>
                    {submitResult && <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">{submitResult.mode === "mock" ? "Demo submission; no live payer received the claim." : "Sent through the configured openIMIS connection."}</p>}
                  </div>
                  {lifecycleError && <p role="alert" className="text-sm text-red-700 dark:text-red-400">{lifecycleError}</p>}
                  <div className="flex flex-wrap gap-2">
                    <button type="button" onClick={handleReadOnlyRecheck} disabled={recheckBusy} className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-800 disabled:opacity-60 dark:border-slate-700 dark:text-slate-100">
                      {recheckBusy ? "Checking…" : "Re-check against current rules (read-only)"}
                    </button>
                  </div>
                  {recheckResult && <div role="status" className="rounded-md bg-slate-100 p-3 text-sm dark:bg-slate-900">Informational result for submitted version {recheckResult.version}: {recheckResult.status} · score {recheckResult.score}/100. Claim remains locked.</div>}
                  <div className="grid gap-2 sm:grid-cols-[1fr_auto]">
                    <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                      Correction reason (required unless outcome is Returned or Rejected)
                      <input value={correctionReason} onChange={(event) => setCorrectionReason(event.target.value)} maxLength={500} className="mt-1.5 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-normal dark:border-slate-700 dark:bg-slate-900" placeholder="Explain why a correction version is needed" />
                    </label>
                    <button type="button" onClick={handleCreateCorrection} disabled={correctionBusy || !correctionAvailable} className="self-end rounded-lg bg-teal-700 px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50">
                      {correctionBusy ? "Creating…" : "Create correction version"}
                    </button>
                  </div>
                </section>
              )}

              {!isSubmitted && state === "idle" && (
                <div className="order-1 bg-white dark:bg-slate-950 border border-slate-200/80 dark:border-slate-850 rounded-2xl p-6 text-center shadow-sm">
                  <p className="text-slate-500 dark:text-slate-300 text-sm mb-4 font-medium">
                    This claim needs validation against SHA pre-submission policies.
                  </p>
                  <button
                    type="button"
                    onClick={validate}
                    className="bg-teal-700 text-white px-6 py-2.5 rounded-xl text-sm font-semibold hover:bg-teal-800 active:scale-95 transition-all shadow-sm"
                  >
                    Validate Claim
                  </button>
                </div>
              )}

              {state === "loading" && (
                <div className="order-1 bg-white dark:bg-slate-950 border border-slate-200/80 dark:border-slate-850 rounded-2xl p-10 flex flex-col items-center justify-center shadow-sm">
                  <SpinnerIcon />
                  <p className="text-sm font-semibold text-slate-700 dark:text-slate-200 mt-3">Running claim checks...</p>
                  <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">Generating plain English rule interpretations</p>
                </div>
              )}

              {!isSubmitted && (state === "results" || state === "submitting") && validation && (
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
                          <span className="text-[10px] text-slate-500 dark:text-slate-400 uppercase block">Diagnosis</span>
                          <span className="text-slate-800 dark:text-slate-200 font-semibold">{edits.diagnosis_code ?? claim.diagnosis_code} — {privateValue(claim.diagnosis_description)}</span>
                        </div>
                        <div>
                          <span className="text-[10px] text-slate-500 dark:text-slate-400 uppercase block">Claimed Amount</span>
                          <span className="text-slate-800 dark:text-slate-200 font-semibold">{privacyMode ? "********" : `KES ${Number(edits.claimed_amount ?? claim.claimed_amount).toLocaleString()}`}</span>
                        </div>
                      </div>
                    </div>
                  </div>

                  <div>
                    <h3 className="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-widest mb-3">
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
                    <h3 className="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-widest mt-6 mb-3">
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
                      <button type="button" onClick={handleOfficerReview} disabled={isSubmitted || !officerName.trim() || hasEdits || officerReviewState === "saving"} className="rounded-lg bg-slate-800 px-4 py-2.5 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50">
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

                    {isStale && !hasEdits && !isSubmitted && (
                      <button type="button" onClick={validate} disabled={state === "loading"} className="flex-1 rounded-xl bg-teal-700 py-3 text-sm font-semibold text-white disabled:opacity-60">
                        {state === "loading" ? "Revalidating…" : "Revalidate current claim"}
                      </button>
                    )}

                    <button
                      type="button"
                        onClick={handleSubmit}
                      disabled={isSubmitted || isStale || !canSubmit || overallStatus.status !== "green" || state === "submitting"}
                      className={`flex-1 text-white font-semibold text-sm py-3 rounded-xl transition-all shadow-md active:scale-95 ${
                        canSubmit
                          ? "bg-teal-700 hover:bg-teal-800 cursor-pointer"
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

          {activeTab === "Details" && (
            <div className="bg-white dark:bg-slate-950 border border-slate-200/80 dark:border-slate-850 rounded-2xl p-6 shadow-sm space-y-6">
              <h3 className="text-sm font-bold text-slate-800 dark:text-slate-200 border-b border-slate-100 dark:border-slate-850 pb-3">Patient Profile & Coverage</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-4 text-sm">
                <div>
                  <span className="text-xs text-slate-500 dark:text-slate-400 block">Full Name</span>
                  <span className="font-semibold text-slate-800 dark:text-slate-200">{privateValue(claim.patient_name)}</span>
                </div>
                <div>
                  <span className="text-xs text-slate-500 dark:text-slate-400 block">Policy ID Number</span>
                  <span className="font-semibold text-slate-800 dark:text-slate-200 font-mono">{privateValue(edits.patient_id ?? claim.patient_id)}</span>
                </div>
                <div>
                  <span className="text-xs text-slate-500 dark:text-slate-400 block">Policy Expiry / Coverage End Date</span>
                  <span className="font-semibold text-slate-800 dark:text-slate-200 font-mono">{privateValue(edits.coverage_end_date ?? claim.coverage_end_date)}</span>
                </div>
                <div>
                  <span className="text-xs text-slate-500 dark:text-slate-400 block">Insurance Scheme</span>
                  <span className="font-semibold text-slate-800 dark:text-slate-200">{privateValue("State Health Authority (SHA)")}</span>
                </div>
                <div>
                  <span className="text-xs text-slate-500 dark:text-slate-400 block">Coverage Status</span>
                  <span className="text-emerald-700 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-950/20 border border-emerald-100 dark:border-emerald-900/30 rounded-full px-2.5 py-0.5 text-xs font-semibold inline-block mt-1">
                    {privateValue("Active")}
                  </span>
                </div>
              </div>
            </div>
          )}

          {activeTab === "Details" && (
            <div className="bg-white dark:bg-slate-950 border border-slate-200/80 dark:border-slate-850 rounded-2xl p-6 shadow-sm space-y-6">
              <h3 className="text-sm font-bold text-slate-800 dark:text-slate-200 border-b border-slate-100 dark:border-slate-850 pb-3">Claim Details & Items</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-4 text-sm">
                <div>
                  <span className="text-xs text-slate-500 dark:text-slate-400 block">Claim ID</span>
                  <span className="font-semibold text-slate-800 dark:text-slate-200 font-mono">{privateValue(claim.id)}</span>
                </div>
                <div>
                  <span className="text-xs text-slate-500 dark:text-slate-400 block">Visit Date</span>
                  <span className="font-semibold text-slate-800 dark:text-slate-200 font-mono">{privateValue(edits.visit_date ?? claim.visit_date)}</span>
                </div>
                <div>
                  <span className="text-xs text-slate-500 dark:text-slate-400 block">Facility Name</span>
                  <span className="font-semibold text-slate-800 dark:text-slate-200">{claim.facility_name}</span>
                </div>
                <div>
                  <span className="text-xs text-slate-500 dark:text-slate-400 block">Admitting Diagnosis Code</span>
                  <span className="font-semibold text-slate-850 dark:text-slate-200 font-mono bg-slate-50 dark:bg-slate-900 border border-slate-100 dark:border-slate-800 rounded px-1">{privateValue(edits.diagnosis_code ?? claim.diagnosis_code)}</span>
                </div>
                <div>
                  <span className="text-xs text-slate-500 dark:text-slate-400 block">Diagnosis Description</span>
                  <span className="font-medium text-slate-700 dark:text-slate-300">{privateValue(claim.diagnosis_description)}</span>
                </div>
                <div>
                  <span className="text-xs text-slate-500 dark:text-slate-400 block">Total Claimed Amount</span>
                  <span className="font-extrabold text-slate-800 dark:text-slate-200">{privacyMode ? "********" : `KES ${Number(edits.claimed_amount ?? claim.claimed_amount).toLocaleString()}`}</span>
                </div>
              </div>

              <div className="mt-6 border-t border-slate-100 dark:border-slate-850 pt-5">
                <h4 className="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-widest mb-3">Service Items Grid</h4>
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

          {activeTab === "Details" && (
            <details className="rounded-lg border border-slate-300 bg-white px-4 py-3 dark:border-slate-700 dark:bg-slate-950">
              <summary className="cursor-pointer text-sm font-semibold text-slate-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-teal-700 dark:text-slate-100">Technical details · FHIR-style preview</summary>
              <div className="pt-4">
                {validation?.fhir_claim_response ? (
                  <pre className="max-h-[450px] overflow-auto rounded-md bg-slate-900 p-4 font-mono text-xs text-teal-300">
                    {JSON.stringify(privacyMode ? "********" : maskFhirPayload(validation.fhir_claim_response), null, 2)}
                  </pre>
                ) : <p className="py-5 text-sm text-slate-600 dark:text-slate-300">Validate the claim first to generate its FHIR-shaped preview.</p>}
              </div>
            </details>
          )}

          {activeTab === "Audit" && (
            <AuditTrailTab claimId={claim.id} privacyMode={privacyMode} />
          )}

          {departmentsEnabled && activeTab === "Departments" && (
            <DeptGuideTab claimId={claim.id} department={claim.department} privacyMode={privacyMode} readOnly={isSubmitted} />
          )}
          {activeTab === "Outcome" && (
            <OutcomeFeedbackTab claim={claim} privacyMode={privacyMode} onOutcomeSaved={handleOutcomeSaved} />
          )}
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
  onLifecycleChange: PropTypes.func,
  onLocalEdit: PropTypes.func,
  privacyMode: PropTypes.bool,
};
