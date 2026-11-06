import { useState, useEffect, useRef, useMemo } from "react";
import ClaimList from "./components/ClaimList.jsx";
import ValidationPanel from "./components/ValidationPanel.jsx";
import LandingPage from "./components/LandingPage.jsx";
import AddClaimModal from "./components/AddClaimModal.jsx";
import PrivacyToggle from "./components/PrivacyToggle.jsx";
import ManagementOverview from "./components/ManagementOverview.jsx";
import { useClaims } from "./hooks/useClaims.js";
import { api } from "./api/client.js";

const DEPARTMENT_ROLES = [
  { value: "outpatient", label: "Outpatient claims desk", department: "outpatient" },
  { value: "renal", label: "Renal claims desk", department: "renal" },
  { value: "maternity", label: "Maternity claims desk", department: "maternity" },
  { value: "manager", label: "Manager", department: null },
];
const GENERAL_ROLES = [
  { value: "claims_officer", label: "Claims officer", department: null },
  { value: "manager", label: "Manager", department: null },
];

export default function App() {
  const [selectedClaim, setSelectedClaim] = useState(null);
  const [counts, setCounts] = useState({ total: 0, ready: 0, review: 0, errors: 0 });

  const { claims, loading, error, offline, savedAt, reload, patchPreview, markNeedsRevalidation, addClaim } = useClaims();
  const [view, setView] = useState("landing");
  const [selectedId, setSelectedId] = useState(null);
  const [addModalOpen, setAddModalOpen] = useState(false);
  const [privacyMode, setPrivacyMode] = useState(() => localStorage.getItem("presentationPrivacy") === "on");
  const [departmentsEnabled, setDepartmentsEnabled] = useState(true);
  const roleOptions = departmentsEnabled ? DEPARTMENT_ROLES : GENERAL_ROLES;
  const [demoRole, setDemoRole] = useState(() => localStorage.getItem("hakikiDemoRole") || "outpatient");
  const role = roleOptions.find((item) => item.value === demoRole) || roleOptions[0];
  const managerOnly = role.value === "manager";
  const [databaseNoticeDismissed, setDatabaseNoticeDismissed] = useState(false);
  const previousDatabaseError = useRef(error);

  useEffect(() => {
    if (error && !previousDatabaseError.current) setDatabaseNoticeDismissed(false);
    previousDatabaseError.current = error;
  }, [error]);

  useEffect(() => {
    let active = true;
    api.getUiSettings().then((settings) => {
      if (active) setDepartmentsEnabled(settings.departments_enabled !== false);
    }).catch(() => {});
    return () => { active = false; };
  }, []);

  function handleValidationComplete(claimId, validationResult, updatedClaim) {
    patchPreview(claimId, validationResult);
    if (updatedClaim) {
      setSelectedClaim((current) => current?.id === claimId ? { ...current, ...updatedClaim } : current);
    }
    if (validationResult.lifecycle) {
      setSelectedClaim((current) => current?.id === claimId ? { ...current, _lifecycle: validationResult.lifecycle } : current);
    }
  }

  function handleLifecycleChange(claimId, lifecycle, updatedClaim) {
    setSelectedClaim((current) => current?.id === claimId ? { ...current, ...(updatedClaim || {}), _lifecycle: lifecycle } : current);
    void reload();
  }

  function handleLocalEdit(claimId) {
    markNeedsRevalidation(claimId);
    setSelectedClaim((current) => current?.id === claimId ? {
      ...current,
      _lifecycle: { ...(current._lifecycle || {}), status: "needs_revalidation" },
      _preview: { ...(current._preview || {}), status: "Needs revalidation", color: "amber" },
    } : current);
  }

  const [darkMode, setDarkMode] = useState(() => {
    if (typeof window !== "undefined") {
      const saved = localStorage.getItem("theme");
      if (saved) return saved === "dark";
      return window.matchMedia("(prefers-color-scheme: dark)").matches;
    }
    return false;
  });

  useEffect(() => {
    if (darkMode) {
      document.documentElement.classList.add("dark");
      localStorage.setItem("theme", "dark");
    } else {
      document.documentElement.classList.remove("dark");
      localStorage.setItem("theme", "light");
    }
  }, [darkMode]);

  useEffect(() => {
    localStorage.setItem("presentationPrivacy", privacyMode ? "on" : "off");
  }, [privacyMode]);

  useEffect(() => {
    if (!roleOptions.some((item) => item.value === demoRole)) setDemoRole(roleOptions[0].value);
  }, [demoRole, roleOptions]);

  useEffect(() => {
    localStorage.setItem("hakikiDemoRole", role.value);
    if (view !== "landing") setView(managerOnly ? "overview" : view === "overview" ? "dashboard" : view);
  }, [role.value, managerOnly, view]);

  const visibleClaims = useMemo(() => role.department
    ? claims.filter((claim) => (claim.department || "").toLowerCase() === role.department)
    : claims, [claims, role.department]);

  useEffect(() => {
    if ((!selectedId || !visibleClaims.some((claim) => claim.id === selectedId)) && visibleClaims.length > 0) {
      setSelectedId(visibleClaims[0].id);
      setSelectedClaim(visibleClaims[0]);
    }
  }, [visibleClaims, selectedId]);

  // Oracle queue rows contain only summary fields; fetch the complete claim
  // only when an officer selects it for the detailed workflow.
  useEffect(() => {
    if (!selectedId || managerOnly || !visibleClaims.some((claim) => claim.id === selectedId)) return undefined;
    let currentSelection = true;
    api.getClaim(selectedId)
      .then((fullClaim) => {
        if (currentSelection) {
          setSelectedClaim((current) => current?.id === selectedId ? { ...current, ...fullClaim } : current);
        }
      })
      .catch(() => {});
    return () => { currentSelection = false; };
  }, [selectedId, managerOnly, visibleClaims]);

  async function handleAddClaim(claimData) {
    const created = await addClaim(claimData);
    setSelectedId(created.id);
    setSelectedClaim(created);
    setAddModalOpen(false);
    setView("dashboard");
  }

  if (view === "landing") {
    return (
      <LandingPage
        claims={claims}
        loading={loading}
        onEnter={() => setView("dashboard")}
        darkMode={darkMode}
        onToggleTheme={() => setDarkMode(!darkMode)}
      />
    );
  }

  return (
    <div className="flex h-screen min-h-0 flex-col overflow-hidden bg-slate-100 font-sans text-slate-900 antialiased dark:bg-slate-900 dark:text-slate-100">
      <header className="z-20 flex min-h-14 shrink-0 flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b border-slate-200 bg-white px-4 py-2 dark:border-slate-800 dark:bg-slate-950">
        <div className="flex min-w-0 items-center gap-3">
          <button type="button" onClick={() => setView("landing")} className="flex shrink-0 items-center gap-2 text-left" aria-label="Return to Hakiki home">
            <img src="/favicon.png" alt="" className="h-7 w-7 object-contain" />
            <span className="text-2xl font-black tracking-tight text-teal-800 dark:text-teal-400">Hakiki</span>
          </button>
          <span className="hidden rounded-full border border-slate-300 px-2.5 py-1 text-[11px] font-semibold text-slate-700 dark:border-slate-700 dark:text-slate-200 sm:inline-flex">Demo environment: synthetic data</span>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-1.5 sm:gap-2">
          <PrivacyToggle enabled={privacyMode} onToggle={() => setPrivacyMode((enabled) => !enabled)} />
          <button type="button" onClick={() => setDarkMode(!darkMode)} aria-label="Toggle theme" className="rounded-md p-2 text-slate-700 hover:bg-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-teal-700 dark:text-slate-200 dark:hover:bg-slate-800">
            <span aria-hidden="true">{darkMode ? "☼" : "☾"}</span>
          </button>
          <label className="flex items-center gap-2 rounded-md px-2 py-2 text-xs font-semibold text-slate-700 dark:text-slate-200">
            <span>Demo role · no authentication</span>
            <select value={role.value} onChange={(event) => { setDemoRole(event.target.value); setView(event.target.value === "manager" ? "overview" : "dashboard"); }} aria-label="Select demo role (not authentication)" className="max-w-52 rounded-md border border-slate-300 bg-white px-2 py-2 text-xs text-slate-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-teal-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100">{roleOptions.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select>
          </label>
          {!managerOnly && <button type="button" onClick={() => setView(view === "overview" ? "dashboard" : "overview")} aria-current={view === "overview" ? "page" : undefined} className="rounded-md border border-slate-300 px-3 py-2 text-xs font-semibold text-slate-800 hover:bg-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-teal-700 dark:border-slate-700 dark:text-slate-100 dark:hover:bg-slate-800">{view === "overview" ? "Claims" : "Management Overview"}</button>}
          {!managerOnly && <button type="button" onClick={() => setAddModalOpen(true)} aria-label="Add claim" className="rounded-md bg-teal-700 px-3 py-2 text-xs font-bold text-white hover:bg-teal-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-700">+ Add</button>}
        </div>
      </header>

      {error && !databaseNoticeDismissed && <div role="alert" className="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-2 border-b border-amber-700 bg-amber-50 px-4 py-2 text-sm text-amber-950 dark:border-amber-500 dark:bg-amber-950 dark:text-amber-100">
        <strong>Database slow / unreachable</strong>
        <span className="min-w-0 flex-1">{offline && savedAt ? `Offline: showing data saved at ${new Date(savedAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}.` : error}</span>
        <button type="button" onClick={() => { setDatabaseNoticeDismissed(false); void reload(); }} disabled={loading} className="rounded border border-amber-800 px-3 py-1 font-semibold text-amber-950 hover:bg-amber-100 disabled:opacity-60 dark:border-amber-300 dark:text-amber-100 dark:hover:bg-amber-900">{loading ? "Retrying…" : "Retry"}</button>
        <button type="button" aria-label="Dismiss database notice" onClick={() => setDatabaseNoticeDismissed(true)} className="rounded px-2 py-1 text-lg font-bold leading-none hover:bg-amber-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-amber-800 dark:hover:bg-amber-900">×</button>
      </div>}

      {managerOnly ? <main className="flex min-h-0 flex-1 overflow-hidden bg-slate-50 dark:bg-slate-900" aria-label="Management overview"><ManagementOverview onBack={() => {}} showBack={false} /></main> : <div className="flex min-h-0 flex-1 overflow-hidden">
        <aside className="flex w-[300px] max-w-[36vw] shrink-0 flex-col border-r border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950 xl:w-[340px] 2xl:w-[370px]" aria-label="Claims queue">
          <div className="flex h-12 shrink-0 items-center justify-between border-b border-slate-200 px-4 dark:border-slate-800">
            <div><p className="text-[11px] font-bold uppercase tracking-wide text-slate-700 dark:text-slate-200">Claims queue</p>{!loading && <p className="text-[11px] text-slate-600 dark:text-slate-300">{counts.total || claims.length} total · {counts.ready} ready</p>}</div>
            <button type="button" onClick={() => { setDatabaseNoticeDismissed(false); void reload(); }} disabled={loading} className="rounded px-2 py-1 text-xs font-semibold text-teal-800 hover:bg-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-teal-700 disabled:opacity-60 dark:text-teal-300 dark:hover:bg-slate-800">{loading ? "Loading…" : "Refresh"}</button>
          </div>
          <div className="min-h-0 flex-1"><ClaimList claims={visibleClaims} loading={loading} privacyMode={privacyMode} selectedId={selectedId} lockedDepartment={role.department} showDepartmentFilter={!departmentsEnabled} onSelect={(id, claim) => { setSelectedId(id); setSelectedClaim(claim); }} onCountsChange={setCounts} /></div>
        </aside>

        <main className="flex min-w-0 flex-1 flex-col overflow-hidden bg-slate-50 dark:bg-slate-900" aria-label={view === "overview" ? "Management overview" : "Claim workspace"}>
          {view === "overview" ? <ManagementOverview onBack={() => setView("dashboard")} /> : <ValidationPanel key={selectedClaim?.id ?? "no-claim"} claim={selectedClaim} privacyMode={privacyMode} departmentsEnabled={departmentsEnabled} onValidationComplete={handleValidationComplete} onLifecycleChange={handleLifecycleChange} onLocalEdit={handleLocalEdit} />}
        </main>
      </div>}

      {addModalOpen && (
        <AddClaimModal onClose={() => setAddModalOpen(false)} onSubmit={handleAddClaim} />
      )}
    </div>
  );
}
