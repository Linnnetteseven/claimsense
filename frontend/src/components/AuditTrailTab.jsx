import { useEffect } from "react";
import PropTypes from "prop-types";
import { useClaimAudit } from "../hooks/useClaimAudit.js";

export default function AuditTrailTab({ claimId }) {
  const { state, history, error, load } = useClaimAudit();

  useEffect(() => {
    if (claimId) load(claimId);
  }, [claimId, load]);

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

  if (history.length === 0) {
    return (
      <div className="bg-white dark:bg-slate-950 border border-slate-200/80 dark:border-slate-850 rounded-2xl p-8 text-center shadow-sm">
        <p className="text-sm text-slate-500 dark:text-slate-400">
          No validation runs recorded yet for this claim.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 bg-teal-50/50 dark:bg-teal-950/10 border border-teal-100 dark:border-teal-900/30 rounded-2xl p-4">
        <span className="w-9 h-9 rounded-full bg-teal-100 dark:bg-teal-950/30 flex items-center justify-center text-teal-700 dark:text-teal-400 text-sm font-bold shrink-0">
          ✓
        </span>
        <div>
          <p className="text-sm font-bold text-slate-800 dark:text-slate-200">
            {history.length} validation run{history.length !== 1 ? "s" : ""} hash-linked
          </p>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            Each run is chained to the one before it — editing a past record would break the chain.
          </p>
        </div>
      </div>

      <div className="bg-white dark:bg-slate-950 border border-slate-200/80 dark:border-slate-850 rounded-2xl p-5 shadow-sm">
        <h3 className="text-xs font-bold text-slate-400 dark:text-slate-500 uppercase tracking-widest mb-4">
          Validation history
        </h3>
        <div className="space-y-3">
          {history.map((block, i) => (
            <div
              key={block.hash}
              className="border border-slate-100 dark:border-slate-850 rounded-xl p-4 bg-slate-50/50 dark:bg-slate-900/40"
            >
              <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                <span className="text-xs font-mono text-slate-400 dark:text-slate-500">
                  Run #{i + 1}
                </span>
                <span className="text-sm font-bold text-slate-800 dark:text-slate-200">
                  Score: {block.score}/100
                </span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs font-mono text-slate-500 dark:text-slate-400">
                <div>
                  <span className="block text-slate-400 dark:text-slate-500">Prev hash</span>
                  {block.prev_hash}
                </div>
                <div>
                  <span className="block text-slate-400 dark:text-slate-500">This hash</span>
                  {block.hash}
                </div>
              </div>
              <p className="text-[11px] text-slate-400 dark:text-slate-500 mt-2">
                {block.timestamp}
              </p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

AuditTrailTab.propTypes = {
  claimId: PropTypes.string.isRequired,
};