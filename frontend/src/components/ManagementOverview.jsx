import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api/client.js";

const CARD = "rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950 p-5 shadow-sm";
const number = (value) => Number(value || 0).toLocaleString();
const percent = (value) => `${Number(value || 0).toFixed(1)}%`;

function SyntheticBadge() {
  return <span className="inline-flex rounded-md border border-amber-200 dark:border-amber-900 bg-amber-50 dark:bg-amber-950/40 px-2 py-1 text-[10px] font-bold uppercase tracking-wide text-amber-700 dark:text-amber-300">Synthetic demo data</span>;
}

function StatusDonut({ rows }) {
  const values = rows.map((row) => Number(row.claim_count || 0));
  const total = values.reduce((sum, value) => sum + value, 0);
  const ready = Number(rows.find((row) => row.status === "Ready for Submission")?.claim_count || 0);
  const review = Number(rows.find((row) => row.status === "Needs Review")?.claim_count || 0);
  const high = Math.max(0, total - ready - review);
  const readyEnd = total ? ready / total * 100 : 0;
  const reviewEnd = total ? readyEnd + review / total * 100 : 0;
  const style = { background: `conic-gradient(#0f9f8f 0% ${readyEnd}%, #f59e0b ${readyEnd}% ${reviewEnd}%, #ef4444 ${reviewEnd}% 100%)` };
  return (
    <div className="flex flex-wrap items-center gap-6">
      <div className="relative h-36 w-36 rounded-full" style={style} role="img" aria-label={`${ready} ready, ${review} needing review, ${high} high risk`}>
        <div className="absolute inset-4 flex flex-col items-center justify-center rounded-full bg-white dark:bg-slate-950"><span className="text-2xl font-bold text-slate-800 dark:text-slate-100">{number(total)}</span><span className="text-[10px] uppercase tracking-wide text-slate-500">claims</span></div>
      </div>
      <ul className="min-w-48 flex-1 space-y-2 text-sm">
        {[["Ready", ready, "bg-teal-500"], ["Needs review", review, "bg-amber-500"], ["High risk", high, "bg-red-500"]].map(([label, value, color]) => <li key={label} className="flex items-center gap-2 text-slate-600 dark:text-slate-300"><span className={`h-2.5 w-2.5 rounded-full ${color}`} />{label}<strong className="ml-auto text-slate-800 dark:text-slate-100">{number(value)}</strong></li>)}
      </ul>
    </div>
  );
}

function WeeklyTrend({ rows }) {
  const points = useMemo(() => {
    const data = rows.slice(-12);
    const max = Math.max(1, ...data.map((row) => Number(row.rework_rate || 0)));
    return data.map((row, index) => ({
      ...row,
      x: data.length < 2 ? 50 : 8 + index / (data.length - 1) * 84,
      y: 88 - Number(row.rework_rate || 0) / max * 72,
    }));
  }, [rows]);
  if (!points.length) return <p className="text-sm text-slate-500">No weekly records yet.</p>;
  return (
    <div>
      <svg viewBox="0 0 100 100" className="h-44 w-full overflow-visible" role="img" aria-label="Weekly rework rate trend">
        <polyline points={points.map((point) => `${point.x},${point.y}`).join(" ")} fill="none" stroke="#0f9f8f" strokeWidth="2.5" vectorEffect="non-scaling-stroke" />
        {points.map((point) => <circle key={point.week_start} cx={point.x} cy={point.y} r="2" fill="#0f9f8f"><title>{point.week_start}: {percent(point.rework_rate)}</title></circle>)}
      </svg>
      <div className="flex justify-between text-[10px] text-slate-500"><span>{String(points[0].week_start).slice(0, 10)}</span><span>{String(points[points.length - 1].week_start).slice(0, 10)}</span></div>
    </div>
  );
}

