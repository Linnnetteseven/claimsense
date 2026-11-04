import { useEffect, useMemo, useRef, useState } from "react";
import PropTypes from "prop-types";
import { DEPARTMENT_GUIDES } from "../data/departmentGuides.js";
import { DEPARTMENT_REVIEW_UPDATED, departmentReviewStorageKey, readDepartmentReview } from "../utils/departmentReview.js";
import { api } from "../api/client.js";
import { fingerprintDepartmentReview } from "../utils/reviewFingerprint.js";

export default function DeptGuideTab({ claimId, department, privacyMode = false }) {
  const departmentKey = (department || "").toLowerCase();
  const guide = DEPARTMENT_GUIDES[departmentKey];
  const storageKey = departmentReviewStorageKey(claimId, department);
  const [review, setReview] = useState(() => readDepartmentReview(claimId, department));
  const [auditSyncState, setAuditSyncState] = useState("idle");
  const [storageSyncState, setStorageSyncState] = useState("loading");
  const reviewRef = useRef(review);
  const localRevision = useRef(0);
  const pendingSaves = useRef(0);
  const requiredSteps = useMemo(() => guide?.steps.filter((step) => step.required) || [], [guide]);
  const completedRequired = requiredSteps.filter((step) => review.completed[step.title]).length;
  const documentedRequired = requiredSteps.filter((step) => review.completed[step.title] && String(review.evidence[step.title] || "").trim()).length;
  const readyToSignOff = requiredSteps.length > 0 && documentedRequired === requiredSteps.length;
  const completedTotal = guide?.steps.filter((step) => review.completed[step.title]).length || 0;

  const logReviewAction = async (snapshot, action, stepTitle = null) => {
    if (!claimId) return;
    setAuditSyncState("saving");
    try {
      const reviewFingerprint = await fingerprintDepartmentReview(departmentKey, snapshot);
      const response = await api.recordDepartmentReview(claimId, {
        department: departmentKey,
        action,
        step_title: stepTitle,
        review_fingerprint: reviewFingerprint,
        completed_checks: Object.keys(snapshot.completed || {}).filter((title) => snapshot.completed[title]),
        signed_off: Boolean(snapshot.signedOffAt),
        actor_label: snapshot.signedOffBy || snapshot.reviewer || "",
      });
      if (!response.recorded) throw new Error("Audit storage is unavailable");
      setAuditSyncState("saved");
    } catch {
      setAuditSyncState("unavailable");
    }
  };

  useEffect(() => {
    let active = true;
    const localReview = readDepartmentReview(claimId, department);
    reviewRef.current = localReview;
    setReview(localReview);
    setStorageSyncState("loading");
    const hasLocalState = Boolean(Object.keys(localReview.completed || {}).length
      || Object.keys(localReview.evidence || {}).length || localReview.signedOffAt
      || localReview.reviewer || localReview.note);

    const refreshSharedReview = async (initial = false) => {
      const revisionAtRequest = localRevision.current;
      try {
        const { review: remoteReview } = await api.getDepartmentReview(claimId, departmentKey);
        if (!active || revisionAtRequest !== localRevision.current || pendingSaves.current > 0) return;
        if (remoteReview) {
          if (JSON.stringify(remoteReview) !== JSON.stringify(reviewRef.current)) {
            reviewRef.current = remoteReview;
            setReview(remoteReview);
            try { window.localStorage.setItem(storageKey, JSON.stringify(remoteReview)); } catch { /* Server copy remains available. */ }
            window.dispatchEvent(new CustomEvent(DEPARTMENT_REVIEW_UPDATED, { detail: { claimId, department: departmentKey } }));
          }
          setStorageSyncState("saved");
        } else if (initial && hasLocalState) {
          pendingSaves.current += 1;
          api.saveDepartmentReview(claimId, departmentKey, localReview)
            .then(() => active && setStorageSyncState("saved"))
            .catch(() => active && setStorageSyncState("local"))
            .finally(() => { pendingSaves.current = Math.max(0, pendingSaves.current - 1); });
        } else if (initial) {
          setStorageSyncState("local");
        }
      } catch {
        if (active && initial) setStorageSyncState("local");
      }
    };

    refreshSharedReview(true);
    const pollId = window.setInterval(() => refreshSharedReview(), 5000);
    return () => { active = false; window.clearInterval(pollId); };
  }, [storageKey, claimId, department, departmentKey]);

  const save = (next, auditAction = null, stepTitle = null) => {
    localRevision.current += 1;
    const revision = localRevision.current;
    reviewRef.current = next;
    setReview(next);
    try {
      window.localStorage.setItem(storageKey, JSON.stringify(next));
      window.dispatchEvent(new CustomEvent(DEPARTMENT_REVIEW_UPDATED, { detail: { claimId, department: departmentKey } }));
    } catch {
      // Keep the checklist usable in memory if browser storage is unavailable.
    }
    setStorageSyncState("saving");
    pendingSaves.current += 1;
    api.saveDepartmentReview(claimId, departmentKey, next)
      .then(() => { if (revision === localRevision.current) setStorageSyncState("saved"); })
      .catch(() => { if (revision === localRevision.current) setStorageSyncState("local"); })
      .finally(() => { pendingSaves.current = Math.max(0, pendingSaves.current - 1); });
    if (auditAction) logReviewAction(next, auditAction, stepTitle);
  };

  const update = (patch, revokeSignoff = true, auditAction = null, stepTitle = null) => {
    const signoffWasRevoked = Boolean(review.signedOffAt && revokeSignoff);
    save({
      ...review,
      ...patch,
      ...(revokeSignoff ? { signedOffAt: null, signedOffBy: "" } : {}),
    }, signoffWasRevoked ? "department_signoff_revoked" : auditAction, stepTitle);
  };

  const setStepComplete = (title, checked) => {
    update(
      { completed: { ...review.completed, [title]: checked } },
      true,
      checked ? "department_check_completed" : "department_check_reopened",
      title,
    );
  };

  const signOff = () => {
    if (!readyToSignOff || !review.reviewer.trim()) return;
    update(
      {
        signedOffAt: new Date().toISOString(),
        signedOffBy: review.reviewer.trim(),
      },
      false,
      "department_signed_off",
    );
  };

  if (!guide) {
    return (
      <div className="bg-white dark:bg-slate-950 border border-slate-200/80 dark:border-slate-850 rounded-2xl p-8 text-center shadow-sm">
        <p className="text-sm text-slate-500 dark:text-slate-400">
          No owning department is set for this claim, so Hakiki cannot place it in a department inbox.
        </p>
      </div>
    );
  }

  const isSignedOff = Boolean(review.signedOffAt && readyToSignOff);
  const status = isSignedOff
    ? "Processing complete"
    : readyToSignOff
      ? "Ready to complete"
      : "In progress";
  const statusStyle = isSignedOff
    ? "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/20 dark:text-emerald-400 dark:border-emerald-900/40"
    : readyToSignOff
      ? "bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-950/20 dark:text-blue-400 dark:border-blue-900/40"
      : "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/20 dark:text-amber-400 dark:border-amber-900/40";

  return (
    <div className="space-y-4">
      <section className="bg-white dark:bg-slate-950 border border-slate-200/80 dark:border-slate-850 rounded-2xl p-6 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 dark:border-slate-850 pb-4 mb-4">
          <div>
            <h3 className="text-sm font-bold text-slate-800 dark:text-slate-200">
              {guide.label} · department workspace
            </h3>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
              Complete this department&apos;s checks and add an evidence reference for each required item. These operational checks should be aligned with Kerugoya&apos;s SOPs; SHA requirements can vary by intervention and scheme.
            </p>
          </div>
          <span className={`text-xs font-semibold rounded-full border px-3 py-1 ${statusStyle}`}>
            {status}
          </span>
        </div>

        <p role="status" className="mb-4 text-xs text-slate-500 dark:text-slate-400">
          {storageSyncState === "loading" ? "Loading shared checklist state…"
            : storageSyncState === "saving" ? "Saving checklist to Hakiki…"
              : storageSyncState === "saved" ? "Checklist saved to the shared backend."
                : "Backend unavailable; checklist remains saved in this browser."}
        </p>

        <div className="mb-5">
          <div className="flex justify-between text-xs text-slate-500 dark:text-slate-400 mb-2">
            <span>Checklist progress</span>
            <span>{completedTotal}/{guide.steps.length} complete · {completedRequired}/{requiredSteps.length} required</span>
          </div>
          <div className="h-2 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
            <div
              className="h-full bg-teal-500 transition-all"
              style={{ width: `${guide.steps.length ? (completedTotal / guide.steps.length) * 100 : 0}%` }}
            />
          </div>
        </div>

        {auditSyncState === "unavailable" && (
          <p role="status" className="mb-4 rounded-lg border border-amber-200 dark:border-amber-900/40 bg-amber-50 dark:bg-amber-950/20 p-3 text-xs text-amber-800 dark:text-amber-300">
            Checklist data remains available locally, but Hakiki could not add the action fingerprint to the server audit trail.
          </p>
        )}

        <div className="space-y-3">
          {guide.steps.map((step) => {
            const done = Boolean(review.completed[step.title]);
            return (
              <div key={step.title} className="rounded-xl border border-slate-100 dark:border-slate-800 p-4">
                <label className="flex items-start gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={done}
                    onChange={(event) => setStepComplete(step.title, event.target.checked)}
                    className="mt-1 h-4 w-4 rounded border-slate-300 text-teal-600 focus:ring-teal-500"
                  />
                  <span className="flex-1 text-sm text-slate-700 dark:text-slate-300">{step.title}</span>
                  <span className={`text-[10px] font-bold uppercase tracking-wide rounded-full px-2 py-0.5 ${step.required ? "text-slate-600 bg-slate-100 dark:bg-slate-800 dark:text-slate-300" : "text-slate-400 border border-slate-200 dark:border-slate-700"}`}>
                    {step.required ? "Required" : "Optional"}
                  </span>
                </label>
                {done && (
                  <input
                    type="text"
                    value={privacyMode && review.evidence[step.title] ? "********" : review.evidence[step.title] || ""}
                    readOnly={privacyMode}
                    onChange={(event) => update({ evidence: { ...review.evidence, [step.title]: event.target.value } })}
                    onBlur={() => logReviewAction(review, "department_evidence_saved", step.title)}
                    placeholder="Evidence reference (record, document, or note)"
                    aria-label={`Evidence reference for ${step.title}`}
                    className="mt-3 ml-7 w-[calc(100%-1.75rem)] text-xs p-2.5 border border-slate-200 dark:border-slate-700 rounded-lg bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-200"
                  />
                )}
              </div>
            );
          })}
        </div>
      </section>

      <section className="bg-white dark:bg-slate-950 border border-slate-200/80 dark:border-slate-850 rounded-2xl p-6 shadow-sm space-y-4">
        <h4 className="text-sm font-bold text-slate-800 dark:text-slate-200">Department processing completion</h4>
        <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400">
          Staff member processing this claim
          <input
            value={privacyMode && review.reviewer ? "********" : review.reviewer}
            readOnly={privacyMode}
            onChange={(event) => update({ reviewer: event.target.value })}
            onBlur={() => logReviewAction(review, "department_reviewer_updated")}
            placeholder="Name of department staff member"
            className="mt-1.5 w-full text-sm font-normal p-2.5 border border-slate-200 dark:border-slate-700 rounded-lg bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-200"
          />
        </label>
        <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400">
          Department work note
          <textarea
            value={privacyMode && review.note ? "********" : review.note}
            readOnly={privacyMode}
            onChange={(event) => update({ note: event.target.value })}
            onBlur={() => logReviewAction(review, "department_review_note_saved")}
            rows={2}
            placeholder="Record a claim-processing note"
            className="mt-1.5 w-full text-sm font-normal p-2.5 border border-slate-200 dark:border-slate-700 rounded-lg bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-200"
          />
        </label>
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={signOff}
            disabled={!readyToSignOff || !review.reviewer.trim() || Boolean(review.signedOffAt)}
            className="rounded-lg px-4 py-2 text-sm font-semibold text-white bg-teal-600 hover:bg-teal-700 disabled:bg-slate-300 disabled:dark:bg-slate-700 disabled:cursor-not-allowed"
          >
            {isSignedOff ? "Department processing complete" : "Mark department processing complete"}
          </button>
          {isSignedOff && (
            <p className="text-xs text-slate-500 dark:text-slate-400">
              Signed by {privacyMode ? "********" : review.signedOffBy} · {new Date(review.signedOffAt).toLocaleString()}
            </p>
          )}
        </div>
        {!readyToSignOff && (
          <p className="text-xs text-slate-500 dark:text-slate-400">
            Complete each required check and add its evidence reference before signing off ({documentedRequired}/{requiredSteps.length} documented).
          </p>
        )}
      </section>
    </div>
  );
}

DeptGuideTab.propTypes = {
  claimId: PropTypes.string,
  department: PropTypes.string,
  privacyMode: PropTypes.bool,
};
