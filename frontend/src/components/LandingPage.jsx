import PropTypes from "prop-types";
import ScoreGauge from "./ScoreGauge.jsx";

const STEPS = [
  { 
    n: "01", 
    title: "Select Claim", 
    body: "Choose a pending patient claim directly from the live hospital queue.",
    icon: <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01" />
  },
  { 
    n: "02", 
    title: "AI Co-Pilot Audit", 
    body: "The AI instantly cross-checks data against SHA billing rules, acting as your second pair of eyes.",
    icon: <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M13 10V3L4 14h7v7l9-11h-7z" />
  },
  { 
    n: "03", 
    title: "Resolve Confidently", 
    body: "Read plain-English explanations of flagged errors and fix the data without leaving the workspace.",
    icon: <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
  },
  { 
    n: "04", 
    title: "Submit to openIMIS", 
    body: "Forward the clean, fully validated claim to the ledger with one click for faster hospital payouts.",
    icon: <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
  },
];

export default function LandingPage({ claims, loading, onEnter, darkMode, onToggleTheme }) {
  const total = claims.length;
  const ready = claims.filter((c) => c._preview?.color === "green").length;
  const review = claims.filter((c) => c._preview?.color === "amber").length;
  const highRisk = claims.filter((c) => c._preview?.color === "red").length;
  const avgScore = total
    ? Math.round(claims.reduce((sum, c) => sum + (c._preview?.score ?? 0), 0) / total)
    : 0;

  return (
    <div className="h-screen w-full bg-slate-50 dark:bg-slate-900 text-slate-800 dark:text-slate-100 overflow-y-auto font-sans antialiased selection:bg-teal-500/20 scroll-smooth">
      
      {/* --- MINIMAL STICKY NAVBAR --- */}
      <nav className="w-full bg-white/90 dark:bg-slate-900/90 backdrop-blur-md border-b border-slate-200 dark:border-slate-850 sticky top-0 z-50">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <img src="/favicon.png" alt="Hakiki" className="h-6 w-6 object-contain" />
            <span className="font-black text-[#0A4D3C] dark:text-teal-400 text-2xl tracking-tighter mt-1">Hakiki</span>
          </div>
          <div className="flex items-center gap-6">
            <a href="#how-it-works" className="text-sm font-medium text-slate-500 dark:text-slate-400 hover:text-teal-600 dark:hover:text-teal-400 transition-colors hidden sm:block">
              How it Works
            </a>
            <button
              type="button"
              onClick={onToggleTheme}
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
            <button onClick={onEnter} className="text-sm font-bold text-[#1565C0] dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300 transition-colors">
              Open Workspace &rarr;
            </button>
          </div>
        </div>
      </nav>

      {/* --- HERO SECTION --- */}
      <div className="flex flex-col items-center justify-center px-4 sm:px-6 pt-16 sm:pt-24 pb-16 max-w-5xl mx-auto animate-fade-in min-h-[90vh]">
        
        {/* Code-Based Brand Lockup */}
        <div className="flex flex-col md:flex-row items-center gap-4 mb-4">
          <div className="flex items-center gap-3">
            <img src="/favicon.png" alt="Hakiki Health" className="h-10 sm:h-14 w-auto object-contain drop-shadow-sm" />
            <div className="flex flex-col justify-center text-left">
              <span className="text-4xl sm:text-5xl font-black tracking-tighter text-[#0A4D3C] dark:text-teal-400 mt-1">
                Hakiki
              </span>
            </div>
          </div>
          <div className="hidden md:block h-10 w-px bg-slate-300 dark:bg-slate-700 mx-2"></div>
          <div className="flex flex-col text-center md:text-left text-xs sm:text-sm font-medium text-slate-500 dark:text-slate-400">
            <span className="text-slate-800 dark:text-slate-200 font-bold">AI-Powered Claims</span>
            <span>Pre-Submission Check</span>
          </div>
        </div>

        {/* Hero Copy */}
        <div className="text-center space-y-5 max-w-4xl mx-auto mt-4">
          <h1 className="text-3xl sm:text-5xl md:text-6xl font-extrabold tracking-tight text-slate-900 dark:text-slate-50 leading-[1.15]">
            Healthcare Claims Deserve <br className="hidden sm:block" />
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-[#1565C0] to-[#00897B] dark:from-blue-400 dark:to-teal-400">Intelligence, Not More Paperwork.</span>
          </h1>
          <p className="text-slate-600 dark:text-slate-350 text-sm sm:text-base md:text-lg leading-relaxed font-medium max-w-2xl mx-auto">
            Hakiki pairs SHA claims officers with an AI co-pilot to instantly validate openIMIS data. We don't replace your expertise—we eliminate the friction so you can process claims faster and with absolute confidence.
          </p>
        </div>

        {/* Primary CTA */}
        <button
          type="button"
          onClick={onEnter}
          className="group mt-8 bg-[#1565C0] hover:bg-[#0d47a1] active:scale-95 transition-all duration-200 text-white font-bold px-8 py-4 rounded-xl text-sm sm:text-base shadow-lg hover:shadow-xl hover:shadow-blue-900/20 flex items-center gap-3"
        >
          Open Claims Workspace
          <svg className="w-5 h-5 transform group-hover:translate-x-1 transition-transform duration-200" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
          </svg>
        </button>

        {/* Live Queue Snapshot Summary Card */}
        <div className="w-full max-w-4xl bg-white dark:bg-slate-950 border border-slate-200/80 dark:border-slate-850 rounded-3xl p-6 sm:p-8 shadow-sm flex flex-col md:flex-row items-center justify-center gap-8 relative overflow-hidden mt-16 sm:mt-20 mb-8">
          <div className="absolute top-0 left-0 w-1.5 h-full bg-gradient-to-b from-[#1565C0] to-[#00897B]"></div>
          {loading ? (
            <div className="py-8 flex items-center gap-3 text-slate-500 dark:text-slate-400 font-medium">
               <div className="w-5 h-5 border-2 border-teal-500 border-t-transparent rounded-full animate-spin"></div>
               Syncing live claims queue...
            </div>
          ) : total === 0 ? (
            <div className="py-8 text-slate-500 dark:text-slate-400 font-medium text-center">No active claims in pre-submission queue.</div>
          ) : (
            <>
              <div className="flex flex-col items-center shrink-0">
                <span className="text-[10px] font-bold text-slate-400 dark:text-slate-500 uppercase tracking-widest mb-2 text-center">Queue Health Score</span>
                <ScoreGauge score={avgScore} />
              </div>
              <div className="border-t md:border-t-0 md:border-l border-slate-100 dark:border-slate-800 pt-5 md:pt-0 md:pl-8 flex-1 w-full">
                <h3 className="text-xs font-bold text-slate-400 dark:text-slate-500 uppercase tracking-wider mb-3.5 text-center md:text-left">Live Status Triage</h3>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                  <div className="bg-slate-50 dark:bg-slate-900/60 border border-slate-100 dark:border-slate-850 p-4 rounded-2xl text-center md:text-left">
                    <span className="text-[10px] text-slate-500 dark:text-slate-400 uppercase block font-bold mb-1">Total Claims</span>
                    <strong className="text-2xl sm:text-3xl font-black text-slate-800 dark:text-slate-200">{total}</strong>
                  </div>
                  <div className="bg-emerald-50/50 dark:bg-emerald-950/10 border border-emerald-100 dark:border-emerald-900/20 p-4 rounded-2xl text-center md:text-left">
                    <span className="text-[10px] text-emerald-700 dark:text-emerald-400 uppercase block font-bold mb-1">Ready</span>
                    <strong className="text-2xl sm:text-3xl font-black text-emerald-600 dark:text-emerald-400">{ready}</strong>
                  </div>
                  <div className="bg-amber-50/50 dark:bg-amber-950/10 border border-amber-100 dark:border-amber-900/20 p-4 rounded-2xl text-center md:text-left">
                    <span className="text-[10px] text-amber-700 dark:text-amber-400 uppercase block font-bold mb-1">Needs Review</span>
                    <strong className="text-2xl sm:text-3xl font-black text-amber-600 dark:text-amber-400">{review}</strong>
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      </div>

      {/* --- HOW IT WORKS --- */}
      <div id="how-it-works" className="w-full bg-slate-100/60 dark:bg-slate-900/30 py-20 sm:py-24 px-4 sm:px-6 border-y border-slate-200 dark:border-slate-800">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-12 sm:mb-16 px-4">
            <h2 className="text-2xl sm:text-3xl font-extrabold text-slate-900 dark:text-slate-50 mb-4">How Hakiki Works</h2>
            <p className="text-sm sm:text-base text-slate-500 dark:text-slate-400 font-medium max-w-2xl mx-auto">A streamlined, four-step workflow designed specifically for hospital claims officers. No technical expertise required.</p>
          </div>
          
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
            {STEPS.map((step) => (
              <div 
                key={step.n} 
                className="group relative bg-white dark:bg-slate-950 p-6 sm:p-8 rounded-3xl shadow-sm hover:shadow-xl transition-all duration-500 text-left overflow-hidden border border-slate-200 dark:border-slate-850 hover:border-transparent dark:hover:border-transparent"
              >
                <div className="absolute inset-0 bg-gradient-to-br from-[#1565C0] to-[#00897B] opacity-0 group-hover:opacity-100 transition-opacity duration-500 -z-10"></div>
                <div className="absolute inset-[2px] bg-white dark:bg-slate-950 rounded-[22px] z-0"></div>
                
                <div className="relative z-10 flex flex-col h-full">
                  <div className="flex items-center justify-between mb-6">
                    <div className="h-12 w-12 rounded-xl bg-slate-50 dark:bg-slate-900 text-teal-600 dark:text-teal-400 flex items-center justify-center group-hover:scale-110 transition-transform duration-300 shrink-0">
                      <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        {step.icon}
                      </svg>
                    </div>
                    <span className="text-4xl sm:text-5xl font-black text-slate-200 dark:text-slate-800 group-hover:text-slate-100 dark:group-hover:text-slate-700 transition-colors duration-300">{step.n}</span>
                  </div>
                  <h4 className="text-base sm:text-lg font-bold text-slate-900 dark:text-slate-100 mb-3">{step.title}</h4>
                  <p className="text-xs sm:text-sm text-slate-500 dark:text-slate-400 leading-relaxed font-medium">{step.body}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* --- WHY HAKIKI (Value Props) --- */}
      <div className="w-full bg-white dark:bg-slate-900 py-20 sm:py-24 px-4 sm:px-6">
        <div className="max-w-5xl mx-auto">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-10 sm:gap-12 text-center">
            <div className="px-4">
              <div className="mx-auto h-16 w-16 bg-blue-50 dark:bg-blue-950/20 rounded-2xl flex items-center justify-center mb-6">
                <svg className="w-8 h-8 text-blue-600 dark:text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" /></svg>
              </div>
              <h3 className="text-base sm:text-lg font-bold text-slate-900 dark:text-slate-100 mb-3">Human-in-the-Loop</h3>
              <p className="text-xs sm:text-sm text-slate-500 dark:text-slate-400 font-medium leading-relaxed">The AI highlights the errors and suggests fixes, but you retain full control. No automated rejections, just intelligent assistance.</p>
            </div>
            <div className="px-4">
              <div className="mx-auto h-16 w-16 bg-teal-50 dark:bg-teal-950/20 rounded-2xl flex items-center justify-center mb-6">
                <svg className="w-8 h-8 text-teal-600 dark:text-teal-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" /></svg>
              </div>
              <h3 className="text-base sm:text-lg font-bold text-slate-900 dark:text-slate-100 mb-3">openIMIS Native</h3>
              <p className="text-xs sm:text-sm text-slate-500 dark:text-slate-400 font-medium leading-relaxed">Built from the ground up to integrate seamlessly with standard openIMIS FHIR structures. No complex implementation required.</p>
            </div>
            <div className="px-4">
              <div className="mx-auto h-16 w-16 bg-amber-50 dark:bg-amber-950/20 rounded-2xl flex items-center justify-center mb-6">
                <svg className="w-8 h-8 text-amber-500 dark:text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" /></svg>
              </div>
              <h3 className="text-base sm:text-lg font-bold text-slate-900 dark:text-slate-100 mb-3">Instant ROI</h3>
              <p className="text-xs sm:text-sm text-slate-500 dark:text-slate-400 font-medium leading-relaxed">Catch missing data, mismatched codes, and policy violations instantly before they ever hit the ledger, accelerating your hospital's cash flow.</p>
            </div>
          </div>
        </div>
      </div>

      {/* --- BOTTOM CTA --- */}
      <div className="w-full bg-slate-900 py-16 sm:py-20 px-4 sm:px-6 text-center">
        <div className="max-w-3xl mx-auto">
          <h2 className="text-2xl sm:text-3xl font-extrabold text-white mb-4 sm:mb-6">Ready to empower your claims team?</h2>
          <p className="text-sm sm:text-base text-slate-400 font-medium mb-8 sm:mb-10 px-4">Experience how Hakiki's AI validation engine can transform your openIMIS workflow today.</p>
          <button
            type="button"
            onClick={onEnter}
            className="group bg-white hover:bg-slate-100 text-slate-900 font-bold px-8 sm:px-10 py-3 sm:py-4 rounded-xl text-base sm:text-lg shadow-xl hover:shadow-2xl transition-all duration-300 flex items-center gap-3 mx-auto"
          >
            Start Validating Claims
            <svg className="w-5 h-5 text-teal-600 transform group-hover:translate-x-1 transition-transform duration-200" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M14 5l7 7m0 0l-7 7m7-7H3" />
            </svg>
          </button>
        </div>
      </div>

      <footer className="px-6 py-6 text-center text-xs text-slate-500 font-medium bg-slate-950">
        Hakiki • Built for seamless openIMIS integration
      </footer>
    </div>
  );
}

LandingPage.propTypes = {
  claims: PropTypes.arrayOf(
    PropTypes.shape({
      _preview: PropTypes.shape({
        color: PropTypes.string,
        score: PropTypes.number,
      }),
    })
  ).isRequired,
  loading: PropTypes.bool,
  onEnter: PropTypes.func.isRequired,
  darkMode: PropTypes.bool.isRequired,
  onToggleTheme: PropTypes.func.isRequired,
};
