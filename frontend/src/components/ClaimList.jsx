import { useState, useEffect, useCallback } from "react";
import { api } from "../api/client.js";

const DOT_STYLES = {
  green: "bg-emerald-500",
  amber: "bg-amber-500",
  red:   "bg-rose-500",
};

export default function ClaimList({ selectedId, onSelect, onCountsChange }) {
  const [claims, setClaims] = useState([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [activeTab, setActiveTab] = useState("all");
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);

  const fetchClaims = useCallback(async () => {
    setLoading(true);
    try {
      // Debug: Check what we are sending to the API
      console.log("ClaimList: Fetching with params:", { query, activeTab, page });
      
      const data = await api.getClaims({
        q: query,
        status: activeTab,
        page,
        page_size: 20,
      });
      
      console.log("ClaimList: API Response:", data);
      setClaims(data.claims ?? []);
      setTotal(data.count ?? 0);
      setTotalPages(data.total_pages ?? 1);

      if (onCountsChange && activeTab === "all" && !query) {
        onCountsChange({ 
          total: data.count, 
          ready: (data.claims ?? []).filter(c => c._preview?.color === "green").length,
          review: (data.claims ?? []).filter(c => c._preview?.color === "amber").length,
          errors: (data.claims ?? []).filter(c => c._preview?.color === "red").length
        });
      }
    } catch (err) {
      console.error("ClaimList: Failed to load:", err);
    } finally {
      setLoading(false);
    }
  }, [query, activeTab, page, onCountsChange]);

  useEffect(() => {
    const timer = setTimeout(() => {
      setPage(1);
      fetchClaims();
    }, 300);
    return () => clearTimeout(timer);
  }, [query, fetchClaims]);

  useEffect(() => {
    fetchClaims();
  }, [activeTab, page, fetchClaims]);

  return (
    <div className="flex flex-col h-full bg-white">
      {/* Search Bar - Clean, Professional Styling */}
      <div className="px-4 py-3 border-b border-slate-100">
        <div className="relative">
          <input
            type="text"
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="Search patient or ID..."
            className="w-full bg-slate-50 border border-slate-200 rounded-lg pl-3 pr-8 py-2 text-xs text-slate-700 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-teal-500/20 focus:border-teal-500 transition-all"
          />
        </div>
      </div>

      {/* Tabs - Clearer visibility */}
      <div className="flex border-b border-slate-100">
        {["all", "ready", "review", "error"].map((tab) => (
          <button
            key={tab}
            onClick={() => { setActiveTab(tab); setPage(1); }}
            className={`flex-1 py-2.5 text-[10px] font-bold uppercase tracking-wider transition-colors ${
              activeTab === tab
                ? "text-teal-700 border-b-2 border-teal-600 bg-teal-50/50"
                : "text-slate-400 hover:text-slate-600"
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* List */}
      <ul className="flex-1 overflow-y-auto divide-y divide-slate-50">
        {loading ? (
          // Professional, Subtle Skeleton Loader
          [...Array(6)].map((_, i) => (
            <li key={i} className="px-5 py-4 animate-pulse">
              <div className="h-4 bg-slate-100 rounded w-3/4 mb-2"></div>
              <div className="h-3 bg-slate-50 rounded w-1/2"></div>
            </li>
          ))
        ) : claims.length === 0 ? (
          <li className="px-5 py-8 text-center text-slate-400 text-xs">No claims found.</li>
        ) : (
          claims.map(claim => (
            <li key={claim.id}>
              <button
                onClick={() => onSelect(claim.id, claim)}
                className={`w-full text-left px-5 py-4 transition-colors hover:bg-slate-50 ${
                  claim.id === selectedId ? "bg-teal-50 border-l-4 border-teal-600" : "border-l-4 border-transparent"
                }`}
              >
                <div className="flex items-center justify-between">
                  <p className="text-sm font-bold text-slate-800">{claim.patient_name}</p>
                  <span className={`w-2 h-2 rounded-full ${DOT_STYLES[claim._preview?.color] ?? 'bg-slate-300'}`} />
                </div>
                <p className="text-xs text-slate-500 mt-0.5">{claim.id}</p>
              </button>
            </li>
          ))
        )}
      </ul>
    </div>
  );
}
