import PropTypes from "prop-types";

// SHA's answer to a handed-off claim (forwarded by the HIS), parsed by the backend.
const TONES = {
  approved: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300",
  paid: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300",
  payment_processing: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300",
  sent_back: "bg-red-100 text-red-800 dark:bg-red-950/50 dark:text-red-300",
  rejected: "bg-red-100 text-red-800 dark:bg-red-950/50 dark:text-red-300",
  payment_declined: "bg-red-100 text-red-800 dark:bg-red-950/50 dark:text-red-300",
};
const NEUTRAL = "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200";

export default function ShaStateBadge({ state, compact = false }) {
  if (!state) return null;
  return (
    <span
      title={`SHA state: ${state.sha_code}`}
      className={`inline-flex items-center rounded-md font-bold ${compact ? "text-[10px] px-1.5 py-0.5" : "text-xs px-2 py-1"} ${
        TONES[state.state] ?? NEUTRAL
      }`}
    >
      SHA: {state.label}
    </span>
  );
}

ShaStateBadge.propTypes = {
  state: PropTypes.shape({ state: PropTypes.string, label: PropTypes.string, sha_code: PropTypes.string }),
  compact: PropTypes.bool,
};
