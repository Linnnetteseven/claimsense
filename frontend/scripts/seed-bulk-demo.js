import { createClient } from "@supabase/supabase-js";
import { seedRow } from "./demo-data.js";

const url = process.env.SUPABASE_URL;
const serviceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY;

// DEMO_DRY_RUN=1 prints the generated rows as JSON instead of writing them.
const dryRun = Boolean(process.env.DEMO_DRY_RUN);

if (!dryRun && (!url || !serviceRoleKey)) {
  console.error(
    "Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY."
  );
  process.exit(1);
}

const supabase = dryRun ? null : createClient(url, serviceRoleKey, {
  auth: {
    autoRefreshToken: false,
    persistSession: false,
  },
});

const COUNT = Math.max(
  1,
  Number(process.env.DEMO_COUNT || 200)
);

// [name, code, SHA facility level]
const facilities = [
  ["Kerugoya Level 5 Referral Hospital", "KRG-L5", "5"],
  ["Kenyatta National Hospital", "KNH", "6"],
  ["Mama Lucy Kibaki Hospital", "MLKH", "5"],
  ["Nyeri County Referral Hospital", "NYR", "5"],
  ["Embu Level 5 Hospital", "EMB-L5", "5"],
  ["Kisumu County Referral Hospital", "KSM", "5"],
  ["Githurai Health Centre", "GTH-HC", "3"],
  ["Kangemi Dispensary", "KNG-DSP", "2"],
];

const firstNames = [
  "Wanjiku",
  "Akinyi",
  "Mwangi",
  "Kamau",
  "Njeri",
  "Otieno",
  "Wambui",
  "Brian",
  "Faith",
  "Mercy",
  "Kevin",
  "Derrick",
  "Joy",
  "Ann",
  "Mary",
  "Peter",
  "Jane",
  "Lucy",
  "Daniel",
  "Esther",
];

const lastNames = [
  "Mwangi",
  "Ochieng",
  "Kamau",
  "Njoroge",
  "Wanjiru",
  "Otieno",
  "Kariuki",
  "Maina",
  "Kiptoo",
  "Mutua",
  "Koech",
  "Muthoni",
  "Kimani",
  "Nyambura",
  "Wambui",
];

// ICD-11 MMS codes (checked against the WHO ICD-11 browser / findacode, Sep 2026).
const diagnoses = [
  { code: "1A40", description: "Gastroenteritis or colitis without specification of infectious agent" },
  { code: "CA40.Z", description: "Pneumonia, organism unspecified" },
  { code: "JB20.Z", description: "Single spontaneous delivery, unspecified", department: "maternity" },
  { code: "5A11", description: "Type 2 diabetes mellitus" },
  { code: "1A07", description: "Typhoid fever" },
  { code: "DD91.1", description: "Functional constipation" },
  { code: "BA00", description: "Essential hypertension" },
];

// SHA intervention codes from the MOH OCL catalogue (see backend/data/sha_interventions.csv).
// Level 2-3: capitated primary care, claimed on the PHC fund at zero price.
const phcServices = [
  { service_code: "SHA-12-001", description: "Consultation" },
  { service_code: "SHA-12-002", description: "Laboratory investigations" },
  { service_code: "SHA-12-004", description: "Prescription, drug administration and dispensing" },
];
// Level 5-6: SHA-07-001 "Management of medical cases", per diem at the OCL level tariff.
const PER_DIEM = { 5: 3920, 6: 4480 };
// SHA-08-005 Vaginal Delivery has no OCL tariff; demo price only.
const DELIVERY_PRICE = 10000;

function pad(value, length = 3) {
  return String(value).padStart(length, "0");
}

// Dates are stored as tokens and resolved at seed/reset time (see demo-data.js).
function daysAgo(days) {
  return `{{today-${days}d}}`;
}

function daysFromNow(days) {
  return `{{today+${days}d}}`;
}

function item(sequence, code, description, quantity, unitPrice, start, end = start) {
  return {
    sequence,
    service_code: code,
    description,
    quantity,
    unit_price: unitPrice,
    service_start: start,
    service_end: end,
  };
}

