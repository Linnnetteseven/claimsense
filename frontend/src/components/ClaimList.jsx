import { useState, useMemo } from "react";
import PropTypes from "prop-types";
import { LIST_BADGE_CLASSES, LIST_DOT_CLASSES } from "../constants/status.js";

/**
 * Left sidebar: scrollable queue of claims styled as a clean light-mode card list.
 * Now with instant real-time search and triage filtering.
 */
export default function ClaimList({ claims, selectedId, onSelect, loading }) {
  const [query, setQuery] = useState("");
  const [activeTab, setActiveTab] = useState("all"); // all | ready | review | error

  // This filters the list instantly as you type
  const filteredClaims = useMemo(() => {
    let items = claims;

    // Filter by Tab (Mapping color keys to your status system)
    if (activeTab !== "all") {
      const colorMap = { ready: "green", review: "amber", error: "red" };
      items = items.filter((c) => c._preview?.color === colorMap[activeTab]);
    }

    // Filter by Search Query
    if (query) {
      const q = query.toLowerCase();
      items = items.filter(
        (c) =>
          c.patient_name?.toLowerCase().includes(q) ||
          c.id?.toLowerCase().includes(q) ||
          c.facility_name?.toLowerCase().includes(q)
      );
    }
    return items;
  }, [claims, query, activeTab]);

  if (loading) {
    return (
      <div className="space-y-3 p-4" aria-busy="true" aria-label="Loading claims">
        {[...Array(5)].map((_, i) => (
          <div key={i} className="h-20 bg-slate-100 border border-slate-200/60 rounded-xl animate-pulse" />
        ))}
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Search Input - Kept clean to match your design */}
      <div className="p-3">
        <input
          type="text"
          placeholder="Search claims..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="w-full px-4 py-2 text-sm border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-teal-500/20 focus:border-teal-500 transition-all"
        />
      </div>

      {/* Triage Tabs - Integrated to match your button styling */}
      <div className="px-3 pb-2 flex gap-1">
        {["all", "ready", "review", "error"].map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`flex-1 text-[10px] font-bold uppercase py-1.5 rounded-lg transition-colors ${
              activeTab === tab
                ? "bg-teal-600 text-white"
                : "bg-slate-100 text-slate-500 hover:bg-slate-200"
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

      <ul className="space-y-2 p-3 overflow-y-auto flex-1">
        {!filteredClaims.length ? (
          <div className="p-8 text-slate-400 text-sm text-center font-medium">No records found.</div>
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
                  onClick={() => onSelect(claim.id)}
                  aria-current={isSelected ? "true" : undefined}
                  className={`w-full text-left p-3.5 rounded-xl border transition-all duration-200 block shadow-sm ${
                    isSelected
                      ? "bg-teal-50/50 border-teal-500 ring-1 ring-teal-500/50"
                      : "bg-white border-slate-200 hover:border-slate-300 hover:bg-slate-50/50 active:bg-slate-50"
                  }`}
                >
                  <div className="flex items-start gap-3">
                    <span className={`mt-1.5 w-2 h-2 rounded-full flex-shrink-0 ${dotClass}`} aria-hidden="true" />
                    
                    <div className="flex-1 min-w-0">
                      <p className={`text-sm font-semibold truncate ${isSelected ? "text-teal-900" : "text-slate-800"}`}>
                        {claim.patient_name || "Unknown Patient"}
                      </p>
                      <p className="text-xs text-slate-500 font-medium truncate mt-0.5">
                        {claim.facility_name || "Unknown Facility"}
                      </p>
                      
                      <div className="flex items-center gap-1.5 mt-2">
                        <span className="text-[10px] bg-slate-100 text-slate-600 font-semibold px-1.5 py-0.5 rounded">
                          {claim.id}
                        </span>
                        <span className="text-[10px] text-slate-400 font-medium">
                          {claim.visit_date}
                        </span>
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
  claims: PropTypes.arrayOf(
    PropTypes.shape({
      id: PropTypes.string.isRequired,
      patient_name: PropTypes.string,
      facility_name: PropTypes.string,
      visit_date: PropTypes.string,
      _preview: PropTypes.shape({
        score: PropTypes.number,
        color: PropTypes.string,
      }),
    })
  ).isRequired,
  selectedId: PropTypes.string,
  onSelect: PropTypes.func.isRequired,
  loading: PropTypes.bool,
};
