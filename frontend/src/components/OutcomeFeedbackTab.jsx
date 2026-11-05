import { useEffect, useMemo, useState } from "react";
import PropTypes from "prop-types";
import { api } from "../api/client.js";

const STORAGE_PREFIX = "hakiki:claim-outcomes:";
const OUTCOME_OPTIONS = ["Submitted", "Queried", "Rejected", "Resubmitted", "Paid", "Other"];
const REASON_OPTIONS = [
  "Missing documentation",
  "Coding or service mismatch",
  "Preauthorization",
  "Eligibility or coverage",
  "Tariff or amount",
  "System or integration issue",
  "Other",
];

function readAllEvents() {
  const events = [];
  try {
    for (let index = 0; index < window.localStorage.length; index += 1) {
      const key = window.localStorage.key(index);
      if (!key?.startsWith(STORAGE_PREFIX)) continue;
      const parsed = JSON.parse(window.localStorage.getItem(key) || "[]");
      if (Array.isArray(parsed)) events.push(...parsed);
    }
  } catch {
    return events;
  }
  return events.sort((a, b) => b.recordedAt.localeCompare(a.recordedAt));
}

export default function OutcomeFeedbackTab({ claim, privacyMode = false }) {
  const storageKey = `${STORAGE_PREFIX}${claim.id}`;
  const [allEvents, setAllEvents] = useState(() => readAllEvents());
  const [outcome, setOutcome] = useState("Queried");
  const [reasonCategory, setReasonCategory] = useState(REASON_OPTIONS[0]);
  const [note, setNote] = useState("");
  const [saveError, setSaveError] = useState("");
  const [storageState, setStorageState] = useState("loading");
  const claimEvents = allEvents.filter((event) => event.claimId === claim.id);
  const queryEvents = allEvents.filter((event) => ["Queried", "Rejected"].includes(event.outcome) && event.reasonCategory);
  const groupedReasons = useMemo(() => {
    const counts = new Map();
    queryEvents.forEach((event) => counts.set(event.reasonCategory, (counts.get(event.reasonCategory) || 0) + 1));
    return [...counts.entries()].sort((a, b) => b[1] - a[1]);
  }, [queryEvents]);
  const latestByClaim = useMemo(() => {
    const latest = new Map();
    allEvents.forEach((event) => {
      if (!latest.has(event.claimId)) latest.set(event.claimId, event);
    });
    return [...latest.values()];
  }, [allEvents]);

  useEffect(() => {
    const refresh = () => setAllEvents(readAllEvents());
    window.addEventListener("storage", refresh);
    const localEvents = readAllEvents();
    api.getOutcomes().then(async ({ outcomes = [] }) => {
      if (outcomes.length) {
        setAllEvents(outcomes);
        setStorageState("saved");
      } else if (localEvents.length) {
        await Promise.allSettled(localEvents.map((event) => api.saveOutcome(event)));
        const migrated = await api.getOutcomes();
        setAllEvents(migrated.outcomes || localEvents);
        setStorageState("saved");
      } else {
        setAllEvents([]);
        setStorageState("saved");
      }
    }).catch(() => {
      setAllEvents(localEvents);
      setStorageState("local");
    });
    return () => window.removeEventListener("storage", refresh);
  }, []);

  const recordOutcome = async (event) => {
    event.preventDefault();
    setSaveError("");
    const record = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      claimId: claim.id,
      department: claim.department || "Unassigned",
      outcome,
      reasonCategory: ["Queried", "Rejected"].includes(outcome) ? reasonCategory : "",
      note: note.trim(),
      recordedAt: new Date().toISOString(),
    };
    const existing = (() => {
      try {
        const parsed = JSON.parse(window.localStorage.getItem(storageKey) || "[]");
        return Array.isArray(parsed) ? parsed : [];
      } catch {
        return [];
      }
    })();
    try {
      window.localStorage.setItem(storageKey, JSON.stringify([record, ...existing]));
    } catch {
      // Continue to the backend; the local copy is only the offline fallback.
    }
    try {
      setStorageState("saving");
      await api.saveOutcome(record);
      const refreshed = await api.getOutcomes();
      setAllEvents(refreshed.outcomes || [record, ...allEvents]);
      setStorageState("saved");
      setNote("");
      setSaveError("");
    } catch {
      try {
        window.localStorage.setItem(storageKey, JSON.stringify([record, ...existing]));
        setAllEvents(readAllEvents());
        setStorageState("local");
        setNote("");
        setSaveError("");
      } catch {
        setSaveError("Could not save this outcome locally or to the backend.");
      }
    }
  };

  return (
    <div className="space-y-4">
      <section className="bg-white dark:bg-slate-950 border border-slate-200/80 dark:border-slate-850 rounded-2xl p-6 shadow-sm">
        <h3 className="text-sm font-bold text-slate-800 dark:text-slate-200">Claim outcome feedback</h3>
        <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 mb-5">
          Log the result and any query reason from the facility&apos;s claims workflow. Review recurring issues by department.
        </p>
        <p role="status" className="-mt-3 mb-4 text-xs text-slate-500 dark:text-slate-400">
          {storageState === "saving" ? "Saving outcome to Hakiki…"
            : storageState === "saved" ? "Outcome history is available from the shared backend."
              : storageState === "local" ? "Backend unavailable; outcomes are stored in this browser."
                : "Loading outcome history…"}
        </p>
        <form onSubmit={recordOutcome} className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <label className="text-xs font-semibold text-slate-600 dark:text-slate-400">
            Outcome
            <select value={outcome} onChange={(event) => setOutcome(event.target.value)} className="mt-1.5 w-full text-sm font-normal p-2.5 border border-slate-200 dark:border-slate-700 rounded-lg bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-200">
              {OUTCOME_OPTIONS.map((item) => <option key={item}>{item}</option>)}
            </select>
          </label>
          {["Queried", "Rejected"].includes(outcome) && (
            <label className="text-xs font-semibold text-slate-600 dark:text-slate-400">
              Query / rejection theme
              <select value={reasonCategory} onChange={(event) => setReasonCategory(event.target.value)} className="mt-1.5 w-full text-sm font-normal p-2.5 border border-slate-200 dark:border-slate-700 rounded-lg bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-200">
                {REASON_OPTIONS.map((item) => <option key={item}>{item}</option>)}
              </select>
            </label>
          )}
          <label className="md:col-span-2 text-xs font-semibold text-slate-600 dark:text-slate-400">
            What happened / action taken
            <textarea value={privacyMode && note ? "********" : note} readOnly={privacyMode} onChange={(event) => setNote(event.target.value)} rows={3} placeholder="Record the payer feedback, correction, or follow-up action" className="mt-1.5 w-full text-sm font-normal p-2.5 border border-slate-200 dark:border-slate-700 rounded-lg bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-200" />
          </label>
          {saveError && <p role="alert" className="md:col-span-2 text-xs text-red-600">{saveError}</p>}
          <div className="md:col-span-2">
            <button type="submit" className="rounded-lg px-4 py-2 text-sm font-semibold text-white bg-teal-700 hover:bg-teal-800">Record outcome update</button>
          </div>
        </form>
      </section>

      <section className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <div className="bg-white dark:bg-slate-950 border border-slate-200/80 dark:border-slate-850 rounded-xl p-4">
          <p className="text-xs text-slate-500 dark:text-slate-400">Claims with recorded outcomes</p>
          <p className="text-2xl font-bold text-slate-800 dark:text-slate-100 mt-1">{latestByClaim.length}</p>
        </div>
        <div className="bg-white dark:bg-slate-950 border border-slate-200/80 dark:border-slate-850 rounded-xl p-4">
          <p className="text-xs text-slate-500 dark:text-slate-400">Query / rejection updates</p>
          <p className="text-2xl font-bold text-slate-800 dark:text-slate-100 mt-1">{queryEvents.length}</p>
        </div>
        <div className="bg-white dark:bg-slate-950 border border-slate-200/80 dark:border-slate-850 rounded-xl p-4">
          <p className="text-xs text-slate-500 dark:text-slate-400">Most common logged reason</p>
          <p className="text-sm font-bold text-slate-800 dark:text-slate-100 mt-2">{groupedReasons[0]?.[0] || "No reasons logged yet"}</p>
          {groupedReasons[0] && <p className="text-xs text-slate-500 mt-1">{groupedReasons[0][1]} logged updates</p>}
        </div>
      </section>

      <section className="bg-white dark:bg-slate-950 border border-slate-200/80 dark:border-slate-850 rounded-2xl p-6 shadow-sm">
        <h4 className="text-sm font-bold text-slate-800 dark:text-slate-200 mb-4">Outcome history for this claim</h4>
        {claimEvents.length === 0 ? (
          <p className="text-sm text-slate-500 dark:text-slate-400">No outcome updates recorded for this claim yet.</p>
        ) : (
          <ol className="space-y-3">
            {claimEvents.map((event) => (
              <li key={event.id} className="border-l-2 border-teal-400 pl-4 py-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-semibold text-slate-800 dark:text-slate-200">{event.outcome}</span>
                  {event.reasonCategory && <span className="text-xs text-amber-700 dark:text-amber-400">· {event.reasonCategory}</span>}
                  <time className="text-[11px] text-slate-400 ml-auto">{new Date(event.recordedAt).toLocaleString()}</time>
                </div>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">{privacyMode && event.note ? "********" : event.note || "No note recorded."}</p>
                <p className="text-[11px] text-slate-400 mt-1">Department: {event.department}</p>
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  );
}

OutcomeFeedbackTab.propTypes = {
  claim: PropTypes.shape({
    id: PropTypes.string.isRequired,
    department: PropTypes.string,
  }).isRequired,
  privacyMode: PropTypes.bool,
};
