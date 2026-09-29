import PropTypes from "prop-types";
import { ALWAYS_SHOWN, CLAIM_FIELDS, PATIENT_FIELDS } from "../constants/claimFields.js";

function coverageStatus(claim) {
  const end = claim.coverage_end_date;
  if (!end) return { text: "Unknown: no coverage end date", tone: "slate" };
  const visit = claim.visit_date || new Date().toISOString().slice(0, 10);
  return end >= visit
    ? { text: `Active on the visit date (until ${end})`, tone: "green" }
    : { text: `Expired on ${end}, before the visit`, tone: "red" };
}

const TONE = {
  green: "text-emerald-800 bg-emerald-50 border-emerald-200 dark:text-emerald-300 dark:bg-emerald-950/30 dark:border-emerald-900/50",
  red: "text-red-800 bg-red-50 border-red-200 dark:text-red-300 dark:bg-red-950/30 dark:border-red-900/50",
  slate: "text-slate-700 bg-slate-50 border-slate-200 dark:text-slate-200 dark:bg-slate-900 dark:border-slate-700",
};

function Field({ field, label, value, highlighted }) {
  const empty = value === undefined || value === null || value === "";
  return (
    <div
      id={`claim-field-${field}`}
      className={`rounded-lg p-2 -m-2 transition-colors duration-700 ${
        highlighted ? "bg-amber-100 ring-2 ring-amber-500 dark:bg-amber-900/40" : ""
      }`}
    >
      <span className="text-xs text-slate-500 dark:text-slate-400 block">{label}</span>
      <span className={`font-semibold ${empty ? "text-red-700 dark:text-red-400 italic" : "text-slate-800 dark:text-slate-100"} ${
        /(_id|_code|_date|^id$|dob|preauth)/.test(field) ? "font-mono" : ""
      }`}>
        {empty ? "Missing" : field === "claimed_amount" ? `KES ${Number(value).toLocaleString()}` : String(value)}
      </span>
    </div>
  );
}

Field.propTypes = {
  field: PropTypes.string.isRequired,
  label: PropTypes.string.isRequired,
  value: PropTypes.any,
  highlighted: PropTypes.bool,
};

function FieldGrid({ fields, claim, highlight }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-4 text-sm">
      {fields
        .filter(([f]) => ALWAYS_SHOWN.has(f) || (claim[f] !== undefined && claim[f] !== "") || highlight === f)
        .map(([f, label]) => (
          <Field key={f} field={f} label={label} value={claim[f]} highlighted={highlight === f} />
        ))}
    </div>
  );
}

FieldGrid.propTypes = { fields: PropTypes.array.isRequired, claim: PropTypes.object.isRequired, highlight: PropTypes.string };

export function PatientDetails({ claim, highlight }) {
  const coverage = coverageStatus(claim);
  return (
    <div className="bg-white dark:bg-slate-950 border border-slate-200/80 dark:border-slate-800 rounded-2xl p-6 shadow-sm space-y-6">
      <h3 className="text-sm font-bold text-slate-800 dark:text-slate-100 border-b border-slate-100 dark:border-slate-800 pb-3">
        Patient and coverage
      </h3>
      <FieldGrid fields={PATIENT_FIELDS} claim={claim} highlight={highlight} />
      <div>
        <span className="text-xs text-slate-500 dark:text-slate-400 block">Coverage status</span>
        <span className={`inline-block mt-1 rounded-full border px-2.5 py-0.5 text-xs font-semibold ${TONE[coverage.tone]}`}>
          {coverage.text}
        </span>
      </div>
    </div>
  );
}

PatientDetails.propTypes = { claim: PropTypes.object.isRequired, highlight: PropTypes.string };

export function ClaimInfo({ claim, highlight }) {
  const items = Array.isArray(claim.items) ? claim.items : [];
  const net = (i) => (i.net ?? Number(i.quantity || 0) * Number(i.unit_price || 0));
  const total = items.reduce((sum, i) => sum + net(i), 0);
  return (
    <div className="bg-white dark:bg-slate-950 border border-slate-200/80 dark:border-slate-800 rounded-2xl p-6 shadow-sm space-y-6">
      <h3 className="text-sm font-bold text-slate-800 dark:text-slate-100 border-b border-slate-100 dark:border-slate-800 pb-3">
        Claim details and items
      </h3>
      <FieldGrid fields={CLAIM_FIELDS} claim={claim} highlight={highlight} />

      <div
        id="claim-field-items"
        className={`border-t border-slate-100 dark:border-slate-800 pt-5 rounded-lg transition-colors duration-700 ${
          highlight === "items" ? "bg-amber-100 ring-2 ring-amber-500 dark:bg-amber-900/40 p-2" : ""
        }`}
      >
        <h4 className="text-xs font-bold text-slate-600 dark:text-slate-300 uppercase tracking-widest mb-3">Service items</h4>
        {items.length === 0 ? (
          <p className="text-sm text-red-700 dark:text-red-400 italic">No items on this claim</p>
        ) : (
          <div className="border border-slate-200 dark:border-slate-800 rounded-xl overflow-x-auto text-xs">
            <table className="w-full text-left">
              <caption className="sr-only">Service items on this claim</caption>
              <thead className="bg-slate-50 dark:bg-slate-900 border-b border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-300 font-bold uppercase tracking-wider">
                <tr>
                  <th scope="col" className="p-3">#</th>
                  <th scope="col" className="p-3">Code</th>
                  <th scope="col" className="p-3">Description</th>
                  <th scope="col" className="p-3">Service dates</th>
                  <th scope="col" className="p-3 text-right">Qty</th>
                  <th scope="col" className="p-3 text-right">Unit price (KES)</th>
                  <th scope="col" className="p-3 text-right">Net (KES)</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800 text-slate-700 dark:text-slate-200">
                {items.map((item, index) => (
                  // Index key: items have no id of their own.
                  <tr key={index}>
                    <td className="p-3">{item.sequence ?? "?"}</td>
                    <td className="p-3 font-mono">{item.service_code || <span className="text-red-700 dark:text-red-400 italic">missing</span>}</td>
                    <td className="p-3">{item.description}</td>
                    <td className="p-3 font-mono whitespace-nowrap">
                      {item.service_start || "?"} to {item.service_end || "?"}
                    </td>
                    <td className="p-3 text-right">{item.quantity}</td>
                    <td className="p-3 text-right">{Number(item.unit_price || 0).toLocaleString()}</td>
                    <td className="p-3 text-right font-medium">{net(item).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="border-t border-slate-200 dark:border-slate-800 font-bold text-slate-800 dark:text-slate-100">
                  <td className="p-3" colSpan={6}>Items total</td>
                  <td className="p-3 text-right">{total.toLocaleString()}</td>
                </tr>
              </tfoot>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

ClaimInfo.propTypes = { claim: PropTypes.object.isRequired, highlight: PropTypes.string };