export default function ManagementOverview({ onBack }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try { setData(await api.getManagementAnalytics()); }
    catch (requestError) { setData(null); setError(requestError.message || "Could not load management analytics."); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  if (loading) return <div className="flex-1 overflow-y-auto p-6"><div className="mx-auto max-w-6xl animate-pulse space-y-4"><div className="h-10 w-72 rounded bg-slate-200 dark:bg-slate-800" /><div className="grid gap-4 md:grid-cols-4">{[1, 2, 3, 4].map((key) => <div key={key} className="h-28 rounded-2xl bg-slate-200 dark:bg-slate-800" />)}</div></div></div>;

  if (error) return (
    <section className="flex-1 overflow-y-auto p-6"><div className="mx-auto max-w-4xl space-y-5">
      <div className="flex items-center justify-between"><button type="button" onClick={onBack} className="text-sm font-semibold text-teal-700 dark:text-teal-400">← Claims</button><SyntheticBadge /></div>
      <div role="alert" className="rounded-2xl border border-amber-200 dark:border-amber-900 bg-white dark:bg-slate-950 p-6">
        <h1 className="text-xl font-bold text-slate-800 dark:text-slate-100">Management Overview</h1>
        <p className="mt-3 text-sm text-slate-600 dark:text-slate-300">{error.includes("Analytics requires Oracle backend") ? "Analytics requires Oracle backend." : error}</p>
        <button type="button" onClick={load} className="mt-4 rounded-lg bg-teal-700 px-4 py-2 text-sm font-semibold text-white">Try again</button>
      </div>
    </div></section>
  );

  const kpis = data?.kpis || {};
  const ledger = data?.ledger_status || {};
  return (
    <section className="flex-1 overflow-y-auto p-5 sm:p-7">
      <div className="mx-auto max-w-6xl space-y-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div><button type="button" onClick={onBack} className="mb-2 text-xs font-semibold text-teal-700 dark:text-teal-400">← Claims</button><h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">Management Overview</h1><p className="mt-1 text-sm text-slate-500">Aggregate workflow indicators for the synthetic facility workload.</p></div>
          <div className="flex items-center gap-3"><SyntheticBadge /><button type="button" onClick={load} className="rounded-lg border border-slate-300 dark:border-slate-700 px-3 py-2 text-sm font-semibold text-slate-700 dark:text-slate-200">Refresh</button></div>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {[["Total claims", number(kpis.total_claims)], ["Ready", percent(kpis.ready_percent)], ["Rework rate", percent(kpis.rework_rate)], ["Ledger entries", number(kpis.ledger_entries)]].map(([label, value]) => <article key={label} className={CARD}><p className="text-xs font-bold uppercase tracking-wide text-slate-500">{label}</p><p className="mt-3 text-3xl font-bold text-slate-900 dark:text-slate-100">{value}</p></article>)}
        </div>
        <div className="grid gap-4 lg:grid-cols-2">
          <article className={CARD}><h2 className="mb-5 text-base font-bold text-slate-800 dark:text-slate-100">Claim status</h2><StatusDonut rows={data.claims_by_status || []} /></article>
          <article className={CARD}><h2 className="mb-5 text-base font-bold text-slate-800 dark:text-slate-100">Average score by department</h2><div className="space-y-4">{(data.score_by_department || []).map((row) => <div key={row.department}><div className="mb-1 flex justify-between text-sm"><span className="capitalize text-slate-600 dark:text-slate-300">{row.department}</span><strong className="text-slate-800 dark:text-slate-100">{Number(row.avg_score || 0).toFixed(1)} <span className="font-normal text-slate-500">({number(row.claims)})</span></strong></div><div className="h-2 rounded-full bg-slate-100 dark:bg-slate-800"><div className="h-full rounded-full bg-teal-600" style={{ width: `${Math.max(0, Math.min(100, Number(row.avg_score || 0)))}%` }} /></div></div>)}</div></article>
          <article className={CARD}><h2 className="mb-4 text-base font-bold text-slate-800 dark:text-slate-100">Most common failed checks</h2>{(data.top_failed_rules || []).length ? <ol className="space-y-3">{data.top_failed_rules.slice(0, 8).map((row) => <li key={row.rule_id} className="flex justify-between gap-4 border-b border-slate-100 dark:border-slate-800 pb-2 text-sm"><span className="text-slate-600 dark:text-slate-300">{row.rule_name || row.rule_id}</span><strong className="text-amber-700 dark:text-amber-300">{number(row.failures)}</strong></li>)}</ol> : <p className="text-sm text-slate-500">No failed rules recorded.</p>}</article>
          <article className={CARD}><h2 className="mb-4 text-base font-bold text-slate-800 dark:text-slate-100">Weekly rework trend</h2><WeeklyTrend rows={data.rework_trend_weekly || []} /></article>
          <article className={CARD}><h2 className="mb-4 text-base font-bold text-slate-800 dark:text-slate-100">Department sign-off progress</h2><div className="space-y-4">{(data.signoff_progress || []).map((row) => { const total = Number(row.pending || 0) + Number(row.signed_off || 0); const done = total ? Number(row.signed_off || 0) / total * 100 : 0; return <div key={row.department}><div className="mb-1 flex justify-between text-sm"><span className="capitalize text-slate-600 dark:text-slate-300">{row.department}</span><span className="text-slate-500">{number(row.signed_off)} signed · {number(row.pending)} pending</span></div><div className="h-2 rounded-full bg-slate-100 dark:bg-slate-800"><div className="h-full rounded-full bg-teal-600" style={{ width: `${done}%` }} /></div></div>; })}</div></article>
          <article className={CARD}><h2 className="mb-4 text-base font-bold text-slate-800 dark:text-slate-100">Ledger and last anchor</h2><dl className="grid grid-cols-2 gap-4 text-sm"><div><dt className="text-slate-500">Ledger entries</dt><dd className="mt-1 font-semibold text-slate-800 dark:text-slate-100">{number(ledger.entries)}</dd></div><div><dt className="text-slate-500">Unanchored entries</dt><dd className="mt-1 font-semibold text-slate-800 dark:text-slate-100">{number(ledger.unanchored_entries)}</dd></div><div><dt className="text-slate-500">Last anchor date</dt><dd className="mt-1 break-words font-semibold text-slate-800 dark:text-slate-100">{ledger.last_anchor_at ? new Date(ledger.last_anchor_at).toLocaleString() : "No anchor recorded"}</dd></div><div><dt className="text-slate-500">Transaction</dt><dd className="mt-1 break-all font-mono text-xs text-slate-700 dark:text-slate-300">{ledger.last_anchor_tx || "—"}</dd></div></dl></article>
        </div>
      </div>
    </section>
  );
}
