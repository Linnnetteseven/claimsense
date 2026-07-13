import { useState, useEffect } from "react";
import ClaimList from "./components/ClaimList.jsx";
import ValidationPanel from "./components/ValidationPanel.jsx";
import LandingPage from "./components/LandingPage.jsx";
import AddClaimModal from "./components/AddClaimModal.jsx";
import { useClaims } from "./hooks/useClaims.js";

export default function App() {
  const [selectedClaim, setSelectedClaim] = useState(null);
  const [counts, setCounts] = useState({ total: 0, ready: 0, review: 0, errors: 0 });

  const { claims, loading, error, reload, patchPreview, addClaim } = useClaims();
  const [view, setView] = useState("landing");
  const [selectedId, setSelectedId] = useState(null);
  const [addModalOpen, setAddModalOpen] = useState(false);

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

  if (!selectedId && claims.length > 0) {
    setSelectedId(claims[0].id);
  }

  const readyCount = claims.filter((c) => c._preview?.color === "green").length;

  async function handleAddClaim(claimData) {
    const created = await addClaim(claimData);
    setSelectedId(created.id);
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
      <aside className="w-80 flex-shrink-0 bg-white dark:bg-slate-950 border-r border-slate-200 dark:border-slate-800 flex flex-col">
        {/* Branding Header - Updated to Hakiki Reference Style */}
        <div className="px-5 py-4 border-b border-slate-100 dark:border-slate-800/60 flex items-center justify-between min-h-[72px]">
          <button
            type="button"
            onClick={() => setView("landing")}
            className="flex items-center hover:opacity-80 transition-opacity text-left shrink-0"
          >
            <div className="flex items-center gap-2.5">
              <img src="/favicon.png" alt="Hakiki Logo" className="h-8 w-8 object-contain" />
              <div className="flex flex-col text-left">
                {/* The new styled Hakiki logo text */}
                <span className="text-3xl font-black tracking-tighter text-[#0A4D3C] dark:text-teal-400 leading-none mt-1">
                  Hakiki
                </span>
              </div>
            </div>
          </button>
          <div className="flex items-center gap-2 ml-4">
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
              className="text-xs bg-[#00897B] hover:bg-teal-700 active:scale-95 transition-all text-white font-semibold rounded-lg px-2.5 py-2 shadow-sm whitespace-nowrap"
            >
              + Add
            </button>
          </div>
        </div>

        {/* Search & Stats Header */}
        <div className="px-5 py-3 bg-slate-50/50 dark:bg-slate-900/50 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between">
          <div>
            <p className="text-[10px] font-bold text-slate-400 dark:text-slate-500 uppercase tracking-wider">
              Claims Queue
            </p>
            {!loading && (
              <p className="text-xs text-slate-500 dark:text-slate-400 font-medium">
                {counts.total || claims.length} total • {counts.ready || readyCount} ready
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

        {error && (
          <div role="alert" className="mx-4 my-2 text-xs text-red-700 dark:text-red-400 bg-red-50 dark:bg-red-950/20 border border-red-100 dark:border-red-900/40 rounded-lg p-3">
            Failed to load: {error}
          </div>
        )}

        {/* Scrollable list of claims */}
        <div className="flex-1 overflow-y-auto">
          <ClaimList
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
        <ValidationPanel 
          claim={selectedClaim} 
          onValidationComplete={patchPreview} 
        />
      </main>

      {addModalOpen && (
        <AddClaimModal onClose={() => setAddModalOpen(false)} onSubmit={handleAddClaim} />
      )}
    </div>
  );
}
