export const DEPARTMENT_GUIDES = {
  maternity: {
    label: "Maternity",
    steps: [
      { title: "Confirm gestation & delivery mode", required: true },
      { title: "Attach partograph reference", required: true },
      { title: "Code maternal complications separately", required: true },
      { title: "Confirm newborn registration if applicable", required: false },
    ],
  },
  renal: {
    label: "Renal Unit",
    steps: [
      { title: "Log session count for the billing period", required: true },
      { title: "Attach latest creatinine / eGFR reading", required: true },
      { title: "Specify vascular access type", required: true },
      { title: "Note any missed sessions", required: false },
    ],
  },
  surgical: {
    label: "Surgical",
    steps: [
      { title: "Match procedure code to consent form", required: true },
      { title: "Itemise theatre time & anaesthesia type", required: true },
      { title: "Attach post-op notes for overnight stays", required: true },
      { title: "Flag any intra-op complication", required: false },
    ],
  },
  outpatient: {
    label: "Outpatient",
    steps: [
      { title: "Confirm single-visit diagnosis code", required: true },
      { title: "Match prescribed items to diagnosis", required: true },
      { title: "Confirm visit duration band", required: false },
    ],
  },
};