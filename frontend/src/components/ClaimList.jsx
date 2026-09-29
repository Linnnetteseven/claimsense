import { useState, useMemo } from "react";
import PropTypes from "prop-types";
import { LIST_BADGE_CLASSES, LIST_DOT_CLASSES } from "../constants/status.js";
import ShaStateBadge from "./ShaStateBadge.jsx";
import { STAGES, stageOf } from "../constants/stages.js";

// Queue shows only the last 4 characters of a patient's SHA number.
const maskId = (id) => (id ? `••••${String(id).slice(-4)}` : "no SHA number");

const highlightMatch = (text, query) => {
  if (!query || !text) return text;
  const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const parts = text.split(new RegExp(`(${escaped})`, 'gi'));
  return (
    <>
      {parts.map((part, i) =>
        part.toLowerCase() === query.toLowerCase()
          ? <span key={i} className="bg-teal-200 text-slate-900 font-bold rounded-sm">{part}</span>
          : part
      )}
    </>
  );
};

export default function ClaimList({ claims, loading, selectedId, onSelect }) {
  const [query, setQuery] = useState("");
  const [activeTab, setActiveTab] = useState("todo");

  const stageCounts = useMemo(() => {
    const counts = Object.fromEntries(STAGES.map((s) => [s.key, 0]));
    claims.forEach((c) => { counts[c._stage ?? stageOf(c)] += 1; });
    return counts;
  }, [claims]);

  // Filter in memory, no API call. A search looks across every stage so any claim can be found.
  const filteredClaims = useMemo(() => {
    let result = claims;

    if (!query.trim()) {
      result = result.filter((c) => (c._stage ?? stageOf(c)) === activeTab);
    } else {
      const q = query.trim().toLowerCase();
      result = result.filter(
        (c) =>
          c.patient_name?.toLowerCase().includes(q) ||
          c.id?.toLowerCase().includes(q) ||
          c.facility_name?.toLowerCase().includes(q)
      );
    }

    return result;
  }, [claims, query, activeTab]);

  if (loading) {
    return (
      <div className="space-y-3 p-4" aria-busy="true">
        {[...Array(5)].map((_, i) => (
          <div key={i} className="h-20 bg-slate-100 dark:bg-slate-900 border border-slate-200/60 dark:border-slate-800 rounded-xl animate-pulse" />
        ))}
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <div className="p-3 space-y-2">
        <input
          id="claim-search"
          aria-label="Search claims (press / to focus)"
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search patient or ID...  ( / )"
          className="w-full text-sm p-2.5 border border-slate-200 dark:border-slate-800 rounded-xl shadow-sm bg-white dark:bg-slate-900 text-slate-800 dark:text-slate-100 placeholder-slate-500 dark:placeholder-slate-400 focus:ring-2 focus:ring-teal-500/20 focus:border-teal-500 outline-none"
        />
        <div
          role="tablist"
          aria-label="Claim stages"
          className={`flex bg-slate-100 dark:bg-slate-900/60 p-1 rounded-lg border dark:border-slate-800 ${query.trim() ? "opacity-60" : ""}`}
        >
          {STAGES.map((stage) => (
            <button
              key={stage.key}
              type="button"
              role="tab"
              aria-selected={activeTab === stage.key}
              title={stage.hint}
              onClick={() => setActiveTab(stage.key)}
              className={`flex-1 py-1.5 text-[10px] font-bold uppercase rounded-md transition-all whitespace-nowrap ${
                activeTab === stage.key
                  ? "bg-white dark:bg-slate-800 shadow-sm text-slate-800 dark:text-slate-100"
                  : "text-slate-600 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200"
              }`}
            >
              {stage.label} <span className="font-semibold">{stageCounts[stage.key]}</span>
            </button>
          ))}
        </div>
        {query.trim() && (
          <p className="text-[11px] text-slate-500 dark:text-slate-400">Searching all stages</p>
        )}
      </div>

      <ul className="space-y-2 p-3 overflow-y-auto flex-1">
        {filteredClaims.length === 0 ? (
          <li className="p-8 text-slate-500 dark:text-slate-400 text-sm text-center font-medium">
            {query
              ? `No claims matching "${query}"`
              : STAGES.find((st) => st.key === activeTab)?.key === "todo"
                ? "Nothing needs you right now."
                : "No claims in this stage."}
          </li>
        ) : (
          filteredClaims.map((claim) => {
            const preview = claim._preview ?? {};
            const isSelected = claim.id === selectedId;
            const dotColor = preview.color ?? "red";
            const dotClass = LIST_DOT_CLASSES[dotColor] ?? LIST_DOT_CLASSES.red;
            const badgeClass = LIST_BADGE_CLASSES[dotColor] ?? LIST_BADGE_CLASSES.red;

            return (
              <li key={claim.id}>
                <button
                  type="button"
                  onClick={() => onSelect(claim.id, claim)}
                  className={`w-full text-left p-3.5 rounded-xl border transition-all duration-200 block shadow-sm ${
                    isSelected
                      ? "bg-teal-50/50 dark:bg-teal-950/25 border-teal-500 ring-1 ring-teal-500/50"
                      : "bg-white dark:bg-slate-950 border-slate-200 dark:border-slate-800 hover:border-slate-300 dark:hover:border-slate-800 hover:bg-slate-50/50 dark:hover:bg-slate-900/50 active:bg-slate-50 dark:active:bg-slate-900"
                  }`}
                >
                  <div className="flex items-start gap-3">
                    <span className={`mt-1.5 w-2 h-2 rounded-full flex-shrink-0 ${dotClass}`} />
                    <div className="flex-1 min-w-0">
                      <p className={`text-sm font-semibold truncate ${isSelected ? "text-teal-900 dark:text-teal-300" : "text-slate-800 dark:text-slate-200"}`}>
                        {highlightMatch(claim.patient_name || "Unknown Patient", query)}
                      </p>
                      <p className="text-xs text-slate-500 dark:text-slate-400 font-medium truncate mt-0.5">
                        {highlightMatch(claim.facility_name || "", query)}
                      </p>
                      <div className="flex flex-wrap items-center gap-x-1.5 gap-y-1 mt-2">
                        <span className="text-[10px] whitespace-nowrap bg-slate-100 dark:bg-slate-900 text-slate-600 dark:text-slate-400 font-semibold px-1.5 py-0.5 rounded border dark:border-slate-800">
                          {highlightMatch(claim.id || "", query)}
                        </span>
                        <span className="text-[10px] whitespace-nowrap text-slate-500 dark:text-slate-400 font-medium">{claim.visit_date}</span>
                        <span className="text-[10px] whitespace-nowrap text-slate-500 dark:text-slate-400 font-mono" title="SHA number (masked)">
                          {maskId(claim.patient_id)}
                        </span>
                      </div>
                    </div>
                    <div className="flex flex-col items-end gap-1 flex-shrink-0">
                      {preview.score !== undefined && (
                        <span className={`text-xs font-bold rounded-lg px-2 py-1 shadow-sm border ${badgeClass}`}>
                          {preview.score}
                        </span>
                      )}
                      <ShaStateBadge state={claim._sha_state} compact />
                      {query.trim() && (
                        <span className="text-[9px] font-bold uppercase tracking-wider text-slate-600 dark:text-slate-300">
                          {STAGES.find((st) => st.key === (claim._stage ?? stageOf(claim)))?.label}
                        </span>
                      )}
                      {claim._status === "handed_off" && !claim._sha_state && (
                        <span className="text-[9px] font-bold uppercase tracking-wider text-teal-700 dark:text-teal-400">
                          Handed off
                        </span>
                      )}
                    </div>
                  </div>
                </button>
              </li>
            );
          })
        )}
      </ul>
    </div>
  );
}

ClaimList.propTypes = {
  claims: PropTypes.arrayOf(PropTypes.object).isRequired,
  loading: PropTypes.bool,
  selectedId: PropTypes.string,
  onSelect: PropTypes.func.isRequired,
};
