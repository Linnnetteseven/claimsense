import { useState, useEffect, useCallback } from "react";
import PropTypes from "prop-types";
import { api } from "../api/client.js";
import { LIST_BADGE_CLASSES, LIST_DOT_CLASSES } from "../constants/status.js";

// Highlight matching text in search results
const highlightMatch = (text, query) => {
  if (!query || !text) return text;
  const parts = text.split(new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi'));
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
  const [claims, setClaims] = useState([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [activeTab, setActiveTab] = useState("all");

  // fetchClaims takes q and tab as params — NOT closed over in useCallback deps
  // This keeps the reference stable so effects don't double-fire
  const fetchClaims = useCallback(async (q, tab) => {
    setLoading(true);
    try {
      const data = await api.getClaims({ q, status: tab });
      const fetched = data.claims ?? [];
      setClaims(fetched);
      if (onCountsChange) {
        onCountsChange({
          total: data.count,
          ready: fetched.filter((c) => c._preview?.color === "green").length,
          review: fetched.filter((c) => c._preview?.color === "amber").length,
          errors: fetched.filter((c) => c._preview?.color === "red").length,
        });
      }
    } catch (err) {
      console.error("Failed to fetch claims:", err);
      setClaims([]);
    } finally {
      setLoading(false);
    }
  }, [onCountsChange]); // stable — only changes if parent passes a new onCountsChange

  // Single effect handles both search (debounced) and tab changes
  useEffect(() => {
    const timer = setTimeout(() => {
      fetchClaims(query, activeTab);
    }, 300);
    return () => clearTimeout(timer);
  }, [query, activeTab, fetchClaims]);

  return (
    <div className="flex flex-col h-full">
      {/* Search and Triage Interface */}
      <div className="p-3 space-y-2">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search patient or ID..."
          className="w-full text-sm p-2.5 border border-slate-200 rounded-xl shadow-sm focus:ring-2 focus:ring-teal-500/20 focus:border-teal-500 outline-none"
        />
        <div className="flex bg-slate-100 p-1 rounded-lg">
          {["all", "ready", "review", "error"].map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`flex-1 py-1.5 text-[10px] font-bold uppercase rounded-md transition-all ${
                activeTab === tab ? "bg-white shadow-sm text-slate-800" : "text-slate-500 hover:text-slate-700"
              }`}
            >
              {tab}
            </button>
          ))}
        </div>
      </div>

      {/* Claims List */}
      <ul className="space-y-2 p-3 overflow-y-auto flex-1">
        {loading ? (
          [...Array(5)].map((_, i) => (
            <li key={i} className="h-20 bg-slate-100 border border-slate-200/60 rounded-xl animate-pulse" />
          ))
        ) : claims.length === 0 ? (
          <li className="p-8 text-slate-400 text-sm text-center font-medium">
            {query ? `No claims matching "${query}"` : "No claims found."}
          </li>
        ) : (
          claims.map((claim) => {
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
                      ? "bg-teal-50/50 border-teal-500 ring-1 ring-teal-500/50"
                      : "bg-white border-slate-200 hover:border-slate-300 hover:bg-slate-50/50 active:bg-slate-50"
                  }`}
                >
                  <div className="flex items-start gap-3">
                    <span className={`mt-1.5 w-2 h-2 rounded-full flex-shrink-0 ${dotClass}`} />
                    <div className="flex-1 min-w-0">
                      <p className={`text-sm font-semibold truncate ${isSelected ? "text-teal-900" : "text-slate-800"}`}>
                        {highlightMatch(claim.patient_name || "Unknown Patient", query)}
                      </p>
                      <p className="text-xs text-slate-500 font-medium truncate mt-0.5">
                        {highlightMatch(claim.facility_name || "", query)}
                      </p>
                      <div className="flex items-center gap-1.5 mt-2">
                        <span className="text-[10px] bg-slate-100 text-slate-600 font-semibold px-1.5 py-0.5 rounded">
                          {highlightMatch(claim.id || "", query)}
                        </span>
                        <span className="text-[10px] text-slate-400 font-medium">{claim.visit_date}</span>
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
