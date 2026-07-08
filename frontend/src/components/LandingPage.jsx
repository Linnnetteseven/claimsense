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

export default function LandingPage({ claims, loading, onEnter }) {
  const total = claims.length;
  const ready = claims.filter((c) => c._preview?.color === "green").length;
  const review = claims.filter((c) => c._preview?.color === "amber").length;
  const highRisk = claims.filter((c) => c._preview?.color === "red").length;
  const avgScore = total
    ? Math.round(claims.reduce((sum, c) => sum + (c._preview?.score ?? 0), 0) / total)
    : 0;

  return (
    // Replaced strict flex height constraints with standard block scrolling
    <div className="h-screen w-full bg-slate-50 text-slate-800 overflow-y-auto font-sans antialiased selection:bg-hakiki-teal/20 scroll-smooth">
      
      {/* --- MINIMAL STICKY NAVBAR --- */}
      <nav className="w-full bg-white/90 backdrop-blur-md border-b border-slate-200 sticky top-0 z-50">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <img src="/favicon.png" alt="Hakiki" className="h-6 w-6 object-contain" />
            <span className="font-extrabold text-hakiki-dark text-lg tracking-tight">ClaimSense</span>
          </div>
          <div className="flex items-center gap-6">
            <a href="#how-it-works" className="text-sm font-medium text-slate-500 hover:text-hakiki-teal transition-colors hidden sm:block">
              How it Works
            </a>
            <button onClick={onEnter} className="text-sm font-bold text-hakiki-blue hover:text-blue-800 transition-colors">
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
            <img src="/favicon.png" alt="Hakiki Health" className="h-10 sm:h-12 w-auto object-contain drop-shadow-sm" />
            <div className="flex flex-col justify-center text-left">
              <span className="text-2xl sm:text-3xl font-extrabold tracking-tight text-hakiki-dark flex items-center gap-2">
                ClaimSense 
                <span className="text-[10px] sm:text-sm font-semibold bg-hakiki-light text-hakiki-teal px-2 py-0.5 rounded-full border border-teal-100 uppercase tracking-wider">
                  by Hakiki
                </span>
              </span>
            </div>
          </div>
          <div className="hidden md:block h-10 w-px bg-slate-300 mx-2"></div>
          <div className="flex flex-col text-center md:text-left text-xs sm:text-sm font-medium text-slate-500">
            <span className="text-hakiki-dark font-bold">AI-Powered Claims</span>
            <span>Pre-Submission Check</span>
          </div>
        </div>

        {/* Hero Copy */}
        <div className="text-center space-y-5 max-w-4xl mx-auto mt-4">
          <h1 className="text-3xl sm:text-5xl md:text-6xl font-extrabold tracking-tight text-slate-900 leading-[1.15]">
            Healthcare Claims Deserve <br className="hidden sm:block" />
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-hakiki-blue to-hakiki-teal">Intelligence, Not More Paperwork.</span>
          </h1>
          <p className="text-slate-600 text-sm sm:text-base md:text-lg leading-relaxed font-medium max-w-2xl mx-auto">
            ClaimSense pairs SHA claims officers with an AI co-pilot to instantly validate openIMIS data. We don't replace your expertise—we eliminate the friction so you can process claims faster and with absolute confidence.
          </p>
        </div>

        {/* Primary CTA */}
        <button
          type="button"
          onClick={onEnter}
          className="group mt-8 bg-hakiki-blue hover:bg-[#0d47a1] active:scale-95 transition-all duration-200 text-white font-bold px-8 py-4 rounded-xl text-sm sm:text-base shadow-lg hover:shadow-xl hover:shadow-hakiki-blue/20 flex items-center gap-3"
        >
          Open Claims Workspace
          <svg className="w-5 h-5 transform group-hover:translate-x-1 transition-transform duration-200" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
          </svg>
        </button>

        {/* Live Queue Snapshot Summary Card (Now with plenty of margin!) */}
        <div className="w-full max-w-4xl bg-white border border-slate-200/80 rounded-3xl p-6 sm:p-8 shadow-sm flex flex-col md:flex-row items-center justify-center gap-8 relative overflow-hidden mt-16 sm:mt-20 mb-8">
          <div className="absolute top-0 left-0 w-1.5 h-full bg-gradient-to-b from-hakiki-blue to-hakiki-teal"></div>
          {loading ? (
            <div className="py-8 flex items-center gap-3 text-slate-500 font-medium">
               <div className="w-5 h-5 border-2 border-hakiki-teal border-t-transparent rounded-full animate-spin"></div>
               Syncing live claims queue...
            </div>
          ) : total === 0 ? (
            <div className="py-8 text-slate-500 font-medium text-center">No active claims in pre-submission queue.</div>
          ) : (
            <>
              <div className="flex flex-col items-center shrink-0">
                <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-2 text-center">Queue Health Score</span>
                <ScoreGauge score={avgScore} />
              </div>
              <div className="border-t md:border-t-0 md:border-l border-slate-100 pt-5 md:pt-0 md:pl-8 flex-1 w-full">
                <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3.5 text-center md:text-left">Live Status Triage</h3>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                  <div className="bg-slate-50 border border-slate-100 p-4 rounded-2xl text-center md:text-left">
                    <span className="text-[10px] text-slate-500 uppercase block font-bold mb-1">Total Claims</span>
                    <strong className="text-2xl sm:text-3xl font-black text-slate-800">{total}</strong>
                  </div>
                  <div className="bg-emerald-50/50 border border-emerald-100 p-4 rounded-2xl text-center md:text-left">
                    <span className="text-[10px] text-emerald-700 uppercase block font-bold mb-1">Ready</span>
                    <strong className="text-2xl sm:text-3xl font-black text-emerald-600">{ready}</strong>
                  </div>
                  <div className="bg-amber-50/50 border border-amber-100 p-4 rounded-2xl text-center md:text-left">
                    <span className="text-[10px] text-amber-700 uppercase block font-bold mb-1">Needs Review</span>
                    <strong className="text-2xl sm:text-3xl font-black text-amber-600">{review}</strong>
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      </div>

      {/* --- HOW IT WORKS (Upgraded Steps & Deepened Numbers) --- */}
      <div id="how-it-works" className="w-full bg-slate-100/60 py-20 sm:py-24 px-4 sm:px-6 border-y border-slate-200">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-12 sm:mb-16 px-4">
            <h2 className="text-2xl sm:text-3xl font-extrabold text-slate-900 mb-4">How ClaimSense Works</h2>
            <p className="text-sm sm:text-base text-slate-500 font-medium max-w-2xl mx-auto">A streamlined, four-step workflow designed specifically for hospital claims officers. No technical expertise required.</p>
          </div>
          
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
            {STEPS.map((step) => (
              <div 
                key={step.n} 
                className="group relative bg-white p-6 sm:p-8 rounded-3xl shadow-sm hover:shadow-xl transition-all duration-500 text-left overflow-hidden border border-slate-200 hover:border-transparent"
              >
                <div className="absolute inset-0 bg-gradient-to-br from-hakiki-blue to-hakiki-teal opacity-0 group-hover:opacity-100 transition-opacity duration-500 -z-10"></div>
                <div className="absolute inset-[2px] bg-white rounded-[22px] z-0"></div>
                
                <div className="relative z-10 flex flex-col h-full">
                  <div className="flex items-center justify-between mb-6">
                    <div className="h-12 w-12 rounded-xl bg-hakiki-light text-hakiki-teal flex items-center justify-center group-hover:scale-110 transition-transform duration-300 shrink-0">
                      <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        {step.icon}
                      </svg>
                    </div>
                    {/* Darkened Step Numbers for better visibility */}
                    <span className="text-4xl sm:text-5xl font-black text-slate-200 group-hover:text-hakiki-light transition-colors duration-300">{step.n}</span>
                  </div>
                  <h4 className="text-base sm:text-lg font-bold text-slate-900 mb-3">{step.title}</h4>
                  <p className="text-xs sm:text-sm text-slate-500 leading-relaxed font-medium">{step.body}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* --- WHY CLAIMSENSE (Value Props) --- */}
      <div className="w-full bg-white py-20 sm:py-24 px-4 sm:px-6">
        <div className="max-w-5xl mx-auto">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-10 sm:gap-12 text-center">
            <div className="px-4">
              <div className="mx-auto h-16 w-16 bg-blue-50 rounded-2xl flex items-center justify-center mb-6">
                <svg className="w-8 h-8 text-hakiki-blue" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" /></svg>
              </div>
              <h3 className="text-base sm:text-lg font-bold text-slate-900 mb-3">Human-in-the-Loop</h3>
              <p className="text-xs sm:text-sm text-slate-500 font-medium leading-relaxed">The AI highlights the errors and suggests fixes, but you retain full control. No automated rejections, just intelligent assistance.</p>
            </div>
            <div className="px-4">
              <div className="mx-auto h-16 w-16 bg-teal-50 rounded-2xl flex items-center justify-center mb-6">
                <svg className="w-8 h-8 text-hakiki-teal" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" /></svg>
              </div>
              <h3 className="text-base sm:text-lg font-bold text-slate-900 mb-3">openIMIS Native</h3>
              <p className="text-xs sm:text-sm text-slate-500 font-medium leading-relaxed">Built from the ground up to integrate seamlessly with standard openIMIS FHIR structures. No complex implementation required.</p>
            </div>
            <div className="px-4">
              <div className="mx-auto h-16 w-16 bg-amber-50 rounded-2xl flex items-center justify-center mb-6">
                {/* Updated Icon: Upward Trending Chart for Instant ROI */}
                <svg className="w-8 h-8 text-amber-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" /></svg>
              </div>
              <h3 className="text-base sm:text-lg font-bold text-slate-900 mb-3">Instant ROI</h3>
              <p className="text-xs sm:text-sm text-slate-500 font-medium leading-relaxed">Catch missing data, mismatched codes, and policy violations instantly before they ever hit the ledger, accelerating your hospital's cash flow.</p>
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
            <svg className="w-5 h-5 text-hakiki-teal transform group-hover:translate-x-1 transition-transform duration-200" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M14 5l7 7m0 0l-7 7m7-7H3" />
            </svg>
          </button>
        </div>
      </div>

      <footer className="px-6 py-6 text-center text-xs text-slate-500 font-medium bg-slate-950">
        ClaimSense • Built for seamless openIMIS integration • By Hakiki Health
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
};
