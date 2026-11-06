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
  if (claim?.is_synthetic) return syntheticDisplayName(claim.patient_id) || "Synthetic patient";
  return claim?.patient_name || "Unknown Patient";
}
