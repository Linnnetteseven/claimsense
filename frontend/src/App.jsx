import { useState, useEffect } from "react";
import ClaimList from "./components/ClaimList.jsx";
import ValidationPanel from "./components/ValidationPanel.jsx";
import LandingPage from "./components/LandingPage.jsx";
import AddClaimModal from "./components/AddClaimModal.jsx";
import { useClaims } from "./hooks/useClaims.js";
import { stageOf } from "./constants/stages.js";

export default function App() {
  const { claims, loading, error, reload, patchClaim, addClaim, resetDemo } = useClaims();
  const [view, setView] = useState("landing");
  const [selectedId, setSelectedId] = useState(null);
  const selectedClaim = claims.find((c) => c.id === selectedId) ?? null;
  const [addModalOpen, setAddModalOpen] = useState(false);
  // "idle" | "confirm" | "running"; bumping resetCount remounts the workspace.
  const [resetState, setResetState] = useState("idle");
  const [resetCount, setResetCount] = useState(0);
  const [resetMessage, setResetMessage] = useState(null);

  const [darkMode, setDarkMode] = useState(() => {
    if (typeof window !== "undefined") {
      const saved = localStorage.getItem("theme");
      if (saved) return saved === "dark";
      return window.matchMedia("(prefers-color-scheme: dark)").matches;
    }
    return false;
  });

  // "/" jumps to the claim search, unless the officer is already typing somewhere.
  useEffect(() => {
    const onKey = (e) => {
      const typing = ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName);
      if (e.key === "/" && !typing && !e.ctrlKey && !e.metaKey) {
        const search = document.getElementById("claim-search");
        if (search) {
          e.preventDefault();
          search.focus();
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (darkMode) {
      document.documentElement.classList.add("dark");
      localStorage.setItem("theme", "dark");
    } else {
      document.documentElement.classList.remove("dark");
      localStorage.setItem("theme", "light");
    }
  }, [darkMode]);

  // Select the first claim on load, or when the selected one disappears (e.g. after a demo reset).
  if (claims.length > 0 && !claims.some((c) => c.id === selectedId)) {
    setSelectedId(claims[0].id);
  }

  async function handleResetDemo() {
    if (resetState === "idle") {
      setResetState("confirm");
      return;
    }
    setResetState("running");
    setResetMessage(null);
    try {
      const { restored, removed } = await resetDemo();
      setResetCount((n) => n + 1);
      setResetMessage(`Demo reset: ${restored} claims restored, ${removed} added claims removed.`);
    } catch (err) {
      setResetMessage(`Demo reset failed: ${err.message}`);
    } finally {
      setResetState("idle");
    }
  }

  const readyCount = claims.filter((c) => (c._stage ?? stageOf(c)) === "ready").length;

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
              className="text-xs bg-[#00796B] hover:bg-teal-800 active:scale-95 transition-all text-white font-semibold rounded-lg px-2.5 py-2 shadow-sm whitespace-nowrap"
            >
              + Add
            </button>
          </div>
        </div>

        {/* Search & Stats Header */}
        <div className="px-5 py-3 bg-slate-50/50 dark:bg-slate-900/50 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between">
          <div>
            <p className="text-[10px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
              Claims Queue
            </p>
            {!loading && (
              <p className="text-xs text-slate-500 dark:text-slate-400 font-medium">
                {claims.length} total • {readyCount} ready
              </p>
            )}
          </div>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={reload}
              className="text-xs text-slate-500 dark:text-slate-400 hover:text-teal-600 dark:hover:text-teal-400 font-medium transition-colors"
            >
              Refresh
            </button>
            <button
              type="button"
              onClick={handleResetDemo}
              onBlur={() => resetState === "confirm" && setResetState("idle")}
              disabled={resetState === "running"}
              title="Restore every seeded claim and remove claims added in this demo"
              className={`text-xs font-medium transition-colors disabled:opacity-60 ${
                resetState === "confirm"
                  ? "text-red-600 dark:text-red-400 font-bold"
                  : "text-slate-500 dark:text-slate-400 hover:text-red-600 dark:hover:text-red-400"
              }`}
            >
              {resetState === "confirm" ? "Confirm reset?" : resetState === "running" ? "Resetting..." : "Reset demo"}
            </button>
          </div>
        </div>

        {resetMessage && (
          <p role="status" className="mx-4 mt-2 text-[11px] text-slate-500 dark:text-slate-400">
            {resetMessage}
          </p>
        )}

        {error && (
          <div role="alert" className="mx-4 my-2 text-xs text-red-700 dark:text-red-400 bg-red-50 dark:bg-red-950/20 border border-red-100 dark:border-red-900/40 rounded-lg p-3">
            Failed to load: {error}
          </div>
        )}

        {/* Scrollable list of claims */}
        <div className="flex-1 overflow-y-auto">
          <ClaimList
            claims={claims}
            loading={loading}
            selectedId={selectedId}
            onSelect={setSelectedId}
          />
        </div>

        {/* Footer info */}
        <div className="px-5 py-3 border-t border-slate-100 dark:border-slate-800 bg-slate-50/30 dark:bg-slate-900/30">
          <p className="text-[10px] text-slate-500 dark:text-slate-400 font-medium">
            Hakiki Claims Portal
          </p>
        </div>
      </aside>

      {/* Right workspace: Dynamic Workspace */}
      <main className="flex-1 flex flex-col overflow-hidden bg-slate-100/60 dark:bg-slate-900/40">
        <ValidationPanel
          key={resetCount}
          claim={selectedClaim}
          onValidationComplete={patchClaim}
        />
      </main>

      {addModalOpen && (
        <AddClaimModal onClose={() => setAddModalOpen(false)} onSubmit={handleAddClaim} />
      )}
    </div>
  );
}
