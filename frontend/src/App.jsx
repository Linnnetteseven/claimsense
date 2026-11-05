import { useState, useEffect } from "react";
import ClaimList from "./components/ClaimList.jsx";
import ValidationPanel from "./components/ValidationPanel.jsx";
import LandingPage from "./components/LandingPage.jsx";
import AddClaimModal from "./components/AddClaimModal.jsx";
import PrivacyToggle from "./components/PrivacyToggle.jsx";
import ManagementOverview from "./components/ManagementOverview.jsx";
import { useClaims } from "./hooks/useClaims.js";
import { api } from "./api/client.js";

const SHOW_PER_CLAIM_SYNTHETIC_LABELS = import.meta.env.VITE_SYNTHETIC_LABEL === "full";

export default function App() {
  const [selectedClaim, setSelectedClaim] = useState(null);
  const [counts, setCounts] = useState({ total: 0, ready: 0, review: 0, errors: 0 });

  const { claims, loading, error, offline, savedAt, reload, patchPreview, addClaim } = useClaims();
  const [view, setView] = useState("landing");
  const [selectedId, setSelectedId] = useState(null);
  const [addModalOpen, setAddModalOpen] = useState(false);
  const [privacyMode, setPrivacyMode] = useState(() => localStorage.getItem("presentationPrivacy") === "on");
  const [demoMode, setDemoMode] = useState(() => localStorage.getItem("hakikiDemoMode") === "on");
  const [demoRole, setDemoRole] = useState(() => localStorage.getItem("hakikiDemoRole") || "Lab");
  const [databaseNoticeDismissed, setDatabaseNoticeDismissed] = useState(false);

  function handleValidationComplete(claimId, validationResult, updatedClaim) {
    patchPreview(claimId, validationResult);
    if (updatedClaim) {
      setSelectedClaim((current) => current?.id === claimId ? { ...current, ...updatedClaim } : current);
    }
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
    localStorage.setItem("hakikiDemoMode", demoMode ? "on" : "off");
    localStorage.setItem("hakikiDemoRole", demoRole);
  }, [demoMode, demoRole]);

  useEffect(() => {
    if (!selectedId && claims.length > 0) {
      setSelectedId(claims[0].id);
      setSelectedClaim(claims[0]);
    }
  }, [claims, selectedId]);

  // Oracle queue rows contain only summary fields; fetch the complete claim
  // only when an officer selects it for the detailed workflow.
  useEffect(() => {
    if (!selectedId) return undefined;
    let currentSelection = true;
    api.getClaim(selectedId)
      .then((fullClaim) => {
        if (currentSelection) {
          setSelectedClaim((current) => current?.id === selectedId ? { ...current, ...fullClaim } : current);
        }
      })
      .catch(() => {});
    return () => { currentSelection = false; };
  }, [selectedId]);

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
    <div className="flex h-screen bg-slate-50 dark:bg-slate-900 overflow-hidden font-sans text-slate-800 dark:text-slate-100 antialiased">
      {/* Left sidebar: Persistent Queue */}
      <aside className="w-72 2xl:w-80 flex-shrink-0 bg-white dark:bg-slate-950 border-r border-slate-200 dark:border-slate-800 flex flex-col">
        {/* Branding Header - Updated to Hakiki Reference Style */}
        <div className="px-4 py-3 border-b border-slate-100 dark:border-slate-800/60 space-y-3">
          <div className="flex items-center justify-between gap-2">
            <button
              type="button"
              onClick={() => setView("landing")}
              className="flex items-center hover:opacity-80 transition-opacity text-left min-w-0"
              aria-label="Return to Hakiki home"
            >
              <div className="flex items-center gap-2.5">
                <img src="/favicon.png" alt="" className="h-8 w-8 object-contain" />
                <span className="text-3xl font-black tracking-tighter text-[#0A4D3C] dark:text-teal-400 leading-none mt-1">Hakiki</span>
              </div>
            </button>
            <div className="flex items-center gap-1 shrink-0">
              <button
                type="button"
                onClick={() => setDarkMode(!darkMode)}
                aria-label="Toggle Theme"
                className="p-2 text-slate-500 hover:text-teal-600 dark:text-slate-400 dark:hover:text-teal-400 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
              >
                {darkMode ? (
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364-6.364l-.707.707M6.343 17.657l-.707.707m12.728 0l-.707-.707M6.343 6.364l-.707-.707M12 8a4 4 0 100 8 4 4 0 000-8z" />
                  </svg>
                ) : (
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
                  </svg>
                )}
              </button>
              <button
                type="button"
                onClick={() => setAddModalOpen(true)}
                className="text-xs bg-[#00897B] hover:bg-teal-700 active:scale-95 transition-all text-white font-semibold rounded-lg px-3 py-2 shadow-sm whitespace-nowrap"
                aria-label="Add claim"
              >
                + Add
              </button>
            </div>
          </div>
          {!SHOW_PER_CLAIM_SYNTHETIC_LABELS && (
            <span className="inline-flex w-fit items-center rounded-full border border-amber-200 bg-amber-50 px-2 py-1 text-[10px] font-semibold text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-300">
              Demo environment: synthetic data
            </span>
          )}
          <PrivacyToggle enabled={privacyMode} onToggle={() => setPrivacyMode((enabled) => !enabled)} />
          <button
            type="button"
            onClick={() => setView(view === "overview" ? "dashboard" : "overview")}
            aria-current={view === "overview" ? "page" : undefined}
            className={`w-full rounded-lg border px-3 py-2 text-xs font-semibold transition-colors ${view === "overview" ? "border-teal-500 bg-teal-50 text-teal-800 dark:bg-teal-950/40 dark:text-teal-300" : "border-slate-200 text-slate-600 hover:border-teal-400 hover:text-teal-700 dark:border-slate-800 dark:text-slate-300"}`}
          >
            {view === "overview" ? "← Return to claims" : "Management Overview"}
          </button>
          <div className="rounded-lg border border-slate-200 dark:border-slate-800 p-2.5">
            <label className="flex items-center justify-between gap-3 text-xs font-semibold text-slate-600 dark:text-slate-300">
              <span>Demo mode <span className="font-normal text-slate-400">(demo only)</span></span>
              <input
                type="checkbox"
                checked={demoMode}
                onChange={(event) => setDemoMode(event.target.checked)}
                aria-label="Enable demo role display"
                className="h-4 w-4 accent-teal-600"
              />
            </label>
            {demoMode && (
              <div className="mt-2 flex items-center gap-2">
                <span className="shrink-0 text-[10px] font-bold uppercase tracking-wide text-teal-700 dark:text-teal-400">Demo role</span>
                <select value={demoRole} onChange={(event) => setDemoRole(event.target.value)} aria-label="Select demo role" className="min-w-0 flex-1 rounded-md border border-slate-200 bg-white px-2 py-1.5 text-xs text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200">
                  {["Lab", "Pharmacy", "Billing"].map((role) => <option key={role}>{role}</option>)}
                </select>
              </div>
            )}
          </div>
        </div>

        {/* Search & Stats Header */}
        <div className="px-4 py-3 bg-slate-50/50 dark:bg-slate-900/50 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between gap-3">
          <div>
            <p className="text-[10px] font-bold text-slate-400 dark:text-slate-500 uppercase tracking-wider">
              Claims Queue
            </p>
            {!loading && (
              <p className="text-xs text-slate-500 dark:text-slate-400 font-medium">
                {counts.total || claims.length} total • {counts.ready} ready
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={reload}
            className="text-xs text-slate-500 dark:text-slate-400 hover:text-teal-600 dark:hover:text-teal-400 font-medium transition-colors"
          >
            Refresh
          </button>
        </div>

        {error && !databaseNoticeDismissed && (
          <div role="alert" className="mx-3 my-2 text-xs text-amber-950 dark:text-amber-100 bg-amber-50 dark:bg-amber-950/50 border border-amber-500 dark:border-amber-700 rounded-lg p-3">
            <div className="flex items-start justify-between gap-2">
              <div>
                <p className="font-bold">{offline ? "Offline: showing saved claims" : "Database slow / unreachable"}</p>
                <p className="mt-1">{offline && savedAt ? `Offline: showing data saved at ${new Date(savedAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}.` : error}</p>
              </div>
              <button type="button" className="shrink-0 rounded px-1 text-sm font-bold focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2" aria-label="Dismiss database notice" onClick={() => setDatabaseNoticeDismissed(true)}>×</button>
            </div>
            <button type="button" onClick={() => { setDatabaseNoticeDismissed(false); void reload(); }} disabled={loading} className="mt-2 rounded-md border border-amber-700 px-2.5 py-1 font-semibold text-amber-950 hover:bg-amber-100 disabled:opacity-60 dark:border-amber-500 dark:text-amber-100 dark:hover:bg-amber-900/70">
              {loading ? "Retrying…" : "Retry now"}
            </button>
          </div>
        )}

        {/* Scrollable list of claims */}
        <div className="flex-1 overflow-y-auto">
          <ClaimList
            claims={claims}
            loading={loading}
            onRefresh={reload}
            privacyMode={privacyMode}
            selectedId={selectedId}
            onSelect={(id, claim) => {
              setSelectedId(id);
              setSelectedClaim(claim);
            }}
            onCountsChange={setCounts}
          />
        </div>

        {/* Footer info */}
        <div className="px-5 py-3 border-t border-slate-100 dark:border-slate-800 bg-slate-50/30 dark:bg-slate-900/30">
          <p className="text-[10px] text-slate-400 dark:text-slate-500 font-medium">
            Hakiki Claims Portal
          </p>
        </div>
      </aside>

      {/* Right workspace: Dynamic Workspace */}
      <main className="flex-1 flex flex-col overflow-hidden bg-slate-100/60 dark:bg-slate-900/40">
        {view === "overview" ? (
          <ManagementOverview onBack={() => setView("dashboard")} />
        ) : (
          <ValidationPanel
            key={selectedClaim?.id ?? "no-claim"}
            claim={selectedClaim}
            privacyMode={privacyMode}
            onValidationComplete={handleValidationComplete}
          />
        )}
      </main>

      {addModalOpen && (
        <AddClaimModal onClose={() => setAddModalOpen(false)} onSubmit={handleAddClaim} />
      )}
    </div>
  );
}
