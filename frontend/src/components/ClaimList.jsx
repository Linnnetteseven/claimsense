import { useState, useEffect, useCallback, useMemo } from "react";
import PropTypes from "prop-types";
import { api } from "../api/client.js";
import { LIST_BADGE_CLASSES, LIST_DOT_CLASSES } from "../constants/status.js";

const highlightMatch = (text, query) => {
  if (!query || !text) return text;
  const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const parts = text.split(new RegExp(`(${escaped})`, 'gi'));
  return (
    <>
      {parts.map((part, i) =>
        part.toLowerCase() === query.toLowerCase()
          ? <span key={i} className="bg-teal-200 font-bold rounded-sm">{part}</span>
          : part
      )}
    </>
  );
};

export default function ClaimList({ selectedId, onSelect, onCountsChange }) {
  const [allClaims, setAllClaims] = useState([]);  // source of truth — never touched after fetch
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [activeTab, setActiveTab] = useState("all");

  // Fetch ONCE on mount
  const fetchClaims = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.getClaims({ q: "", status: "all" });
      const fetched = data.claims ?? [];
      setAllClaims(fetched);
      if (onCountsChange) {
        onCountsChange({
          total: fetched.length,
          ready: fetched.filter((c) => c._preview?.color === "green").length,
          review: fetched.filter((c) => c._preview?.color === "amber").length,
          errors: fetched.filter((c) => c._preview?.color === "red").length,
        });
      }
    } catch (err) {
      console.error("Failed to fetch claims:", err);
      setAllClaims([]);
    } finally {
      setLoading(false);
    }
  }, [onCountsChange]);

  useEffect(() => {
    fetchClaims();
  }, [fetchClaims]);

  // Filter in memory — no API call, instant
  const filteredClaims = useMemo(() => {
    let result = allClaims;

    // Tab filter
    if (activeTab === "ready") {
      result = result.filter((c) => c._preview?.color === "green");
    } else if (activeTab === "review") {
      result = result.filter((c) => c._preview?.color === "amber");
    } else if (activeTab === "error") {
      result = result.filter((c) => c._preview?.color === "red");
    }

    // Search filter
    if (query.trim()) {
      const q = query.trim().toLowerCase();
      result = result.filter(
        (c) =>
          c.patient_name?.toLowerCase().includes(q) ||
          c.id?.toLowerCase().includes(q) ||
          c.facility_name?.toLowerCase().includes(q)
      );
    }

    return result;
  }, [allClaims, query, activeTab]);

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
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search patient or ID..."
          className="w-full text-sm p-2.5 border border-slate-200 dark:border-slate-800 rounded-xl shadow-sm bg-white dark:bg-slate-900 text-slate-800 dark:text-slate-100 placeholder-slate-400 dark:placeholder-slate-500 focus:ring-2 focus:ring-teal-500/20 focus:border-teal-500 outline-none"
        />
        <div className="flex bg-slate-100 dark:bg-slate-900/60 p-1 rounded-lg border dark:border-slate-800">
          {["all", "ready", "review", "error"].map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`flex-1 py-1.5 text-[10px] font-bold uppercase rounded-md transition-all ${
                activeTab === tab
                  ? "bg-white dark:bg-slate-800 shadow-sm text-slate-800 dark:text-slate-100"
                  : "text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-300"
              }`}
            >
              {tab}
            </button>
          ))}
        </div>
      </div>

      <ul className="space-y-2 p-3 overflow-y-auto flex-1">
        {filteredClaims.length === 0 ? (
          <li className="p-8 text-slate-400 dark:text-slate-500 text-sm text-center font-medium">
            {query ? `No claims matching "${query}"` : "No claims found."}
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
                      : "bg-white dark:bg-slate-950 border-slate-200 dark:border-slate-850 hover:border-slate-300 dark:hover:border-slate-800 hover:bg-slate-50/50 dark:hover:bg-slate-900/50 active:bg-slate-50 dark:active:bg-slate-900"
                  }`}
                >
                  <div className="flex items-start gap-3">
                    <span className={`mt-1.5 w-2 h-2 rounded-full flex-shrink-0 ${dotClass}`} />
                    <div className="flex-1 min-w-0">
                      <p className={`text-sm font-semibold truncate ${isSelected ? "text-teal-900 dark:text-teal-350" : "text-slate-800 dark:text-slate-200"}`}>
                        {highlightMatch(claim.patient_name || "Unknown Patient", query)}
                      </p>
                      <p className="text-xs text-slate-500 dark:text-slate-400 font-medium truncate mt-0.5">
                        {highlightMatch(claim.facility_name || "", query)}
                      </p>
                      <div className="flex items-center gap-1.5 mt-2">
                        <span className="text-[10px] bg-slate-100 dark:bg-slate-900 text-slate-600 dark:text-slate-400 font-semibold px-1.5 py-0.5 rounded border dark:border-slate-800">
                          {highlightMatch(claim.id || "", query)}
                        </span>
                        <span className="text-[10px] text-slate-400 dark:text-slate-500 font-medium">{claim.visit_date}</span>
                      </div>
                    </div>
                    {preview.score !== undefined && (
                      <span className={`flex-shrink-0 text-xs font-bold rounded-lg px-2 py-1 shadow-sm border ${badgeClass}`}>
                        {preview.score}
                      </span>
                    )}
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
  selectedId: PropTypes.string,
  onSelect: PropTypes.func.isRequired,
  onCountsChange: PropTypes.func,
};
