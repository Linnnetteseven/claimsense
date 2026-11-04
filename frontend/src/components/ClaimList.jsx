import { useState, useEffect, useMemo } from "react";
import PropTypes from "prop-types";
import { LIST_BADGE_CLASSES, LIST_DOT_CLASSES } from "../constants/status.js";
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
      <div className="p-3 space-y-3 border-b border-slate-100 dark:border-slate-800">
        <input
          type={privacyMode ? "password" : "text"}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Search claims"
          placeholder="Search patient or ID..."
          className="w-full text-sm px-3 py-2.5 border border-slate-200 dark:border-slate-800 rounded-lg bg-white dark:bg-slate-900 text-slate-800 dark:text-slate-100 placeholder-slate-400 dark:placeholder-slate-500 focus:ring-2 focus:ring-teal-500/20 focus:border-teal-500 outline-none"
        />
        <label className="block text-xs font-bold uppercase text-slate-600 dark:text-slate-300">
          Filter by department
          <select value={activeDepartment} onChange={(e) => setActiveDepartment(e.target.value)} className="mt-1 w-full text-sm normal-case font-medium px-3 py-2.5 border border-slate-200 dark:border-slate-800 rounded-lg bg-white dark:bg-slate-900 text-slate-800 dark:text-slate-100">
            <option value="all">All departments</option>
            <option value="outpatient">Outpatient</option>
            <option value="maternity">Maternity</option>
            <option value="renal">Renal Unit</option>
            <option value="surgical">Surgical</option>
          </select>
        </label>
        <div className="flex bg-slate-100 dark:bg-slate-900/60 p-1 rounded-lg border border-slate-200 dark:border-slate-800" role="group" aria-label="Filter claims by overall status">
          {["all", "ready", "review", "error"].map((tab) => (
            <button
              key={tab}
              type="button"
              onClick={() => setActiveTab(tab)}
              aria-pressed={activeTab === tab}
              className={`flex-1 py-1.5 text-xs font-bold uppercase rounded-md transition-all ${
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
            {query ? `No claims matching "${privacyMode ? "********" : query}"` : "No claims found."}
          </li>
        ) : (
          filteredClaims.map((claim) => {
            const preview = claim._preview ?? {};
            const isSelected = claim.id === selectedId;
            const overallStatus = getClaimOverallStatus(claim, departmentReviews);
            const dotColor = overallStatus.status;
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
                  <div className="space-y-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className={`w-2 h-2 rounded-full flex-shrink-0 ${dotClass}`} />
                      <p className={`text-sm font-semibold truncate flex-1 min-w-0 ${isSelected ? "text-teal-900 dark:text-teal-350" : "text-slate-800 dark:text-slate-200"}`}>
                        {privacyMode ? "********" : highlightMatch(claim.patient_name || "Unknown Patient", query)}
                      </p>
                      {preview.score !== undefined && (
                        <span className="text-xs font-semibold text-slate-600 dark:text-slate-300 shrink-0" aria-label={`Automated score ${preview.score}`}>
                          Score {preview.score}
                        </span>
                      )}
                    </div>
                    <p className="pl-4 text-xs text-slate-500 dark:text-slate-400 font-medium truncate">
                      {highlightMatch(claim.facility_name || "", query)}
                    </p>
                    <div className="pl-4 flex flex-wrap items-center gap-x-2 gap-y-1">
                      {claim.is_synthetic && (
                        <span className="text-[10px] font-bold uppercase tracking-wide text-amber-700 dark:text-amber-300 bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-900 rounded px-1.5 py-0.5">
                          Synthetic demo data
                        </span>
                      )}
                      <span className="text-xs text-teal-700 dark:text-teal-400 font-semibold uppercase">
                        {claim.department || "unassigned"}
                      </span>
                      <span className="max-w-full truncate text-xs bg-slate-100 dark:bg-slate-900 text-slate-700 dark:text-slate-300 font-semibold px-1.5 py-0.5 rounded border border-slate-200 dark:border-slate-800">
                        {privacyMode ? "********" : highlightMatch(claim.id || "", query)}
                      </span>
                      <span className="text-xs text-slate-600 dark:text-slate-300 font-medium">{privacyMode ? "********" : claim.visit_date}</span>
                    </div>
                    <div className="pl-4">
                      <span className={`inline-flex max-w-full whitespace-normal break-words text-left text-xs font-bold rounded-md px-2 py-1 border leading-tight ${badgeClass}`} title={overallStatus.reason}>
                        {overallStatus.label}
                      </span>
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
  claims: PropTypes.arrayOf(PropTypes.object),
  loading: PropTypes.bool,
  privacyMode: PropTypes.bool,
  selectedId: PropTypes.string,
  onSelect: PropTypes.func.isRequired,
  onCountsChange: PropTypes.func,
};
