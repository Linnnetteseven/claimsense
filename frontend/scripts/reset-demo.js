import { createClient } from "@supabase/supabase-js";
import { resolvedDemoClaims } from "./demo-data.js";

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

const claims = resolvedDemoClaims();

const claimNumbers = claims.map((claim) => claim.id);

console.log(`Resetting ${claimNumbers.length} canonical demo claims...`);

const { error: deleteError } = await supabase
  .from("claims")
  .delete()
  .in("claim_number", claimNumbers);

if (deleteError) {
  console.error(`Demo reset failed: ${deleteError.message}`);
  process.exit(1);
}

const rows = claims.map((claim) => ({
  claim_number: claim.id,
  status: "draft",
  claim_data: claim,
}));

const { error: seedError } = await supabase
  .from("claims")
  .upsert(rows, {
    onConflict: "claim_number",
  });

if (seedError) {
  console.error(`Demo reseed failed: ${seedError.message}`);
  process.exit(1);
}

console.log(
  `Demo reset complete. Restored ${rows.length} canonical seeded claims.`
);
