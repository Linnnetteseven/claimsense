/**
 * Left sidebar claim queue with:
 * - Search bar (patient name, ID, facility)
 * - Triage tabs: All | Ready | Review | Errors
 * - Paginated claim rows with color-coded scores
 */
import { useState, useEffect, useCallback } from "react";
import { api } from "../api/client.js";

const TABS = [
  { key: "all",    label: "All",    dot: null },
  { key: "ready",  label: "Ready",  dot: "bg-emerald-500" },
  { key: "review", label: "Review", dot: "bg-amber-500" },
  { key: "error",  label: "Errors", dot: "bg-red-500" },
];

const SCORE_STYLES = {
  green: "bg-emerald-900 text-emerald-300",
  amber: "bg-amber-900 text-amber-300",
  red:   "bg-red-900 text-red-300",
};

const DOT_STYLES = {
  green: "bg-emerald-400",
  amber: "bg-amber-400",
  red:   "bg-red-400",
};

export default function ClaimList({ selectedId, onSelect, onCountsChange }) {
  const [claims, setClaims]     = useState([]);
  const [loading, setLoading]   = useState(true);
  const [query, setQuery]       = useState("");
  const [activeTab, setActiveTab] = useState("all");
  const [page, setPage]         = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal]       = useState(0);

  const fetchClaims = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.getClaims({
        q: query,
        status: activeTab,
        page,
        page_size: 20,
      });
      setClaims(data.claims ?? []);
      setTotal(data.count ?? 0);
      setTotalPages(data.total_pages ?? 1);

      // Bubble counts up to App for the header stats
      if (onCountsChange && activeTab === "all" && !query) {
        const ready  = (data.claims ?? []).filter(c => c._preview?.color === "green").length;
        const review = (data.claims ?? []).filter(c => c._preview?.color === "amber").length;
        const errors = (data.claims ?? []).filter(c => c._preview?.color === "red").length;
        onCountsChange({ total: data.count, ready, review, errors });
      }
    } catch (err) {
      console.error("Failed to load claims:", err);
    } finally {
      setLoading(false);
    }
  }, [query, activeTab, page, onCountsChange]);

  // Debounce search — wait 300ms after user stops typing
  useEffect(() => {
    const timer = setTimeout(() => {
      setPage(1);
      fetchClaims();
    }, 300);
    return () => clearTimeout(timer);
  }, [query]);

  // Immediate fetch on tab or page change
  useEffect(() => {
    fetchClaims();
  }, [activeTab, page]);

  return (
    <div className="flex flex-col h-full">
      {/* Search input */}
      <div className="px-3 pt-3 pb-2 flex-shrink-0">
        <div className="relative">
          <svg
            className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-500"
            fill="none" viewBox="0 0 24 24" stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            type="text"
            value={query}
            onChange={e => { setQuery(e.target.value); setPage(1); }}
            placeholder="Search patient, ID, facility…"
            className="w-full bg-slate-800 border border-slate-700 rounded-lg pl-8 pr-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-teal-500 focus:border-teal-500"
          />
          {query && (
            <button
              onClick={() => setQuery("")}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300"
            >
              ✕
            </button>
          )}
        </div>
      </div>

      {/* Triage tabs */}
      <div className="flex border-b border-slate-800 flex-shrink-0">
        {TABS.map(tab => (
          <button
            key={tab.key}
            onClick={() => { setActiveTab(tab.key); setPage(1); }}
            className={`flex-1 py-2 text-xs font-semibold flex items-center justify-center gap-1 transition-colors ${
              activeTab === tab.key
                ? "text-teal-400 border-b-2 border-teal-400"
                : "text-slate-500 hover:text-slate-300"
            }`}
          >
            {tab.dot && <span className={`w-1.5 h-1.5 rounded-full ${tab.dot}`} />}
            {tab.label}
          </button>
        ))}
      </div>

      {/* Result count */}
      {!loading && (
        <div className="px-4 py-1.5 text-[10px] text-slate-500 flex-shrink-0">
          {total} claim{total !== 1 ? "s" : ""}
          {query && ` matching "${query}"`}
        </div>
      )}

      {/* Claims list */}
      <ul className="flex-1 overflow-y-auto divide-y divide-slate-800">
        {loading ? (
          [...Array(5)].map((_, i) => (
            <li key={i} className="px-4 py-3">
              <div className="h-3 bg-slate-800 rounded animate-pulse mb-2 w-3/4" />
              <div className="h-2 bg-slate-800 rounded animate-pulse w-1/2" />
            </li>
          ))
        ) : claims.length === 0 ? (
          <li className="px-4 py-8 text-center text-slate-500 text-xs">
            {query ? `No claims matching "${query}"` : "No claims in this category"}
          </li>
        ) : (
          claims.map(claim => {
            const preview = claim._preview ?? {};
            const isSelected = claim.id === selectedId;
            const dot = DOT_STYLES[preview.color] ?? DOT_STYLES.red;
            const score = SCORE_STYLES[preview.color] ?? SCORE_STYLES.red;

            return (
              <li key={claim.id}>
                <button
                  onClick={() => onSelect(claim.id, claim)}
                  className={`w-full text-left px-4 py-3 transition-colors ${
                    isSelected ? "bg-teal-700" : "hover:bg-slate-800 active:bg-slate-700"
                  }`}
                >
                  <div className="flex items-start gap-3">
                    <span className={`mt-1.5 w-2 h-2 rounded-full flex-shrink-0 ${dot}`} />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-semibold text-white truncate">
                        {claim.patient_name}
                      </p>
                      <p className="text-xs text-slate-400 truncate">{claim.facility_name}</p>
                      <p className="text-xs text-slate-500 mt-0.5">
                        {claim.visit_date} · <span className="font-mono">{claim.id}</span>
                      </p>
                    </div>
                    {preview.score !== undefined && (
                      <span className={`flex-shrink-0 text-xs font-bold rounded-full w-8 h-8 flex items-center justify-center ${score}`}>
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

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between px-4 py-2 border-t border-slate-800 flex-shrink-0">
          <button
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page === 1}
            className="text-xs text-slate-400 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed"
          >
            ← Prev
          </button>
          <span className="text-xs text-slate-500">
            {page} / {totalPages}
          </span>
          <button
            onClick={() => setPage(p => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
            className="text-xs text-slate-400 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed"
          >
            Next →
          </button>
        </div>
      )}
    </div>
  );
}
