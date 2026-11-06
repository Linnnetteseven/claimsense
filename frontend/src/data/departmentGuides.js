// Draft: to be confirmed with the desk officers. These operational checklists support
// staff review and evidence capture; they are not all published SHA adjudication rules.
export const DEPARTMENT_GUIDES = {
  outpatient: {
    label: "Outpatient",
    steps: [
      { title: "Match the diagnosis and services to the encounter note", required: true },
      { title: "Confirm each billed service was recorded as delivered", required: true },
      { title: "Check the prescription and dispensing record for billed medicines", required: true },
      { title: "Confirm any required referral or authorization is linked", required: false },
    ],
  },
  maternity: {
    label: "Maternity",
    steps: [
      { title: "Record gestation, delivery mode, and delivery date from the maternity record", required: true },
      { title: "Attach the partograph reference when this is a labour or delivery claim", required: false },
      { title: "Check delivery and any post-delivery inpatient dates against the maternity global period", required: true },
      { title: "Link maternal and newborn records and itemize services billed", required: true },
      { title: "Confirm any intervention-specific preauthorization and required documents", required: false },
    ],
  },
  renal: {
    label: "Renal Unit",
    steps: [
      { title: "Match dialysis sessions and dates to the signed session log", required: true },
      { title: "Confirm the billed renal intervention and coverage are appropriate", required: true },
      { title: "Attach the clinical notes or investigations required for this treatment", required: true },
      { title: "Document missed sessions or any clinically justified extra sessions", required: true },
      { title: "Confirm any required preauthorization is linked to the claim", required: false },
    ],
  },
  surgical: {
    label: "Surgical",
    steps: [
      { title: "Match the requested, consented, and performed procedure", required: true },
      { title: "Confirm required preauthorization was approved before the procedure", required: true },
      { title: "Attach the operative note and itemize procedure and anaesthesia services", required: true },
      { title: "Link post-operative notes and discharge summary for an inpatient stay", required: true },
      { title: "Document complications or changes from the planned procedure", required: false },
    ],
  },
};