function makeClaim(index) {
  const first = firstNames[index % firstNames.length];
  const last = lastNames[(index * 3) % lastNames.length];
  const [facilityName, facilityCode, facilityLevel] = facilities[index % facilities.length];
  const primaryCare = Number(facilityLevel) <= 3;
  let diagnosis = diagnoses[index % diagnoses.length];
  // Deliveries happen at hospitals, not dispensaries.
  if (primaryCare && diagnosis.department === "maternity") diagnosis = diagnoses[0];
  const maternity = diagnosis.department === "maternity";

  const claimId = `SHA-DEMO-${new Date().getFullYear()}-${pad(index + 1, 4)}`;
  const admitDaysAgo = 3 + (index % 170);
  let visitDate = daysAgo(admitDaysAgo);
  let dischargeDate;
  let coverageEndDate = daysFromNow(30 + (index % 365));
  let fund = "SHIF";
  let items;

  if (primaryCare) {
    fund = "PHC";
    const count = 1 + (index % 3);
    items = phcServices.slice(0, count).map((s, i) => item(i + 1, s.service_code, s.description, 1, 0, visitDate));
  } else if (maternity) {
    dischargeDate = daysAgo(admitDaysAgo - 1);
    items = [item(1, "SHA-08-005", "Vaginal delivery", 1, DELIVERY_PRICE, visitDate, dischargeDate)];
  } else {
    const days = 1 + (index % 4);
    dischargeDate = daysAgo(admitDaysAgo - days);
    items = [
      item(1, "SHA-07-001", `Inpatient management of ${diagnosis.description.toLowerCase()} (per day)`,
        days, PER_DIEM[facilityLevel], visitDate, dischargeDate),
    ];
  }

  const calculatedAmount = items.reduce((sum, i) => sum + i.unit_price * i.quantity, 0);
  let claimedAmount = calculatedAmount;
  let diagnosisCode = diagnosis.code;
  let preauthRef;

  // Even-numbered claims are clean; odd ones cycle through one defect pattern per rule family.
  const pattern = index % 2 === 0 ? 0 : ((index - 1) / 2) % 12;

  if (pattern === 1) diagnosisCode = "ZZZ999";                   // INVALID_ICD11
  if (pattern === 2) diagnosisCode = "J18.9";                    // INVALID_ICD11 (ICD-10 entered)
  if (pattern === 3) visitDate = daysFromNow(14);                // VISIT_DATE + period checks
  if (pattern === 4) coverageEndDate = daysAgo(admitDaysAgo + 30); // COVERAGE_EXPIRED
  if (pattern === 5) claimedAmount = calculatedAmount + 1500;    // TOTAL_EQUALS_NET_SUM
  if (pattern === 6) items[0].service_code = "SHA-OPD-001";      // SHA_SERVICE_CODE_FORMAT
  if (pattern === 7) diagnosisCode = "";                         // MISSING_FIELDS
  if (pattern === 8) items[0].service_end = "";                  // SERVICED_PERIOD_PRESENT
  if (pattern === 9) {                                           // ITEM_SEQUENCE_VALID
    items.push({ ...items[0], sequence: 1 });
    claimedAmount += items[0].unit_price * items[0].quantity;
  }
  if (pattern === 10) fund = primaryCare ? "SHIF" : "PHC";       // PHC_ZERO_TOTAL / CAPITATION_PAYMENT
  if (pattern === 11) {                                          // PREAUTH_REQUIRED + TARIFF_CEILING
    items.splice(0, items.length, item(1, "SHA-16-001", "Haemodialysis session", 1, 12000, visitDate));
    dischargeDate = undefined;
    claimedAmount = 12000;
    diagnosisCode = "QB94.1";
    fund = "SHIF";
    if (Math.floor(index / 24) % 2 === 1) preauthRef = `PA-${pad(index, 5)}`;
  }
  const renal = diagnosisCode.startsWith("QB94");

  const dobYear = 1970 + (index % 40);

  return {
    id: claimId,
    patient_name: `${first} ${last}`,
    patient_id: `SHA-PAT-${pad(index + 1, 6)}`,
    dob: `${dobYear}-${pad((index % 12) + 1, 2)}-${pad((index % 27) + 1, 2)}`,
    gender: maternity || index % 2 === 0 ? "F" : "M",

    facility_name: facilityName,
    facility_code: facilityCode,
    facility_level: renal && Number(facilityLevel) < 3 ? "5" : facilityLevel,

    visit_date: visitDate,
    ...(dischargeDate ? { discharge_date: dischargeDate } : {}),

    diagnosis_code: diagnosisCode,
    diagnosis_description: renal ? "Care involving extracorporeal dialysis" : diagnosis.description,
    department: renal ? "renal" : diagnosis.department ?? (primaryCare ? "outpatient" : "medical"),
    ...(maternity ? { partograph_id: `PG-${pad(index + 1, 5)}` } : {}),
    fund,
    ...(preauthRef ? { preauth_ref: preauthRef } : {}),
    // Demo registry numbers, not real PUIDs.
    practitioner_id: `PUID-${pad(10000 + (index % 40), 7)}-${index % 10}`,
    practitioner_name: `Dr. ${lastNames[(index * 7) % lastNames.length]}`,

    coverage_start_date: "2025-01-01",
    coverage_end_date: coverageEndDate,
    scheme_code: "SHA-2025",

    items,
    claimed_amount: claimedAmount,
  };
}

const claims = Array.from(
  { length: COUNT },
  (_, index) => makeClaim(index)
);

const rows = claims.map(seedRow);

if (dryRun) {
  console.log(JSON.stringify(rows));
  process.exit(0);
}

console.log(`Preparing ${rows.length} demo claims...`);

const BATCH_SIZE = 100;

for (
  let start = 0;
  start < rows.length;
  start += BATCH_SIZE
) {
  const batch = rows.slice(
    start,
    start + BATCH_SIZE
  );

  const { error } = await supabase
    .from("claims")
    .upsert(batch, {
      onConflict: "claim_number",
    });

  if (error) {
    console.error(
      `Bulk seed failed at batch ${start}: ${error.message}`
    );
    process.exit(1);
  }

  console.log(
    `Seeded ${Math.min(
      start + batch.length,
      rows.length
    )}/${rows.length}`
  );
}

console.log(
  `Bulk demo seed complete: ${rows.length} claims.`
);
