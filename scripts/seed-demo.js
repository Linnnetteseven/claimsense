import { createClient } from "@supabase/supabase-js";
import { demoSeedRows } from "./demo-data.js";

const url = process.env.SUPABASE_URL;
const serviceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY;

if (!url || !serviceRoleKey) {
  console.error("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required.");
  process.exit(1);
}

const supabase = createClient(url, serviceRoleKey, {
  auth: { autoRefreshToken: false, persistSession: false },
});
const rows = demoSeedRows();

const { error } = await supabase
  .from("claims")
  .upsert(rows, { onConflict: "claim_number" });

if (error) {
  console.error(`Demo seed failed: ${error.message}`);
  process.exit(1);
}

console.log(`Seeded ${rows.length} canonical demo claims.`);
