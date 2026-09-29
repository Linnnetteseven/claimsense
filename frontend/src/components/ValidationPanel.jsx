import { useState, useEffect } from "react";
import PropTypes from "prop-types";
import ScoreGauge from "./ScoreGauge.jsx";
import StatusBadge from "./StatusBadge.jsx";
import ErrorCard from "./ErrorCard.jsx";
import { CheckIcon, SpinnerIcon } from "./icons.jsx";
import { useClaimValidation } from "../hooks/useClaimValidation.js";
import AuditTrailTab from "./AuditTrailTab.jsx";
import DeptGuideTab from "./DeptGuideTab.jsx";
import ShaStateBadge from "./ShaStateBadge.jsx";
import { ClaimInfo, PatientDetails } from "./ClaimDetails.jsx";
import { tabForField } from "../constants/claimFields.js";
import { stageOf } from "../constants/stages.js";

/**
 * Main right workspace: patient profile header, tabbed details (Demographics, Claim Info, AI Validation, FHIR Preview),
 * status timeline on the right edge, document upload/scan simulation, and action buttons.
 */
export default function ValidationPanel({ claim, onValidationComplete }) {
  if (!claim) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-slate-500 dark:text-slate-400 p-8 text-center bg-slate-50/50 dark:bg-slate-900/30">
        <svg className="w-12 h-12 mb-4 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01" /></svg>
        <p className="text-sm font-medium">Select a claim from the queue to start validation.</p>
      </div>
    );
  }
  return <ClaimWorkspace claim={claim} onValidationComplete={onValidationComplete} />;
}

