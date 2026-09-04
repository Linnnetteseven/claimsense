import { createClient } from "@supabase/supabase-js";

const url = process.env.SUPABASE_URL;
const serviceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY;

if (!url || !serviceRoleKey) {
  console.error(
    "Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY."
  );
  process.exit(1);
}

const supabase = createClient(url, serviceRoleKey, {
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

const diagnoses = [
  {
    code: "A09",
    description: "Diarrhoea and gastroenteritis of infectious origin",
    amount: 3500,
  },
  {
    code: "J18.9",
    description: "Pneumonia, unspecified organism",
    amount: 6750,
  },
  {
    code: "O80",
    description: "Encounter for full-term uncomplicated delivery",
    amount: 16400,
  },
  {
    code: "I10",
    description: "Essential primary hypertension",
    amount: 4200,
  },
  {
    code: "E11.9",
    description: "Type 2 diabetes mellitus without complications",
    amount: 4800,
  },
  {
    code: "K30",
    description: "Functional dyspepsia",
    amount: 3000,
  },
  {
    code: "N39.0",
    description: "Urinary tract infection, site not specified",
    amount: 3900,
  },
];

const services = [
  {
    service_code: "SHA-OPD-001",
    description: "Outpatient consultation",
    unit_price: 1200,
  },
  {
    service_code: "SHA-LAB-001",
    description: "Laboratory investigation",
    unit_price: 850,
  },
  {
    service_code: "SHA-MED-001",
    description: "Prescribed medication",
    unit_price: 1500,
  },
  {
    service_code: "SHA-RAD-001",
    description: "Diagnostic imaging",
    unit_price: 2200,
  },
];

function pad(value, length = 3) {
  return String(value).padStart(length, "0");
}

function isoDate(date) {
  return date.toISOString().slice(0, 10);
}

function daysAgo(days) {
  const date = new Date();
  date.setDate(date.getDate() - days);
  return isoDate(date);
}

function daysFromNow(days) {
  const date = new Date();
  date.setDate(date.getDate() + days);
  return isoDate(date);
}

function makeItems(diagnosis, index) {
  const itemCount = 1 + (index % 3);

  return Array.from({ length: itemCount }, (_, itemIndex) => {
    const service = services[(index + itemIndex) % services.length];

    return {
      service_code: service.service_code,
      description: service.description,
      quantity: 1,
      unit_price: service.unit_price,
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

  const items = makeItems(diagnosis, index);

  const calculatedAmount = items.reduce(
    (sum, item) =>
      sum +
      Number(item.unit_price) *
        Number(item.quantity),
    0
  );

  let visitDate = daysAgo(index % 180);
  let coverageEndDate = daysFromNow(30 + (index % 365));

  let diagnosisCode = diagnosis.code;
  let claimedAmount = calculatedAmount;

  // Deliberately create a realistic mixture of clean,
  // warning and error claims for the demo.

  const pattern = index % 10;

  if (pattern === 1) {
    diagnosisCode = "ZZZ999";
  }

  if (pattern === 2) {
    visitDate = daysFromNow(30);
  }

  if (pattern === 3) {
    coverageEndDate = daysAgo(60);
  }

  if (pattern === 4) {
    claimedAmount = calculatedAmount + 1500;
  }

  if (pattern === 5) {
    items[0].service_code = "";
  }

  if (pattern === 6) {
    claimedAmount = 15000;
  }

  if (pattern === 7) {
    diagnosisCode = "";
  }

  if (pattern === 8) {
    visitDate = daysFromNow(14);
    coverageEndDate = daysAgo(30);
  }

  if (pattern === 9) {
    claimedAmount = Math.round(calculatedAmount * 1.08);
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
    diagnosis_description: diagnosis.description,

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

const rows = claims.map((claim) => ({
  claim_number: claim.id,
  status: "draft",
  claim_data: claim,
}));

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
