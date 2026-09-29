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

const facilities = [
  ["Kerugoya Level 5 Referral Hospital", "KRG-L5"],
  ["Kenyatta National Hospital", "KNH"],
  ["Mama Lucy Kibaki Hospital", "MLKH"],
  ["Nyeri County Referral Hospital", "NYR"],
  ["Embu Level 5 Hospital", "EMB-L5"],
  ["Kisumu County Referral Hospital", "KSM"],
  ["Nakuru Level 5 Hospital", "NKR-L5"],
  ["Machakos Level 5 Hospital", "MKS-L5"],
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
  { code: "GB61.Z", description: "Chronic kidney disease, stage unspecified" },
];

// SHA intervention codes from the DHA eClaims IG (see backend/data/sha_tariffs_sample.csv).
// Prices are demo values, not tariffs.
const services = [
  { service_code: "SHA-12-001", description: "Consultation", unit_price: 1200 },
  { service_code: "SHA-12-002", description: "Laboratory investigations", unit_price: 850 },
  { service_code: "SHA-12-004", description: "Prescription, drug administration and dispensing", unit_price: 1500 },
  { service_code: "SHA-12-003", description: "Basic radiological examinations", unit_price: 2200 },
];

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

function makeItems(index, serviceDay) {
  const itemCount = 1 + (index % 3);

  return Array.from({ length: itemCount }, (_, itemIndex) => {
    const service = services[(index + itemIndex) % services.length];

    return {
      sequence: itemIndex + 1,
      service_code: service.service_code,
      description: service.description,
      quantity: 1,
      unit_price: service.unit_price,
      service_start: serviceDay,
      service_end: serviceDay,
    };
  });
}

function makeClaim(index) {
  const first = firstNames[index % firstNames.length];
  const last = lastNames[(index * 3) % lastNames.length];

  const [facilityName, facilityCode] =
    facilities[index % facilities.length];

  const diagnosis =
    diagnoses[index % diagnoses.length];

  const claimId =
    `SHA-DEMO-${new Date().getFullYear()}-${pad(index + 1, 4)}`;

  const patientId =
    `SHA-PAT-${pad(index + 1, 6)}`;

  const visitDaysAgo = index % 180;
  const items = makeItems(index, daysAgo(visitDaysAgo));

  const calculatedAmount = items.reduce(
    (sum, item) =>
      sum +
      Number(item.unit_price) *
        Number(item.quantity),
    0
  );

  let visitDate = daysAgo(visitDaysAgo);
  let coverageEndDate = daysFromNow(30 + (index % 365));

  let diagnosisCode = diagnosis.code;
  let claimedAmount = calculatedAmount;

  let fund = "SHIF";
  let preauthRef;

  // Deliberately create a realistic mixture of clean,
  // warning and error claims for the demo. Even-numbered claims are clean;
  // odd ones cycle through one defect pattern per rule family.
  const pattern = index % 2 === 0 ? 0 : ((index - 1) / 2) % 12;

  if (pattern === 1) diagnosisCode = "ZZZ999";                   // INVALID_ICD11
  if (pattern === 2) diagnosisCode = "J18.9";                    // INVALID_ICD11 (ICD-10 entered)
  if (pattern === 3) {                                           // VISIT_DATE + SERVICED_PERIOD_IN_BILLABLE
    visitDate = daysFromNow(14);
  }
  if (pattern === 4) coverageEndDate = daysAgo(Math.max(0, visitDaysAgo) + 30); // COVERAGE_EXPIRED
  if (pattern === 5) claimedAmount = calculatedAmount + 1500;    // TOTAL_EQUALS_NET_SUM
  if (pattern === 6) items[0].service_code = "SHA-OPD-001";      // SHA_SERVICE_CODE_FORMAT
  if (pattern === 7) diagnosisCode = "";                         // MISSING_FIELDS
  if (pattern === 8) items[0].service_end = "";                  // SERVICED_PERIOD_PRESENT
  if (pattern === 9) {                                           // ITEM_SEQUENCE_VALID
    items.push({ ...items[0], sequence: 1 });
    claimedAmount += items[0].unit_price;
  }
  if (pattern === 10) fund = "PHC";                              // PHC_ZERO_TOTAL
  if (pattern === 11) {                                          // PREAUTH_REQUIRED + TARIFF_CEILING
    items.splice(0, items.length, {
      sequence: 1,
      service_code: "SHA-16-001",
      description: "Haemodialysis session",
      quantity: 1,
      unit_price: 12000,
      service_start: daysAgo(visitDaysAgo),
      service_end: daysAgo(visitDaysAgo),
    });
    claimedAmount = 12000;
    diagnosisCode = "GB61.5";
    if (Math.floor(index / 24) % 2 === 1) preauthRef = `PA-${pad(index, 5)}`;
  }

  const dobYear = 1970 + (index % 40);

  return {
    id: claimId,
    patient_name: `${first} ${last}`,
    patient_id: patientId,
    dob: `${dobYear}-${pad((index % 12) + 1, 2)}-${pad(
      (index % 27) + 1,
      2
    )}`,
    gender: index % 2 === 0 ? "F" : "M",

    facility_name: facilityName,
    facility_code: facilityCode,

    visit_date: visitDate,

    diagnosis_code: diagnosisCode,
    diagnosis_description: diagnosisCode === "GB61.5" ? "Chronic kidney disease, stage 5" : diagnosis.description,
    department: diagnosis.department ?? (diagnosisCode === "GB61.5" ? "renal" : "outpatient"),
    ...(diagnosis.department === "maternity" ? { partograph_id: `PG-${pad(index + 1, 5)}` } : {}),
    fund,
    ...(preauthRef ? { preauth_ref: preauthRef } : {}),

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
