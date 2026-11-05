import PropTypes from "prop-types";

export default function PrivacyToggle({ enabled, onToggle }) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-pressed={enabled}
      aria-label={`${enabled ? "Privacy on" : "Hide details"}: claims queue privacy ${enabled ? "on" : "off"}`}
      title="Masks patient and claim information across Hakiki screens"
      className={`inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-xs font-semibold transition-colors ${
        enabled
          ? "border-teal-500 bg-teal-50 text-teal-800 dark:bg-teal-950/40 dark:text-teal-300"
          : "border-slate-200 text-slate-600 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
      }`}
    >
      <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
        {enabled ? (
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 3l18 18M10.6 10.6a2 2 0 002.8 2.8M9.9 5.2A10.9 10.9 0 0112 5c5 0 8.3 4.5 9 7-.3 1.2-1 2.4-2 3.4M6.2 6.2C4.4 7.5 3.4 9.2 3 12c.7 2.5 4 7 9 7 1.2 0 2.2-.2 3.2-.7" />
        ) : (
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M2.5 12s3.4-7 9.5-7 9.5 7 9.5 7-3.4 7-9.5 7-9.5-7-9.5-7z M12 9a3 3 0 100 6 3 3 0 000-6z" />
        )}
      </svg>
      {enabled ? "Privacy on" : "Hide details"}
    </button>
  );
}

PrivacyToggle.propTypes = {
  enabled: PropTypes.bool.isRequired,
  onToggle: PropTypes.func.isRequired,
};
