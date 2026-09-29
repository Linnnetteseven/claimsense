import PropTypes from "prop-types";
import { CheckIcon, ErrorIcon, WarnIcon } from "./icons.jsx";
import { FIELD_INPUTS, PASS_STYLE, SEVERITY_STYLES } from "../constants/status.js";

const INPUT_CLASS =
  "w-full text-xs font-semibold border border-slate-200 dark:border-slate-800 rounded-lg px-3 py-2 bg-white dark:bg-slate-950 text-slate-800 dark:text-slate-100 placeholder-slate-400 dark:placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-transparent transition-all";

const EMPTY_ITEM = {
  sequence: 1,
  service_code: "",
  description: "",
  quantity: 1,
  unit_price: 0,
  service_start: "",
  service_end: "",
};

function submitOnEnter(onSave) {
  return (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      onSave?.();
    }
  };
}

function FieldInput({ ruleId, field, value, onEdit, onSave }) {
  const { label, type, options } = FIELD_INPUTS[field];
  const id = `fix-${ruleId}-${field}`;
  return (
    <div>
      <label
        htmlFor={id}
        className="block text-[10px] font-bold uppercase tracking-wider text-slate-400 dark:text-slate-500 mb-1"
      >
        {label}
      </label>
      {type === "select" ? (
        <select id={id} value={value ?? ""} onChange={(e) => onEdit(field, e.target.value)} className={INPUT_CLASS}>
          <option value="">Select...</option>
          {options.map((opt) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
        </select>
      ) : (
        <input
          id={id}
          type={type}
          value={value ?? ""}
          onChange={(e) => onEdit(field, e.target.value)}
          onKeyDown={submitOnEnter(onSave)}
          className={INPUT_CLASS}
        />
      )}
    </div>
  );
}

FieldInput.propTypes = {
  ruleId: PropTypes.string.isRequired,
  field: PropTypes.string.isRequired,
  value: PropTypes.oneOfType([PropTypes.string, PropTypes.number]),
  onEdit: PropTypes.func.isRequired,
  onSave: PropTypes.func,
};

function ItemsEditor({ items, onEdit, onSave }) {
  const rows = Array.isArray(items) ? items : [];
  const update = (index, key, raw) => {
    const numeric = key === "quantity" || key === "unit_price" || key === "sequence";
    const value = numeric ? (raw === "" ? "" : Number(raw)) : raw;
    onEdit("items", rows.map((item, i) => (i === index ? { ...item, [key]: value } : item)));
  };
  const remove = (index) => onEdit("items", rows.filter((_, i) => i !== index));
  const add = () => onEdit("items", [...rows, { ...EMPTY_ITEM, sequence: rows.length + 1 }]);

  return (
    <div>
      <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400 dark:text-slate-500 mb-1">
        Service items
      </p>
      <div className="space-y-2">
        {rows.map((item, index) => {
          const label = (what) => `Item ${index + 1} ${what}`;
          const onKeyDown = submitOnEnter(onSave);
          return (
            // Index key: items have no id of their own.
            <div key={index} className="rounded-lg border border-slate-200 dark:border-slate-800 p-2 space-y-1.5">
              <div className="grid grid-cols-12 gap-1.5 items-center">
                <input
                  aria-label={label("sequence")}
                  title="Sequence"
                  type="number"
                  min="1"
                  value={item.sequence ?? ""}
                  onChange={(e) => update(index, "sequence", e.target.value)}
                  onKeyDown={onKeyDown}
                  className={`${INPUT_CLASS} col-span-2`}
                />
                <input
                  aria-label={label("intervention code")}
                  placeholder="SHA-12-001"
                  value={item.service_code ?? ""}
                  onChange={(e) => update(index, "service_code", e.target.value.toUpperCase())}
                  onKeyDown={onKeyDown}
                  className={`${INPUT_CLASS} col-span-4 font-mono ${item.service_code ? "" : "ring-2 ring-red-400"}`}
                />
                <input
                  aria-label={label("description")}
                  placeholder="Description"
                  value={item.description ?? ""}
                  onChange={(e) => update(index, "description", e.target.value)}
                  onKeyDown={onKeyDown}
                  className={`${INPUT_CLASS} col-span-5`}
                />
                <button
                  type="button"
                  onClick={() => remove(index)}
                  aria-label={`Remove item ${index + 1}`}
                  className="col-span-1 text-slate-400 hover:text-red-600 text-sm font-bold"
                >
                  ×
                </button>
              </div>
              <div className="grid grid-cols-12 gap-1.5 items-center">
                <input
                  aria-label={label("quantity")}
                  title="Quantity"
                  type="number"
                  min="1"
                  value={item.quantity ?? 1}
                  onChange={(e) => update(index, "quantity", e.target.value)}
                  onKeyDown={onKeyDown}
                  className={`${INPUT_CLASS} col-span-2`}
                />
                <input
                  aria-label={label("unit price")}
                  title="Unit price (KES)"
                  type="number"
                  min="0"
                  value={item.unit_price ?? 0}
                  onChange={(e) => update(index, "unit_price", e.target.value)}
                  onKeyDown={onKeyDown}
                  className={`${INPUT_CLASS} col-span-3`}
                />
                <input
                  aria-label={label("service start date")}
                  title="Service start"
                  type="date"
                  value={(item.service_start ?? "").slice(0, 10)}
                  onChange={(e) => update(index, "service_start", e.target.value)}
                  className={`${INPUT_CLASS} col-span-3 ${item.service_start ? "" : "ring-2 ring-red-400"}`}
                />
                <span className="col-span-1 text-center text-[10px] text-slate-400">to</span>
                <input
                  aria-label={label("service end date")}
                  title="Service end"
                  type="date"
                  value={(item.service_end ?? "").slice(0, 10)}
                  onChange={(e) => update(index, "service_end", e.target.value)}
                  className={`${INPUT_CLASS} col-span-3 ${item.service_end ? "" : "ring-2 ring-red-400"}`}
                />
              </div>
            </div>
          );
        })}
      </div>
      <button
        type="button"
        onClick={add}
        className="mt-2 text-[11px] font-semibold text-teal-700 dark:text-teal-400 hover:underline"
      >
        + Add item
      </button>
    </div>
  );
}

ItemsEditor.propTypes = {
  items: PropTypes.array,
  onEdit: PropTypes.func.isRequired,
  onSave: PropTypes.func,
};

export default function ErrorCard({ result, explanation, fixSteps, claim, onEdit, onApplyFix, onSave, busy }) {
  const {
    passed,
    severity = "error",
    rule_id: ruleId,
    message,
    field,
    fields,
    suggestion,
    suggested_value: suggestedValue,
    suggested_label: suggestedLabel,
  } = result;

  const style = passed ? PASS_STYLE : SEVERITY_STYLES[severity] ?? SEVERITY_STYLES.error;
  const editableFields = (fields ?? (field ? [field] : [])).filter((f) => FIELD_INPUTS[f]);
  const canEdit = !passed && Boolean(onEdit) && editableFields.length > 0;
  // Only offer one-click apply for a concrete value computed by the backend rule.
  const canApply =
    canEdit &&
    Boolean(onApplyFix) &&
    suggestedValue !== undefined &&
    suggestedValue !== null &&
    editableFields.length === 1;
  const advice = explanation || suggestion;

  return (
    <div className={`rounded-xl border ${style.border} ${style.bg} p-4 transition-all`}>
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
                passed ? PASS_STYLE.badge : style.badge
              }`}
            >
              {ruleId}
            </span>
            <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500">
              {passed ? "Passed" : severity}
            </span>
          </div>

          <p className="mt-2 text-sm font-semibold text-slate-800 dark:text-slate-100">{message}</p>

          {!passed && advice && (
            <p className="mt-2 text-xs leading-5 text-slate-600 dark:text-slate-400">{advice}</p>
          )}

          {!passed && fixSteps?.length > 0 && (
            <ol className="mt-2 list-decimal pl-5 space-y-0.5 text-xs leading-5 text-slate-600 dark:text-slate-400">
              {fixSteps.map((step) => (
                <li key={step}>{step}</li>
              ))}
            </ol>
          )}

          {canApply && (
            <div className="mt-3 rounded-lg border border-teal-200/70 dark:border-teal-900/50 bg-white/70 dark:bg-slate-950/40 p-3 flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-[10px] font-bold uppercase tracking-wider text-teal-700 dark:text-teal-400">
                  Suggested fix
                </p>
                <p className="mt-1 text-xs font-semibold text-slate-700 dark:text-slate-200 break-words">
                  {typeof suggestedValue === "object" ? (
                    <>{suggestedLabel ? suggestedLabel[0].toUpperCase() + suggestedLabel.slice(1) : "Apply the suggested correction"}</>
                  ) : (
                    <>
                      Set {FIELD_INPUTS[editableFields[0]].label.toLowerCase()} to{" "}
                      <span className="font-mono font-bold">{String(suggestedValue)}</span>
                    </>
                  )}
                </p>
              </div>
              <button
                type="button"
                disabled={busy}
                onClick={() => onApplyFix(editableFields[0], suggestedValue)}
                className="shrink-0 rounded-lg bg-teal-600 hover:bg-teal-700 disabled:opacity-60 active:scale-95 text-white text-[11px] font-bold px-3 py-2 transition-all shadow-sm"
              >
                Apply fix
              </button>
            </div>
          )}

          {canEdit && (
            <div className="mt-3 space-y-3">
              {editableFields.map((f) =>
                f === "items" ? (
                  <ItemsEditor key={f} items={claim?.items} onEdit={onEdit} onSave={onSave} />
                ) : (
                  <FieldInput
                    key={f}
                    ruleId={ruleId}
                    field={f}
                    value={claim?.[f]}
                    onEdit={onEdit}
                    onSave={onSave}
                  />
                )
              )}
              <p className="text-[10px] leading-4 text-slate-400 dark:text-slate-500">
                Press Enter or &quot;Save &amp; re-validate&quot; to save the correction and re-check every rule.
              </p>
            </div>
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
    fields: PropTypes.arrayOf(PropTypes.string),
    suggestion: PropTypes.string,
    suggested_value: PropTypes.oneOfType([PropTypes.string, PropTypes.number, PropTypes.array]),
    suggested_label: PropTypes.string,
  }).isRequired,
  explanation: PropTypes.string,
  fixSteps: PropTypes.arrayOf(PropTypes.string),
  claim: PropTypes.object,
  onEdit: PropTypes.func,
  onApplyFix: PropTypes.func,
  onSave: PropTypes.func,
  busy: PropTypes.bool,
};
