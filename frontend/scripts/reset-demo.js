import { createClient } from "@supabase/supabase-js";
import { demoClaimNumbers } from "./demo-data.js";

const url = process.env.SUPABASE_URL;
const serviceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY;

if (!url || !serviceRoleKey) {
  console.error("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required.");
  process.exit(1);
}

const supabase = createClient(url, serviceRoleKey, {
  auth: { autoRefreshToken: false, persistSession: false },
});
const { error } = await supabase
  .from("claims")
  .delete()
  .in("claim_number", demoClaimNumbers());

if (error) {
  console.error(`Demo reset failed: ${error.message}`);
  process.exit(1);
}

await import("./seed-demo.js");
