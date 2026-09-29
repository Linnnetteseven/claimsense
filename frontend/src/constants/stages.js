// Claim lifecycle stages for the queue. Mirrors backend services/stages.py.
export const STAGES = [
  { key: "todo", label: "To do", hint: "Needs you: errors, warnings, or sent back by SHA" },
  { key: "ready", label: "Ready", hint: "100 and not yet handed off" },
  { key: "with_sha", label: "With SHA", hint: "Handed off; waiting for SHA's answer" },
  { key: "closed", label: "Closed", hint: "Approved, paid or cancelled by SHA; read-only" },
];

const CLOSED_SHA_STATES = new Set(["approved", "payment_processing", "paid", "cancelled"]);

export function stageOf(claim) {
  const sha = claim._sha_state;
  if (sha) {
    if (sha.action_needed) return "todo";
    return CLOSED_SHA_STATES.has(sha.state) ? "closed" : "with_sha";
  }
  if (claim._status === "handed_off") return "with_sha";
  const p = claim._preview;
  if (p && p.error_count === 0 && p.warning_count === 0) return "ready";
  return "todo";
}
