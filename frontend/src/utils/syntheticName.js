import nameParts from "../data/syntheticNameParts.js";

function syntheticIndex(reference) {
  const match = /^SYN-(\d{6})$/.exec(String(reference || ""));
  return match ? Number(match[1]) : null;
}

export function syntheticDisplayName(reference) {
  const index = syntheticIndex(reference);
  if (index === null) return null;
  const { first, middle, surname } = nameParts;
  return `${first[(index * 7) % first.length]} ${middle[(index * 11) % middle.length]} ${surname[(index * 13) % surname.length]}`;
}

export function displayPatientName(claim) {
  if (claim?.is_synthetic) {
    const fromPatientReference = syntheticDisplayName(claim.patient_id);
    if (fromPatientReference) return fromPatientReference;

    // Older synthetic rows may not have a SYN patient reference yet. Derive a
    // stable, display-only reference from the claim number without persisting it.
    const claimNumber = String(claim.id || "").match(/(\d{1,6})$/)?.[1];
    if (claimNumber) {
      const displayReference = `SYN-${claimNumber.padStart(6, "0")}`;
      return syntheticDisplayName(displayReference) || "Synthetic patient";
    }
    return "Synthetic patient";
  }
  return claim?.patient_name || "Unknown Patient";
}
