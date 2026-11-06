import { useCallback, useEffect, useState } from "react";
import PropTypes from "prop-types";
import { useClaimAudit } from "../hooks/useClaimAudit.js";
import { api } from "../api/client.js";

export default function AuditTrailTab({ claimId, privacyMode = false }) {
  const { state, history, currentVersion, error, load } = useClaimAudit();
  const [anchorState, setAnchorState] = useState({ status: "not_checked", anchors: [] });
  const [anchorBusy, setAnchorBusy] = useState(false);
  const [anchorError, setAnchorError] = useState("");
  const [fullVerifyBusy, setFullVerifyBusy] = useState(false);
  const [fullVerifyResult, setFullVerifyResult] = useState(null);
  const [evidenceBusy, setEvidenceBusy] = useState(false);
  const [evidenceResult, setEvidenceResult] = useState(null);
  const [evidenceError, setEvidenceError] = useState("");

  const checkAnchorStatus = useCallback(async () => {
    setAnchorState((current) => ({ ...current, status: "checking" }));
    try { setAnchorState(await api.checkAnchorStatus()); }
    catch (error) {
      setAnchorError(error.message || "Could not check the saved anchor status.");
      setAnchorState((current) => ({ ...current, status: "unavailable" }));
    }
  }, []);

  const verifyFullLedger = async () => {
    setFullVerifyBusy(true);
    setFullVerifyResult(null);
    try { setFullVerifyResult(await api.verifyFullLedger()); }
    catch (error) { setFullVerifyResult({ verified: false, reason: error.message }); }
    finally { setFullVerifyBusy(false); }
  };

  const anchorNow = async () => {
    const secret = window.prompt("Enter the backend anchor authorization secret:");
    if (!secret) return;
    setAnchorBusy(true); setAnchorError("");
    try {
      const result = await api.anchorLedger(secret);
      const normalizedStatus = result.status === "anchored" || result.status === "already_anchored" ? "confirmed" : result.status === "unavailable" ? "failed" : result.status;
      const legacyAnchor = result.tx_hash ? {
        status: normalizedStatus, tx_hash: result.tx_hash, root_hash: result.root_hash || result.root,
        head_hash: result.head_hash, from_seq: result.from_seq, to_seq: result.to_seq,
        block_number: result.block_number, explorer_url: result.explorer_url,
      } : null;
      setAnchorState({ status: normalizedStatus, anchors: result.anchor ? [result.anchor] : legacyAnchor ? [legacyAnchor] : [] });
      if (normalizedStatus === "failed") setAnchorError(result.reason || "The anchor transaction failed.");
      else setAnchorError("");
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

  useEffect(() => {
    checkAnchorStatus();
  }, [checkAnchorStatus]);

  const trackedAnchor = anchorState.anchor || anchorState.anchors?.at(-1);
  useEffect(() => {
    if (trackedAnchor?.status !== "pending" || !trackedAnchor.root_hash) return undefined;
    const timer = window.setTimeout(async () => {
      try { setAnchorState(await api.checkAnchorStatus(trackedAnchor.root_hash)); }
      catch { /* Keep the pending display; the user can check again manually. */ }
    }, 5000);
    return () => window.clearTimeout(timer);
  }, [trackedAnchor?.root_hash, trackedAnchor?.status]);

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
          {(() => {
            const anchorRow = anchorState.anchor || anchorState.anchors?.at(-1);
            const displayStatus = anchorRow?.status || anchorState.status;
            return <div className="text-sm">
              <span className={displayStatus === "confirmed" || displayStatus === "verified" ? "text-emerald-700 dark:text-emerald-400" : displayStatus === "failed" || displayStatus === "mismatch" ? "text-red-600 dark:text-red-400" : displayStatus === "pending" || displayStatus === "checking" ? "text-amber-700 dark:text-amber-400" : "text-slate-500 dark:text-slate-400"}>
                {displayStatus === "confirmed" || displayStatus === "verified" ? `Confirmed${anchorRow?.block_number ? ` in block ${anchorRow.block_number}` : " on Avalanche Fuji"}` : displayStatus === "pending" ? "Pending on Avalanche Fuji" : displayStatus === "failed" ? "Anchor failed" : displayStatus === "checking" ? "Checking anchor status…" : displayStatus === "not_anchored" ? "No anchor recorded yet" : displayStatus === "not_checked" ? "Not checked yet" : "Anchor status unavailable"}
              </span>
              {anchorRow?.tx_hash && <a className="ml-2 text-teal-700 underline dark:text-teal-400" href={anchorRow.explorer_url || `https://subnets-test.avax.network/c-chain/tx/${anchorRow.tx_hash}`} target="_blank" rel="noreferrer">View transaction</a>}
              {anchorRow?.tx_hash && <code className="ml-2 break-all text-xs text-slate-500">{anchorRow.tx_hash}</code>}
            </div>;
          })()}
          <div className="flex flex-wrap gap-2">
            <button type="button" disabled={anchorBusy || anchorState.status === "checking"} onClick={checkAnchorStatus} className="rounded-lg border border-slate-300 dark:border-slate-700 px-4 py-2 text-sm font-semibold text-slate-700 dark:text-slate-200 disabled:opacity-50">{anchorState.status === "checking" ? "Checking…" : anchorState.status === "failed" ? "Retry status check" : "Check status"}</button>
            <button type="button" disabled={anchorBusy || anchorState.status === "checking" || anchorState.status === "pending" || anchorState.status === "failed" || anchorState.anchor?.status === "pending" || anchorState.anchor?.status === "failed" || anchorState.anchors?.at(-1)?.status === "pending" || anchorState.anchors?.at(-1)?.status === "failed"} onClick={anchorNow} className="rounded-lg bg-teal-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{anchorBusy ? "Submitting…" : "Anchor now"}</button>
            <button type="button" disabled={fullVerifyBusy} onClick={verifyFullLedger} className="rounded-lg border border-slate-300 dark:border-slate-700 px-4 py-2 text-sm font-semibold text-slate-700 dark:text-slate-200 disabled:opacity-50">{fullVerifyBusy ? "Verifying full ledger…" : "Verify full ledger"}</button>
          </div>
          {anchorError && <p className="w-full text-sm text-red-600">{anchorError}</p>}
          {fullVerifyResult && <p role="status" className={`w-full text-sm ${fullVerifyResult.verified ? "text-emerald-700 dark:text-emerald-400" : "text-red-600 dark:text-red-400"}`}>{fullVerifyResult.verified ? `Full ledger verified (${fullVerifyResult.total} records). Checkpoint saved at seq ${fullVerifyResult.checkpoint?.seq ?? fullVerifyResult.total}.` : `Full ledger verification failed: ${fullVerifyResult.message || fullVerifyResult.reason || `record ${fullVerifyResult.broken_at}`}`}</p>}
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
