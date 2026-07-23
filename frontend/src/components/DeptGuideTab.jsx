import PropTypes from "prop-types";
import { DEPARTMENT_GUIDES } from "../data/departmentGuides.js";

export default function DeptGuideTab({ department }) {
  const guide = DEPARTMENT_GUIDES[(department || "").toLowerCase()];

  if (!guide) {
    return (
      <div className="bg-white dark:bg-slate-950 border border-slate-200/80 dark:border-slate-850 rounded-2xl p-8 text-center shadow-sm">
        <p className="text-sm text-slate-500 dark:text-slate-400">
          No department set on this claim yet, so there&apos;s no SOP guide to show.
        </p>
      </div>
    );
  }

  return (
    <div className="bg-white dark:bg-slate-950 border border-slate-200/80 dark:border-slate-850 rounded-2xl p-6 shadow-sm">
      <h3 className="text-sm font-bold text-slate-800 dark:text-slate-200 border-b border-slate-100 dark:border-slate-850 pb-3 mb-5">
        {guide.label} · claim creation checklist
      </h3>
      <div className="space-y-4">
        {guide.steps.map((step, i) => (
          <div key={step.title} className="flex items-start gap-3">
            <span className="w-6 h-6 rounded-full bg-teal-50 dark:bg-teal-950/20 border border-teal-100 dark:border-teal-900/30 flex items-center justify-center text-teal-700 dark:text-teal-400 text-xs font-bold shrink-0 mt-0.5">
              {i + 1}
            </span>
            <div className="flex-1 flex items-center justify-between gap-3">
              <p className="text-sm text-slate-700 dark:text-slate-300">{step.title}</p>
              {step.required && (
                <span className="text-[10px] font-bold uppercase tracking-wide text-slate-400 dark:text-slate-500 border border-slate-200 dark:border-slate-800 rounded-full px-2 py-0.5 shrink-0">
                  Required
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

DeptGuideTab.propTypes = {
  department: PropTypes.string,
};