// Split from ValidationPanel so hooks never run conditionally.
function ClaimWorkspace({ claim, onValidationComplete }) {
  const {
    state,
    validation,
    edits,
    error,
    submitResult,
    currentClaim,
    hasEdits,
    canSubmit,
    validate,
    editField,
    discardEdits,
    saveCorrections,
    applyFix,
    restoreOriginal,
    submit,
    reset,
  } = useClaimValidation(claim, onValidationComplete);

  const workingClaim = { ...currentClaim, ...edits };
  const saving = state === "saving";
  // Closed by SHA (approved, paid, cancelled): kept for audit, not editable.
  const shaState = currentClaim?._sha_state ?? claim._sha_state;
  const closed = stageOf({ _sha_state: shaState }) === "closed";

  const [activeTab, setActiveTab] = useState("AI Validation");
  const [warningsReviewed, setWarningsReviewed] = useState(false);
  const [highlightField, setHighlightField] = useState(null);

  // "Show in claim": open the tab holding the field, scroll to it and flash it.
  const locateField = (field) => {
    setActiveTab(tabForField(field));
    setHighlightField(field);
    setTimeout(() => document.getElementById(`claim-field-${field}`)?.scrollIntoView({ behavior: "smooth", block: "center" }), 50);
    setTimeout(() => setHighlightField(null), 2500);
  };

  // Keyboard: Ctrl/Cmd+Enter validates (or saves and re-validates edits); Esc discards edits.
  useEffect(() => {
    const onKey = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
        e.preventDefault();
        if (hasEdits) saveCorrections();
        else if (state === "idle" || state === "results") validate();
      } else if (e.key === "Escape" && hasEdits && !document.querySelector("[role='dialog']")) {
        discardEdits();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [hasEdits, state, saveCorrections, validate, discardEdits]);
  // A new validation result may carry different warnings; ask again.
  useEffect(() => setWarningsReviewed(false), [validation]);

  // Document scan simulation state
  const [scanFile, setScanFile] = useState(null);
  const [scanState, setScanState] = useState("idle"); // "idle" | "scanning" | "done"
  const [extractedData, setExtractedData] = useState(null);

  // Automatically reset scan tab and timeline state when selected claim changes
  useEffect(() => {
    setActiveTab("AI Validation");
    setScanFile(null);
    setScanState("idle");
    setExtractedData(null);
    reset();
  }, [claim?.id, reset]);

  // Handle simulated document drop/upload
  const handleFileUpload = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setScanFile(file);
    setScanState("scanning");

    setTimeout(() => {
      setScanState("done");
      setExtractedData({
        diagnosis_code: "1A40",
        diagnosis_description: "Gastroenteritis or colitis without specification of infectious agent",
        visit_date: "2026-07-02",
        claimed_amount: 8500,
      });
    }, 2000);
  };

  const applyExtractedData = () => {
    if (!extractedData) return;
    Object.entries(extractedData).forEach(([field, value]) => {
      editField(field, value);
    });
    setScanState("applied");
  };

  // Determine current timeline active step
  let activeStep = 0; // 0: Claim Received, 1: AI Initial Review, 2: Pending Corrections, 3: Ready for Social Health Authority / Submitted
  if (state === "idle") {
    activeStep = 0;
  } else if (state === "loading") {
    activeStep = 1;
  } else if (state === "results" || state === "saving") {
    activeStep = validation?.error_count > 0 ? 2 : 3;
  } else if (state === "submitted" || state === "submitting") {
    activeStep = 3;
  }

  if (state === "submitted" && submitResult) {
    const downloadBundle = () => {
      const blob = new Blob([JSON.stringify(submitResult.sha_bundle, null, 2)], { type: "application/fhir+json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${claim.id}-sha-bundle.json`;
      link.click();
      URL.revokeObjectURL(url);
    };
    const deliveryText = {
      stored: "Stored in Hakiki for the hospital HIS to collect.",
      delivered: "Delivered to the hospital HIS.",
      failed: "Saved, but delivery to the hospital HIS failed. Download the bundle or retry.",
    }[submitResult.delivery_status];

    return (
      <div className="flex-1 bg-slate-50 dark:bg-slate-900 p-8 overflow-y-auto">
        <div className="max-w-3xl mx-auto bg-white dark:bg-slate-950 border border-slate-200/80 dark:border-slate-800 rounded-2xl p-8 shadow-sm text-center">
          <div className="w-16 h-16 rounded-full bg-emerald-100 dark:bg-emerald-950/20 flex items-center justify-center mx-auto mb-5">
            <CheckIcon className="w-8 h-8 text-emerald-600 dark:text-emerald-400" />
          </div>
          <h2 className="text-2xl font-bold text-slate-800 dark:text-slate-100">Handed off to the hospital HIS</h2>
          <p className="text-slate-500 dark:text-slate-400 text-sm mt-2 max-w-md mx-auto">
            Hakiki validated this claim against SHA rules and built the eClaims bundle. The hospital submits it to SHA
            through its HIS or the SHA provider portal. {deliveryText}
          </p>

          <dl className="my-6 grid grid-cols-2 gap-3 max-w-md mx-auto text-left text-xs">
            {[
              ["Score", `${submitResult.score}/100`],
              ["Ruleset", submitResult.ruleset_version],
              ["Hand-off ID", submitResult.handoff_id],
              ["Delivery", `${submitResult.delivery} (${submitResult.delivery_status})`],
            ].map(([label, value]) => (
              <div key={label} className="p-3 bg-slate-50 dark:bg-slate-900 border border-slate-200/60 dark:border-slate-800 rounded-xl">
                <dt className="text-[10px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">{label}</dt>
                <dd className="mt-1 font-semibold text-slate-700 dark:text-slate-200 break-all">{value}</dd>
              </div>
            ))}
          </dl>

          {submitResult.warnings_acknowledged?.length > 0 && (
            <p className="text-xs text-amber-700 dark:text-amber-400 mb-4">
              Warnings reviewed by the officer: {submitResult.warnings_acknowledged.join(", ")}
            </p>
          )}

          <div className="w-full text-left bg-slate-900 dark:bg-slate-950 border border-slate-800 dark:border-slate-800 rounded-xl p-5 overflow-hidden shadow-inner mb-6">
            <h3 className="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-widest mb-3">SHA eClaims Bundle (FHIR R4)</h3>
            <pre className="text-xs text-emerald-400 dark:text-emerald-500 font-mono overflow-x-auto max-h-60">
              {JSON.stringify(submitResult.sha_bundle, null, 2)}
            </pre>
          </div>

          <div className="flex justify-center gap-3">
            <button
              type="button"
              onClick={downloadBundle}
              className="border border-slate-200 dark:border-slate-800 text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-900 font-semibold text-sm px-5 py-2.5 rounded-xl transition-all"
            >
              Download bundle
            </button>
            <button
              type="button"
              onClick={reset}
              className="bg-teal-700 hover:bg-teal-800 active:scale-95 text-white font-semibold text-sm px-6 py-2.5 rounded-xl transition-all shadow-sm"
            >
              Validate Next Claim
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex overflow-hidden">
      {/* Dynamic workspace pane */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Patient Profile Header */}
        <div className="bg-white dark:bg-slate-950 border-b border-slate-200 dark:border-slate-800 px-6 py-5 flex-shrink-0">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div className="flex items-center gap-4">
              <div className="w-14 h-14 rounded-full bg-teal-50 dark:bg-teal-950/20 border border-teal-100 dark:border-teal-900/30 flex items-center justify-center text-teal-700 dark:text-teal-400 text-lg font-bold shadow-inner">
                {currentClaim?.patient_name ? currentClaim.patient_name.split(" ").map(n => n[0]).join("") : "PT"}
              </div>
              <div>
                <div className="flex items-center gap-2.5">
                  <h2 className="text-xl font-bold text-slate-800 dark:text-slate-100 leading-tight">
                    {currentClaim?.patient_name}
                  </h2>
                  {validation && (
                    <StatusBadge status={validation.status} color={validation.color} />
                  )}
                  <ShaStateBadge state={currentClaim?._sha_state ?? claim._sha_state} />
                </div>
                <p className="text-xs text-slate-500 dark:text-slate-400 font-medium mt-1">
                  ID: <code className="font-mono bg-slate-50 dark:bg-slate-900 border border-slate-100 dark:border-slate-800 rounded px-1 text-slate-600 dark:text-slate-400">{claim.id}</code>
                  <span className="mx-2 text-slate-300 dark:text-slate-700">•</span>
                  Facility: <span className="text-slate-700 dark:text-slate-300">{currentClaim?.facility_name}</span>
                </p>
              </div>
            </div>
            <div className="flex flex-col text-left md:text-right gap-1 md:self-end">
              <span className="text-[10px] text-slate-500 dark:text-slate-400 font-bold uppercase tracking-wider">Policy/Visit Date</span>
              <span className="text-sm font-semibold text-slate-700 dark:text-slate-300">{currentClaim?.visit_date}</span>
            </div>
          </div>
        </div>

        {/* Tabbed Navigation Selector */}
        <div className="bg-white dark:bg-slate-950 border-b border-slate-200 dark:border-slate-800 px-6 flex-shrink-0">
          <nav className="flex gap-6" aria-label="Tabs">
            {["AI Validation", "Demographics", "Claim Info", "FHIR Preview", "Audit Trail", "Dept Guide"].map((tab) => {
              const isActive = activeTab === tab;
              return (
                <button
                  key={tab}
                  type="button"
                  onClick={() => setActiveTab(tab)}
                  className={`py-3.5 px-1 font-semibold text-sm border-b-2 transition-all ${
                    isActive
                      ? "border-teal-600 dark:border-teal-400 text-teal-700 dark:text-teal-400"
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
          {closed && (
            <div role="status" className="mb-4 rounded-xl border border-emerald-200 dark:border-emerald-900/50 bg-emerald-50 dark:bg-emerald-950/30 p-4 text-sm text-emerald-900 dark:text-emerald-200">
              Closed: SHA marked this claim &quot;{shaState.label}&quot;. It is kept for audit and cannot be edited.
            </div>
          )}

          {error && (
            <div role="alert" className="mb-4 rounded-xl bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-900/30 p-4 text-sm text-red-700 dark:text-red-400 shadow-sm">
              {error}
            </div>
          )}

          {activeTab === "AI Validation" && (
            <div className="space-y-6">
              <div className="bg-white dark:bg-slate-950 border border-slate-200/80 dark:border-slate-800 rounded-2xl p-5 shadow-sm">
                <h3 className="text-sm font-bold text-slate-800 dark:text-slate-200 mb-2 flex items-center gap-2">
                  <svg className="w-5 h-5 text-teal-700 dark:text-teal-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                  Scan Claim Invoice/Document
                  <span className="text-[10px] font-bold uppercase tracking-wider rounded bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 px-1.5 py-0.5">Demo</span>
                </h3>
                <p className="text-xs text-slate-500 dark:text-slate-400 mb-4">
                  Simulated for demos: choosing a file fills example values. No document is read and nothing is uploaded.
                </p>

                {scanState === "idle" && (
                  <label className="border-2 border-dashed border-slate-200 dark:border-slate-800 hover:border-teal-500 dark:hover:border-teal-400 rounded-xl p-6 flex flex-col items-center justify-center cursor-pointer transition-all hover:bg-teal-50/20 dark:hover:bg-teal-950/5 group">
                    <svg className="w-8 h-8 text-slate-500 dark:text-slate-600 group-hover:text-teal-600 dark:group-hover:text-teal-400 mb-2 transition-colors" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                    </svg>
                    <span className="text-xs font-semibold text-slate-600 dark:text-slate-300 group-hover:text-teal-700 dark:group-hover:text-teal-400">Choose Invoice Document</span>
                    <span className="text-[10px] text-slate-500 dark:text-slate-400 mt-1">PDF, JPG, PNG (Max 5MB)</span>
                    <input type="file" className="hidden" accept=".pdf,.png,.jpg,.jpeg" onChange={handleFileUpload} />
                  </label>
                )}

                {scanState === "scanning" && (
                  <div className="border border-slate-100 dark:border-slate-800 rounded-xl p-5 flex flex-col items-center justify-center bg-slate-50 dark:bg-slate-900/60 relative overflow-hidden">
                    <div className="absolute top-0 left-0 right-0 h-0.5 bg-gradient-to-r from-teal-400 to-emerald-500 animate-[pulse_1.5s_infinite] shadow-lg shadow-teal-500" />
                    <SpinnerIcon className="w-8 h-8 text-teal-700 mb-2" />
                    <p className="text-xs font-semibold text-slate-700 dark:text-slate-200">Simulating extraction (demo)...</p>
                    <p className="text-[10px] text-slate-500 dark:text-slate-400 mt-1">Example values only</p>
                  </div>
                )}

                {scanState === "done" && (
                  <div className="border border-teal-100 dark:border-teal-900/30 rounded-xl p-4 bg-teal-50/20 dark:bg-teal-950/10">
                    <div className="flex items-center justify-between mb-3">
                      <span className="text-xs font-bold text-teal-800 dark:text-teal-400 flex items-center gap-1.5">
                        <span className="w-2 h-2 rounded-full bg-teal-500" />
                        AI Extraction Successful
                      </span>
                      <span className="text-[10px] text-slate-500 dark:text-slate-400">{scanFile?.name}</span>
                    </div>
                    <div className="grid grid-cols-2 gap-3 mb-4 bg-white dark:bg-slate-950 p-3 rounded-lg border border-slate-100 dark:border-slate-800 text-xs">
                      <div>
                        <span className="text-slate-500 dark:text-slate-400 block mb-0.5">ICD-11 Diagnosis</span>
                        <strong className="text-slate-700 dark:text-slate-200 font-semibold">{extractedData.diagnosis_code} - {extractedData.diagnosis_description}</strong>
                      </div>
                      <div>
                        <span className="text-slate-500 dark:text-slate-400 block mb-0.5">Visit Date</span>
                        <strong className="text-slate-700 dark:text-slate-200 font-semibold">{extractedData.visit_date}</strong>
                      </div>
                      <div>
                        <span className="text-slate-500 dark:text-slate-400 block mb-0.5">Claimed Amount</span>
                        <strong className="text-slate-700 dark:text-slate-200 font-semibold">KES {extractedData.claimed_amount.toLocaleString()}</strong>
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
                        onClick={() => { setScanState("idle"); setScanFile(null); }}
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
                      onClick={() => { setScanState("idle"); setScanFile(null); }}
                      className="text-xs text-teal-700 dark:text-teal-400 hover:underline font-semibold"
                    >
                      Scan Another
                    </button>
                  </div>
                )}
              </div>

              {state === "idle" && (
                <div className="bg-white dark:bg-slate-950 border border-slate-200/80 dark:border-slate-800 rounded-2xl p-8 text-center shadow-sm">
                  <p className="text-slate-500 dark:text-slate-400 text-sm mb-4 font-medium">
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
                <div className="bg-white dark:bg-slate-950 border border-slate-200/80 dark:border-slate-800 rounded-2xl p-10 flex flex-col items-center justify-center shadow-sm">
                  <SpinnerIcon />
                  <p className="text-sm font-semibold text-slate-700 dark:text-slate-200 mt-3">Adjudicating Claims Policy Rules...</p>
                  <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">Generating plain English rule interpretations</p>
                </div>
              )}

              {(state === "results" || state === "saving" || state === "submitting") && validation && (
                <>
                  <div className="flex flex-col md:flex-row items-center gap-6 bg-white dark:bg-slate-950 border border-slate-200/80 dark:border-slate-800 rounded-2xl p-6 shadow-sm">
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
                          <span className="text-xs font-bold text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-950/20 border border-amber-100 dark:border-amber-900/30 px-2 py-0.5 rounded-md self-center">
                            {validation.warning_count} Warning{validation.warning_count !== 1 ? "s" : ""}
                          </span>
                        )}
                      </div>
                      <div className="grid grid-cols-2 gap-4 mt-4 pt-4 border-t border-slate-100 dark:border-slate-800 text-xs text-slate-500 dark:text-slate-400 font-medium">
                        <div>
                          <span className="text-[10px] text-slate-500 dark:text-slate-400 uppercase block">Diagnosis</span>
                          <span className="text-slate-800 dark:text-slate-200 font-semibold">
                            {edits.diagnosis_code ?? currentClaim?.diagnosis_code ?? claim.diagnosis_code} — {currentClaim?.diagnosis_description ?? claim.diagnosis_description}
                          </span>
                        </div>
                        <div>
                          <span className="text-[10px] text-slate-500 dark:text-slate-400 uppercase block">Claimed Amount</span>
                          <span className="text-slate-800 dark:text-slate-200 font-semibold">
                            KES {Number(edits.claimed_amount ?? currentClaim?.claimed_amount ?? claim.claimed_amount).toLocaleString()}
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>

                  <div>
                    <h3 className="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-widest mb-3">
                      Validation Checklist ({validation.results?.length || 0} Rules Checked)
                    </h3>
                    <div className="space-y-3">
                      {validation.results?.map((result) => (
                        <ErrorCard
                          key={result.rule_id}
                          result={result}
                          explanation={validation.explanations?.[result.rule_id]}
                          fixSteps={validation.fix_steps?.[result.rule_id]}
                          claim={workingClaim}
                          onEdit={closed ? undefined : editField}
                          onApplyFix={closed ? undefined : applyFix}
                          onSave={() => saveCorrections()}
                          onLocate={locateField}
                          busy={saving}
                        />
                      ))}
                    </div>
                  </div>

                  {!closed && (
                  <div className="flex items-center gap-3 pt-2 bg-slate-50 dark:bg-slate-900 sticky bottom-0 z-10 py-4 border-t border-slate-200/50 dark:border-slate-800">
                    {(hasEdits || saving) && (
                      <>
                        <button
                          type="button"
                          onClick={() => saveCorrections()}
                          disabled={saving}
                          className="flex-1 bg-slate-800 hover:bg-slate-900 dark:bg-slate-700 dark:hover:bg-slate-600 disabled:opacity-60 active:scale-95 text-white font-semibold text-sm py-3 rounded-xl transition-all shadow-md"
                        >
                          {saving ? "Saving & re-validating..." : "Save & re-validate"}
                        </button>
                        {!saving && (
                          <button
                            type="button"
                            onClick={discardEdits}
                            className="px-4 py-3 border border-slate-200 dark:border-slate-800 rounded-xl text-sm font-semibold text-slate-600 dark:text-slate-400 bg-white dark:bg-slate-950 hover:bg-slate-50 dark:hover:bg-slate-900 transition-all"
                          >
                            Discard edits
                          </button>
                        )}
                      </>
                    )}

                    {canSubmit && validation.warning_count > 0 && (
                      <label className="flex items-center gap-2 text-xs font-semibold text-amber-700 dark:text-amber-400">
                        <input
                          type="checkbox"
                          checked={warningsReviewed}
                          onChange={(e) => setWarningsReviewed(e.target.checked)}
                          className="rounded border-amber-300 text-teal-700 focus:ring-teal-700 dark:focus:ring-teal-400"
                        />
                        I have reviewed the {validation.warning_count} warning{validation.warning_count !== 1 ? "s" : ""}
                      </label>
                    )}

                    <button
                      type="button"
                      onClick={() => submit(warningsReviewed)}
                      disabled={!canSubmit || state === "submitting" || (validation.warning_count > 0 && !warningsReviewed)}
                      className={`flex-1 text-white font-semibold text-sm py-3 rounded-xl transition-all shadow-md active:scale-95 ${
                        canSubmit
                          ? "bg-teal-700 hover:bg-teal-800 cursor-pointer"
                          : "bg-slate-300 dark:bg-slate-800 cursor-not-allowed opacity-70"
                      }`}
                    >
                      {state === "submitting" ? "Handing off..." : "Send to hospital HIS →"}
                    </button>

                    <button
                      type="button"
                      onClick={restoreOriginal}
                      disabled={saving}
                      title="Demo: undo all saved corrections to this claim"
                      className="px-5 py-3 border border-slate-200 dark:border-slate-800 rounded-xl text-sm font-semibold text-slate-600 dark:text-slate-400 bg-white dark:bg-slate-950 hover:bg-slate-50 dark:hover:bg-slate-900 disabled:opacity-60 active:scale-95 transition-all"
                    >
                      Restore original
                    </button>
                  </div>
                  )}
                </>
              )}
            </div>
          )}

          {activeTab === "Demographics" && <PatientDetails claim={workingClaim} highlight={highlightField} />}

          {activeTab === "Claim Info" && <ClaimInfo claim={workingClaim} highlight={highlightField} />}

          {activeTab === "FHIR Preview" && (
            <div className="bg-white dark:bg-slate-950 border border-slate-200/80 dark:border-slate-800 rounded-2xl p-6 shadow-sm">
              <h3 className="text-sm font-bold text-slate-800 dark:text-slate-200 border-b border-slate-100 dark:border-slate-800 pb-3 mb-4">FHIR R4 ClaimResponse Payload</h3>
              {validation?.fhir_claim_response ? (
                <pre className="text-xs text-slate-700 dark:text-slate-300 bg-slate-900 dark:bg-slate-950 border border-slate-800 dark:border-slate-800 rounded-xl p-4 overflow-auto font-mono text-emerald-400 dark:text-emerald-400 max-h-[450px]">
                  {JSON.stringify(validation.fhir_claim_response, null, 2)}
                </pre>
              ) : (
                <div className="text-center py-10 text-slate-500 dark:text-slate-400 text-sm font-medium">
                  Please validate the claim first to compile the FHIR JSON schema.
                </div>
              )}
            </div>
          )}

          {activeTab === "Audit Trail" && (
            <AuditTrailTab claimId={claim.id} />
          )}

          {activeTab === "Dept Guide" && (
            <DeptGuideTab department={claim.department} />
          )}
        </div>
      </div>

      {/* Right Edge: Persistent Timeline Tracker */}
      <div className="w-64 border-l border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950 flex flex-col flex-shrink-0 p-5">
        <h3 className="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-widest mb-6 mt-1">Status Timeline</h3>
        <div className="relative pl-6 space-y-8 flex-1">
          <div className="absolute left-[30px] top-2 bottom-6 w-0.5 bg-slate-200 dark:bg-slate-800" />

          <div className="relative flex gap-3.5 items-start">
            <span className={`absolute left-0 w-3 h-3 rounded-full border-2 transform -translate-x-1.5 mt-1.5 transition-all duration-300 ${
              activeStep >= 0 ? "bg-teal-500 border-teal-500 scale-110 shadow-sm shadow-teal-500/50" : "bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-700"
            }`} />
            <div className="pl-3.5">
              <p className={`text-xs font-bold ${activeStep >= 0 ? "text-slate-800 dark:text-slate-200" : "text-slate-500 dark:text-slate-400"}`}>Claim Received</p>
              <p className="text-[10px] text-slate-500 dark:text-slate-400 mt-0.5">Registered in system</p>
            </div>
          </div>

          <div className="relative flex gap-3.5 items-start">
            <span className={`absolute left-0 w-3 h-3 rounded-full border-2 transform -translate-x-1.5 mt-1.5 transition-all duration-300 ${
              activeStep >= 1 ? "bg-teal-500 border-teal-500 scale-110 shadow-sm shadow-teal-500/50" : "bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-700"
            }`} />
            <div className="pl-3.5">
              <p className={`text-xs font-bold ${activeStep >= 1 ? "text-slate-800 dark:text-slate-200" : "text-slate-500 dark:text-slate-400"}`}>AI Initial Review</p>
              <p className="text-[10px] text-slate-500 dark:text-slate-400 mt-0.5">FastAPI & Gemini AI</p>
            </div>
          </div>

          <div className="relative flex gap-3.5 items-start">
            <span className={`absolute left-0 w-3 h-3 rounded-full border-2 transform -translate-x-1.5 mt-1.5 transition-all duration-300 ${
              activeStep >= 2 ? "bg-teal-500 border-teal-500 scale-110 shadow-sm shadow-teal-500/50" : "bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-700"
            }`} />
            <div className="pl-3.5">
              <p className={`text-xs font-bold ${activeStep >= 2 ? "text-slate-800 dark:text-slate-200" : "text-slate-500 dark:text-slate-400"}`}>Pending Corrections</p>
              <p className="text-[10px] text-slate-500 dark:text-slate-400 mt-0.5">Live officer triage</p>
            </div>
          </div>

          <div className="relative flex gap-3.5 items-start">
            <span className={`absolute left-0 w-3 h-3 rounded-full border-2 transform -translate-x-1.5 mt-1.5 transition-all duration-300 ${
              activeStep >= 3 ? "bg-emerald-500 border-emerald-500 scale-110 shadow-sm shadow-emerald-500/50" : "bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-700"
            }`} />
            <div className="pl-3.5">
              <p className={`text-xs font-bold ${activeStep >= 3 ? "text-slate-800 dark:text-slate-200" : "text-slate-500 dark:text-slate-400"}`}>Ready for hospital HIS</p>
              <p className="text-[10px] text-slate-500 dark:text-slate-400 mt-0.5">Clear uploaded document</p>
            </div>
          </div>
        </div>

        <div className="border-t border-slate-100 dark:border-slate-800 pt-4 text-[10px] text-slate-500 dark:text-slate-400">
          <span className="font-semibold block text-slate-500 dark:text-slate-400">Validation Mode:</span>
          <span>FastAPI + Gemini Rule Processor</span>
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
};

ClaimWorkspace.propTypes = {
  ...ValidationPanel.propTypes,
  claim: ValidationPanel.propTypes.claim.isRequired,
};
