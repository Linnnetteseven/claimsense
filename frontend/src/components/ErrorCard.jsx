import PropTypes from "prop-types";
import { CheckIcon, ErrorIcon, WarnIcon } from "./icons.jsx";
import {
  EDITABLE_FIELDS,
  PASS_STYLE,
  SEVERITY_STYLES,
} from "../constants/status.js";

const QUICK_FIXES = {
  "SHA-R1": "A09",
  "SHA-R2": "3500",
  "SHA-R3": null,
  "SHA-R4": "SHA-OPD-001",
  "SHA-R5": null,
  "SHA-R6": null,
  "SHA-R7": null,
};

function EditBox({ field, value, onChange }) {
  if (!field || !onChange || !EDITABLE_FIELDS.includes(field)) {
    return null;
  }

  const inputType =
    field === "claimed_amount"
      ? "number"
      : field === "visit_date" || field === "coverage_end_date"
        ? "date"
        : "text";

  return (
    <div className="mt-3">
      <label
        htmlFor={`correction-${field}`}
        className="block text-[10px] font-bold uppercase tracking-wider text-slate-400 dark:text-slate-500 mb-1.5"
      >
        Correction
      </label>

      <input
        id={`correction-${field}`}
        type={inputType}
        value={value ?? ""}
        onChange={(e) => onChange(field, e.target.value)}
        className="w-full text-xs font-semibold border border-slate-200 dark:border-slate-800 rounded-lg px-3.5 py-2.5 bg-white dark:bg-slate-950 text-slate-800 dark:text-slate-100 placeholder-slate-400 dark:placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-transparent transition-all"
        placeholder={`Enter correct ${field.replace(/_/g, " ")}...`}
      />
    </div>
  );
}

EditBox.propTypes = {
  field: PropTypes.string,
  value: PropTypes.oneOfType([PropTypes.string, PropTypes.number]),
  onChange: PropTypes.func,
};

export default function ErrorCard({
  result,
  explanation,
  fieldValue,
  onChange,
}) {
  const {
    passed,
    severity = "error",
    rule_id: ruleId,
    message,
    field,
    suggestion,
    suggested_value: suggestedValue,
    fix_value: fixValue,
  } = result;

  const style = passed
    ? PASS_STYLE
    : SEVERITY_STYLES[severity] ?? SEVERITY_STYLES.error;

  const fallbackFix = QUICK_FIXES[ruleId];

  const suggestedFix =
    suggestedValue ??
    fixValue ??
    suggestion ??
    fallbackFix;

  const hasSuggestedFix =
    !passed &&
    suggestedFix !== null &&
    suggestedFix !== undefined &&
    String(suggestedFix).trim() !== "" &&
    Boolean(field) &&
    Boolean(onChange) &&
    EDITABLE_FIELDS.includes(field);

  const applySuggestedFix = () => {
    if (hasSuggestedFix) {
      onChange(field, suggestedFix);
    }
  };

  return (
    <div
      className={`rounded-xl border ${style.border} ${style.bg} p-4 transition-all`}
    >
      <div className="flex items-start gap-3">
        <div className={`mt-0.5 shrink-0 ${style.icon ?? ""}`}>
          {passed ? (
            <CheckIcon className="w-5 h-5" />
          ) : severity === "warning" ? (
            <WarnIcon className="w-5 h-5" />
          ) : (
            <ErrorIcon className="w-5 h-5" />
          )}
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-3">
            <span
              className={`inline-flex items-center rounded-md px-2 py-1 text-[10px] font-bold uppercase tracking-wider ${
                passed
                  ? PASS_STYLE.badge
                  : style.badge
              }`}
            >
              {ruleId}
            </span>

            <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500">
              {passed ? "Passed" : severity}
            </span>
          </div>

          <p className="mt-2 text-sm font-semibold text-slate-800 dark:text-slate-100">
            {message}
          </p>

          {!passed && explanation && (
            <div className="mt-2">
              <p className="text-xs leading-5 text-slate-600 dark:text-slate-400">
                {explanation}
              </p>
            </div>
          )}

          {!passed && hasSuggestedFix && (
            <div className="mt-3 rounded-lg border border-teal-200/70 dark:border-teal-900/50 bg-white/70 dark:bg-slate-950/40 p-3">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-[10px] font-bold uppercase tracking-wider text-teal-700 dark:text-teal-400">
                    Suggested fix
                  </p>

                  <p className="mt-1 text-xs font-semibold text-slate-700 dark:text-slate-200 break-words">
                    Set{" "}
                    <span className="font-mono text-teal-700 dark:text-teal-400">
                      {field.replace(/_/g, " ")}
                    </span>{" "}
                    to{" "}
                    <span className="font-mono font-bold">
                      {String(suggestedFix)}
                    </span>
                  </p>
                </div>

                <button
                  type="button"
                  onClick={applySuggestedFix}
                  className="shrink-0 rounded-lg bg-teal-600 hover:bg-teal-700 active:scale-95 text-white text-[11px] font-bold px-3 py-2 transition-all shadow-sm"
                >
                  Apply fix
                </button>
              </div>
            </div>
          )}

          {!passed && field && onChange && (
            <EditBox
              field={field}
              value={fieldValue}
              onChange={onChange}
            />
          )}

          {!passed && field && onChange && (
            <p className="mt-2 text-[10px] leading-4 text-slate-400 dark:text-slate-500">
              Apply the suggested value above, or type your own correction
              before re-validating.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

ErrorCard.propTypes = {
  result: PropTypes.shape({
    passed: PropTypes.bool.isRequired,
    severity: PropTypes.string,
    rule_id: PropTypes.string.isRequired,
    message: PropTypes.string.isRequired,
    field: PropTypes.string,
    suggestion: PropTypes.string,
    suggested_value: PropTypes.oneOfType([
      PropTypes.string,
      PropTypes.number,
    ]),
    fix_value: PropTypes.oneOfType([
      PropTypes.string,
      PropTypes.number,
    ]),
  }).isRequired,

  explanation: PropTypes.string,
  fieldValue: PropTypes.oneOfType([
    PropTypes.string,
    PropTypes.number,
  ]),
  onChange: PropTypes.func,
};
