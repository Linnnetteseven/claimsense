import assert from "node:assert/strict";
import { displayPatientName, syntheticDisplayName } from "./syntheticName.js";

assert.equal(syntheticDisplayName("SYN-000001"), "Makena Wanjala Nyongesa");
assert.equal(syntheticDisplayName("invalid"), null);
assert.equal(displayPatientName({ is_synthetic: true, patient_id: "SYN-000001", patient_name: "Ignored name" }), "Makena Wanjala Nyongesa");
assert.equal(displayPatientName({ patient_name: "Grace Example" }), "Grace Example");
assert.equal(new Set(Array.from({ length: 250 }, (_, index) => syntheticDisplayName(`SYN-${String(index + 1).padStart(6, "0")}`))).size, 250);
