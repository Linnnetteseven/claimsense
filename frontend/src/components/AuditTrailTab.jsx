import { useCallback, useEffect, useState } from "react";
import PropTypes from "prop-types";
import { useClaimAudit } from "../hooks/useClaimAudit.js";
import { api } from "../api/client.js";

export default function AuditTrailTab({ claimId, privacyMode = false }) {
  const { state, history, currentVersion, error, load } = useClaimAudit();
  const [anchorState, setAnchorState] = useState({ status: "not_checked", anchors: [] });
  const [anchorBusy, setAnchorBusy] = useState(false);
  const [anchorError, setAnchorError] = useState("");
  const [evidenceBusy, setEvidenceBusy] = useState(false);
  const [evidenceResult, setEvidenceResult] = useState(null);
  const [evidenceError, setEvidenceError] = useState("");

  const verifyAnchor = useCallback(async () => {
    setAnchorState((current) => ({ ...current, status: "checking" }));
    try { setAnchorState(await api.verifyLedgerAnchor()); }
    catch { setAnchorState({ status: "unavailable", anchors: [] }); }
  }, []);

  const anchorNow = async () => {
    const secret = window.prompt("Enter the backend anchor authorization secret:");
    if (!secret) return;
    setAnchorBusy(true); setAnchorError("");
    try {
      const result = await api.anchorLedger(secret);
      if (result.status === "unavailable") {
        setAnchorError(result.reason || "Avalanche is unavailable.");
        return;
      }
      await verifyAnchor();
    } catch (err) { setAnchorError(err.message); }
    finally { setAnchorBusy(false); }
  };

  const exportEvidencePack = async () => {
    setEvidenceBusy(true);
    setEvidenceError("");
    setEvidenceResult(null);
    try { setEvidenceResult(await api.createEvidencePack(claimId)); }
    catch (exportError) { setEvidenceError(exportError.message || "Could not create evidence pack."); }
    finally { setEvidenceBusy(false); }
  };

  useEffect(() => {
    if (claimId) load(claimId);
  }, [claimId, load]);

  const versionAnchor = anchorState.anchors?.find((item) =>
    currentVersion?.event_seq >= item.from_seq && currentVersion?.event_seq <= item.to_seq
  );

  if (state === "idle" || state === "loading") {
    return (
      <div className="bg-white dark:bg-slate-950 border border-slate-200/80 dark:border-slate-850 rounded-2xl p-8 text-center shadow-sm">
        <p className="text-sm text-slate-500 dark:text-slate-400">Loading audit history…</p>
      </div>
    );
  }

  if (state === "error") {
    return (
      <div className="bg-white dark:bg-slate-950 border border-slate-200/80 dark:border-slate-850 rounded-2xl p-6 shadow-sm">
        <p className="text-sm text-red-600 dark:text-red-400">
          Couldn&apos;t load audit history: {error}
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <details className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950 p-4">
        <summary className="cursor-pointer text-sm font-semibold text-slate-700 dark:text-slate-200">Ledger integrity and Avalanche anchoring</summary>
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 dark:border-slate-800 pt-4">
          <div className="text-sm">
            {anchorState.status === "verified" && anchorState.anchors?.length > 0 ? (
              <span className="text-emerald-700 dark:text-emerald-400">Verified against Avalanche Fuji, block {anchorState.anchors.at(-1).block_number}</span>
            ) : <span className="text-slate-500 dark:text-slate-400">{anchorState.status === "not_checked" ? "Not checked yet" : anchorState.status === "checking" ? "Checking Avalanche Fuji…" : anchorState.status === "not_anchored" ? "Not anchored to Avalanche Fuji" : anchorState.status === "mismatch" ? "Ledger anchor mismatch" : "Avalanche verification unavailable"}</span>}
            {anchorState.anchors?.at(-1)?.tx_hash && <a className="ml-2 text-teal-700 underline" href={`https://subnets-test.avax.network/c-chain/tx/${anchorState.anchors.at(-1).tx_hash}`} target="_blank" rel="noreferrer">View on Avalanche Explorer</a>}
          </div>
          <div className="flex flex-wrap gap-2">
            <button type="button" disabled={anchorBusy || anchorState.status === "checking"} onClick={verifyAnchor} className="rounded-lg border border-slate-300 dark:border-slate-700 px-4 py-2 text-sm font-semibold text-slate-700 dark:text-slate-200 disabled:opacity-50">{anchorState.status === "checking" ? "Checking…" : "Check against Avalanche"}</button>
            <button type="button" disabled={anchorBusy || anchorState.status === "checking"} onClick={anchorNow} className="rounded-lg bg-teal-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{anchorBusy ? "Anchoring…" : "Anchor now"}</button>
          </div>
          {anchorError && <p className="w-full text-sm text-red-600">{anchorError}</p>}
        </div>
      </details>
      <div className="flex items-center gap-3 bg-teal-50/50 dark:bg-teal-950/10 border border-teal-100 dark:border-teal-900/30 rounded-2xl p-4">
        <span className="w-9 h-9 rounded-full bg-teal-100 dark:bg-teal-950/30 flex items-center justify-center text-teal-700 dark:text-teal-400 text-sm font-bold shrink-0">
          ✓
        </span>
        <div>
          <p className="text-sm font-bold text-slate-800 dark:text-slate-200">
            {history.length} lifecycle event{history.length !== 1 ? "s" : ""} hash-linked
          </p>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            Intake, validation, corrections, department actions, and submission events are linked in order.
          </p>
        </div>
      </div>

      {currentVersion && (
        <div className={`rounded-xl border p-4 text-sm ${currentVersion.status === "mismatch" ? "border-red-200 bg-red-50 text-red-700 dark:border-red-900/40 dark:bg-red-950/20 dark:text-red-300" : "border-slate-200 bg-white text-slate-600 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-300"}`}>
          {currentVersion.status === "matches" ? (
            versionAnchor
              ? `Saved claim version ${currentVersion.version} matches its fingerprint and is included in verified Avalanche Fuji block ${versionAnchor.block_number}.`
              : `Saved claim version ${currentVersion.version} matches its recorded fingerprint; it is not included in a verified Avalanche anchor yet.`
          ) : currentVersion.status === "mismatch" ? (
            "The current saved claim does not match the latest recorded version fingerprint."
          ) : "No saved claim version fingerprint is available yet."}
        </div>
      )}

      <section className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950 p-4">
        <div><h3 className="text-sm font-bold text-slate-800 dark:text-slate-200">Synthetic evidence pack</h3><p className="text-xs text-slate-500 dark:text-slate-400">Exports version fingerprints, checks, sign-offs, ledger hashes and anchor status without claim contents.</p></div>
        <button type="button" onClick={exportEvidencePack} disabled={evidenceBusy} className="rounded-lg bg-teal-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{evidenceBusy ? "Preparing…" : "Export evidence pack"}</button>
        {evidenceError && <p role="alert" className="w-full text-xs text-red-600 dark:text-red-400">{evidenceError}</p>}
        {evidenceResult && <div role="status" className="w-full space-y-2 text-xs text-slate-600 dark:text-slate-300"><p>{evidenceResult.message || "Evidence pack saved locally."}</p><div className="flex gap-4"><a className="font-semibold text-teal-700 underline dark:text-teal-400" href={api.evidencePackFileUrl(evidenceResult.files.json)} download>Download JSON</a><a className="font-semibold text-teal-700 underline dark:text-teal-400" href={api.evidencePackFileUrl(evidenceResult.files.pdf)} download>Download PDF</a></div></div>}
      </section>

      <div className="bg-white dark:bg-slate-950 border border-slate-200/80 dark:border-slate-850 rounded-2xl p-5 shadow-sm">
        <h3 className="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-widest mb-4">
            Claim lifecycle history
        </h3>
        {history.length === 0 && <p className="text-sm text-slate-500 dark:text-slate-400">No claim events have been recorded yet.</p>}
        {history.length > 0 ? (
          <div className="space-y-3">
          {history.map((block, i) => (
            <div
              key={block.hash}
              className="border border-slate-100 dark:border-slate-850 rounded-xl p-4 bg-slate-50/50 dark:bg-slate-900/40"
            >
              <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                <span className="text-xs font-mono text-slate-500 dark:text-slate-400">
                  Event #{block.seq ?? i + 1} · {eventLabel(block.type)}
                </span>
                {block.type === "validation" && <span className="text-sm font-bold text-slate-800 dark:text-slate-200">Automated score: {block.score}/100</span>}
              </div>
              <div className="mb-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500 dark:text-slate-400">
                {block.version != null && <span>Claim version {block.version}</span>}
                {block.changed_fields?.length > 0 && <span>Changed: {block.changed_fields.join(", ")}</span>}
                {block.department && <span>Department: {block.department}</span>}
                {block.step_title && <span>Check: {block.step_title}</span>}
                {block.actor_label && <span>Recorded name: {privacyMode ? "********" : block.actor_label} (not account-verified)</span>}
                {block.decision && <span>Officer decision: {block.decision === "correction_requested" ? "correction requested" : "reviewed"}</span>}
                {block.outcome && <span>Submission: {block.outcome}</span>}
                {block.completed_checks?.length > 0 && <span>Completed: {block.completed_checks.join(", ")}</span>}
              </div>
              <details className="min-w-0">
                <summary className="cursor-pointer text-xs font-semibold text-teal-700 dark:text-teal-400">View version and event fingerprints</summary>
                <div className="grid grid-cols-1 gap-3 mt-3 text-xs font-mono text-slate-500 dark:text-slate-400">
                  {block.version_fingerprint && <div className="min-w-0"><span className="block text-slate-500 dark:text-slate-400">Claim version fingerprint</span><code className="block mt-1 break-all">{block.version_fingerprint}</code></div>}
                  {block.review_fingerprint && <div className="min-w-0"><span className="block text-slate-500 dark:text-slate-400">Department review fingerprint</span><code className="block mt-1 break-all">{block.review_fingerprint}</code></div>}
                  <div className="min-w-0">
                    <span className="block text-slate-500 dark:text-slate-400">Previous record hash</span>
                    <code className="block mt-1 break-all">{block.prev_hash}</code>
                  </div>
                  <div className="min-w-0">
                    <span className="block text-slate-500 dark:text-slate-400">This record hash</span>
                    <code className="block mt-1 break-all">{block.hash}</code>
                  </div>
                </div>
              </details>
              <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-2">
                {block.timestamp}
              </p>
            </div>
          ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}

function eventLabel(type) {
  const labels = {
    claim_received: "Claim received",
    claim_corrected: "Claim corrected",
    validation: "Automated validation",
    staff_review_completed: "Claims officer review",
    department_check_completed: "Department check completed",
    department_check_reopened: "Department check reopened",
    department_evidence_saved: "Department evidence reference saved",
    department_signed_off: "Department signed off",
    department_signoff_revoked: "Department sign-off revoked",
    department_reviewer_updated: "Department reviewer updated",
    department_review_note_saved: "Department note saved",
    submission: "Submission attempt",
  };
  return labels[type] || type || "Audit event";
}

AuditTrailTab.propTypes = {
  claimId: PropTypes.string.isRequired,
  privacyMode: PropTypes.bool,
};
