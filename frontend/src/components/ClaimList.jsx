import { useState, useEffect, useMemo } from "react";
import PropTypes from "prop-types";
import { LIST_DOT_CLASSES } from "../constants/status.js";
import { DEPARTMENT_REVIEW_UPDATED, readDepartmentReview } from "../utils/departmentReview.js";
import { getOverallStatus } from "../utils/overallStatus.js";

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

function getClaimOverallStatus(claim, departmentReviews) {
  return getOverallStatus(
    { ...(claim._preview || {}), department: claim.department },
    departmentReviews[claim.id] || readDepartmentReview(claim.id, claim.department),
  );
}

export default function ClaimList({ claims: claimsProp, loading, privacyMode, selectedId, onSelect, onCountsChange }) {
  const [query, setQuery] = useState("");
  const [activeTab, setActiveTab] = useState("all");
  const [activeDepartment, setActiveDepartment] = useState("all");
  const [departmentReviews, setDepartmentReviews] = useState({});

  const sourceClaims = useMemo(() => claimsProp ?? [], [claimsProp]);

  useEffect(() => {
    setDepartmentReviews(Object.fromEntries(sourceClaims.map((claim) => [
      claim.id,
      readDepartmentReview(claim.id, claim.department),
    ])));
  }, [sourceClaims]);

  useEffect(() => {
    const refreshDepartmentReview = (event) => {
      const { claimId, department } = event.detail || {};
      if (!claimId) return;
      setDepartmentReviews((reviews) => ({
        ...reviews,
        [claimId]: readDepartmentReview(claimId, department),
      }));
    };
    window.addEventListener(DEPARTMENT_REVIEW_UPDATED, refreshDepartmentReview);
    return () => window.removeEventListener(DEPARTMENT_REVIEW_UPDATED, refreshDepartmentReview);
  }, []);

  useEffect(() => {
    onCountsChange?.({
      total: sourceClaims.length,
      ready: sourceClaims.filter((claim) => getClaimOverallStatus(claim, departmentReviews).status === "green").length,
      review: sourceClaims.filter((claim) => getClaimOverallStatus(claim, departmentReviews).status === "amber").length,
      errors: sourceClaims.filter((claim) => getClaimOverallStatus(claim, departmentReviews).status === "red").length,
    });
  }, [departmentReviews, onCountsChange, sourceClaims]);

  // Filter in memory — no API call, instant
  const filteredClaims = useMemo(() => {
    let result = sourceClaims;

    if (activeDepartment !== "all") {
      result = result.filter((c) => (c.department || "unassigned").toLowerCase() === activeDepartment);
    }

    // Tab filter
    if (activeTab === "ready") {
      result = result.filter((claim) => getClaimOverallStatus(claim, departmentReviews).status === "green");
    } else if (activeTab === "review") {
      result = result.filter((claim) => getClaimOverallStatus(claim, departmentReviews).status === "amber");
    } else if (activeTab === "error") {
      result = result.filter((claim) => getClaimOverallStatus(claim, departmentReviews).status === "red");
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
  }, [sourceClaims, query, activeTab, activeDepartment, departmentReviews]);

  if (loading && sourceClaims.length === 0) {
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
      <div className="space-y-2 border-b border-slate-200 p-2.5 dark:border-slate-800">
        <input
          type={privacyMode ? "password" : "text"}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Search claims"
          placeholder="Search patient or ID..."
          className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder-slate-500 outline-none focus-visible:ring-2 focus-visible:ring-teal-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:placeholder-slate-400"
        />
        <div className="flex min-w-0 items-center gap-1.5">
          <select id="claims-department-filter" aria-label="Filter by department" value={activeDepartment} onChange={(e) => setActiveDepartment(e.target.value)} className="w-28 shrink-0 rounded-md border border-slate-300 bg-white px-2 py-2 text-[11px] font-semibold text-slate-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-teal-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100">
            <option value="all">All depts</option><option value="outpatient">Outpatient</option><option value="maternity">Maternity</option><option value="renal">Renal</option><option value="surgical">Surgical</option>
          </select>
          <div className="flex shrink-0 items-center rounded-md border border-slate-300 bg-slate-100 p-0.5 dark:border-slate-700 dark:bg-slate-900" role="group" aria-label="Filter claims by overall status">
          {["all", "ready", "review", "error"].map((tab) => (
            <button
              key={tab}
              type="button"
              onClick={() => setActiveTab(tab)}
              aria-pressed={activeTab === tab}
              className={`min-w-8 rounded px-1.5 py-1.5 text-[9px] font-bold uppercase transition-colors ${
                activeTab === tab
                  ? "bg-teal-800 text-white dark:bg-teal-700"
                  : "text-slate-700 hover:bg-white dark:text-slate-300 dark:hover:bg-slate-800"
              }`}
            >
              {tab}
            </button>
          ))}
          </div>
        </div>
      </div>

      <ul className="flex-1 space-y-1 overflow-y-auto p-1.5">
        {filteredClaims.length === 0 ? (
          <li className="p-8 text-slate-500 dark:text-slate-400 text-sm text-center font-medium">
            {query ? `No claims matching "${privacyMode ? "********" : query}"` : "No claims found."}
          </li>
        ) : (
          filteredClaims.map((claim) => {
            const preview = claim._preview ?? {};
            const isSelected = claim.id === selectedId;
            const overallStatus = getClaimOverallStatus(claim, departmentReviews);
            const dotColor = overallStatus.status;
            const dotClass = LIST_DOT_CLASSES[dotColor] ?? LIST_DOT_CLASSES.red;

            return (
              <li key={claim.id}>
                <button
                  type="button"
                  onClick={() => onSelect(claim.id, claim)}
                  className={`block w-full rounded-md border px-2 py-1.5 text-left transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-teal-700 ${
                    isSelected
                      ? "border-teal-700 bg-teal-50 dark:border-teal-500 dark:bg-teal-950/40"
                      : "border-transparent bg-white hover:border-slate-300 hover:bg-slate-50 dark:bg-slate-950 dark:hover:border-slate-700 dark:hover:bg-slate-900"
                  }`}
                >
                  <div className="flex min-w-0 items-center gap-2">
                      <span aria-label={overallStatus.label} title={overallStatus.label} className={`h-2 w-2 shrink-0 rounded-full ${dotClass}`} />
                      <p className={`min-w-0 flex-1 truncate text-xs font-semibold ${isSelected ? "text-teal-900 dark:text-teal-100" : "text-slate-900 dark:text-slate-100"}`}>
                        {privacyMode ? "********" : highlightMatch(claim.patient_name || "Unknown Patient", query)}
                      </p>
                      {preview.score !== undefined && <span className="shrink-0 text-[10px] font-semibold text-slate-700 dark:text-slate-200" aria-label={`Automated score ${preview.score}`}>{preview.score}/100</span>}
                  </div>
                  <div className="ml-4 mt-0.5 flex min-w-0 items-center gap-2 text-[10px] leading-4 text-slate-700 dark:text-slate-300">
                    <span className="shrink-0 font-semibold uppercase">{claim.department || "unassigned"}</span>
                    <span aria-hidden="true">·</span>
                    <span className="truncate font-mono">{privacyMode ? "********" : highlightMatch(claim.id || "", query)}</span>
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
  claims: PropTypes.arrayOf(PropTypes.object),
  loading: PropTypes.bool,
  privacyMode: PropTypes.bool,
  selectedId: PropTypes.string,
  onSelect: PropTypes.func.isRequired,
  onCountsChange: PropTypes.func,
};
