/* global process, localStorage, URL */
import { chromium } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import path from "node:path";

const outDir = path.resolve(process.argv[2] || "artifacts/ui-declutter/before");
const viewports = [
  { width: 1366, height: 768 },
  { width: 1920, height: 1080 },
  { width: 1024, height: 768 },
];
const departments = ["outpatient", "maternity", "renal", "surgical"];
const claims = Array.from({ length: 50 }, (_, index) => {
  const number = String(index + 1).padStart(6, "0");
  return {
    id: `SYN-CLM-${number}`,
    patient_name: `Sample Patient ${index + 1}`,
    patient_id: `SYN-${number}`,
    facility_name: "Kerugoya Level 5 Hospital",
    department: departments[index % departments.length],
    visit_date: "2026-10-30",
    coverage_end_date: "2027-01-31",
    diagnosis_code: "A09",
    diagnosis_description: "Sample diagnosis for layout review",
    claimed_amount: 8500,
    is_synthetic: true,
    _preview: { score: 100 - (index % 4) * 10, status: "Ready for Submission", color: "green", error_count: 0, warning_count: 0 },
  };
});
const analytics = {
  available: true,
  kpis: { total_claims: 50, ready_percent: 72, rework_rate: 18, ledger_entries: 170 },
  claims_by_status: [
    { status: "Ready for Submission", claim_count: 36 },
    { status: "Needs Review", claim_count: 10 },
    { status: "High Risk — Errors Found", claim_count: 4 },
  ],
  score_by_department: departments.map((department, i) => ({ department, avg_score: 80 + i * 4, claims: 12 })),
  top_failed_rules: [{ rule_id: "AMOUNT_MISMATCH", rule_name: "Amount mismatch", failures: 12 }],
  rework_trend_weekly: [{ week_start: "2026-10-26", rework_rate: 18 }],
  signoff_progress: departments.map((department) => ({ department, pending: 3, signed_off: 9 })),
  ledger_status: { entries: 170, unanchored_entries: 170 },
};

const browser = await chromium.launch({ headless: true });
try {
  await mkdir(outDir, { recursive: true });
  for (const viewport of viewports) {
    const context = await browser.newContext({ viewport, colorScheme: "dark" });
    await context.addInitScript(() => localStorage.setItem("theme", "dark"));
    const page = await context.newPage();
    await page.route("http://localhost:8001/**", async (route) => {
      const url = new URL(route.request().url());
      const pathname = decodeURIComponent(url.pathname);
      if (pathname === "/claims" && route.request().method() === "GET") {
        return route.fulfill({ json: { claims, count: claims.length, total_count: claims.length } });
      }
      if (pathname === "/analytics/overview") return route.fulfill({ json: analytics });
      if (pathname === "/outcomes") return route.fulfill({ json: { outcomes: [] } });
      if (pathname === "/ledger/verify-anchor") return route.fulfill({ json: { status: "not_anchored", anchors: [] } });
      if (pathname.endsWith("/audit")) {
        return route.fulfill({ json: { history: [{ seq: 1, type: "claim_received", hash: "a".repeat(64), prev_hash: "0000000000000000", timestamp: "2026-11-05T10:00:00Z", version: 1 }], current_version: { status: "matches", version: 1, event_seq: 1 } } });
      }
      if (/^\/claims\/[^/]+\/department-review$/.test(pathname) && route.request().method() === "GET") {
        return route.fulfill({ json: { review: { completed: {}, evidence: {}, signedOffAt: null, reviewer: "", note: "" } } });
      }
      if (/^\/claims\/[^/]+$/.test(pathname) && route.request().method() === "GET") {
        const claim = claims.find((item) => item.id === pathname.split("/").at(-1));
        return route.fulfill({ json: claim || claims[0] });
      }
      return route.fulfill({ json: { recorded: true, review: null } });
    });

    await page.goto("http://127.0.0.1:5173", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(500);
    await page.getByRole("button", { name: "Open Claims Workspace", exact: true }).click();
    await page.waitForTimeout(250);
    await page.screenshot({ path: path.join(outDir, `claims-${viewport.width}x${viewport.height}.png`) });
    await page.screenshot({ path: path.join(outDir, `checks-${viewport.width}x${viewport.height}.png`) });
    await page.getByRole("button", { name: "Audit", exact: true }).click();
    await page.waitForTimeout(250);
    await page.screenshot({ path: path.join(outDir, `audit-${viewport.width}x${viewport.height}.png`) });
    await page.getByRole("button", { name: "Departments", exact: true }).click();
    await page.waitForTimeout(250);
    await page.screenshot({ path: path.join(outDir, `departments-${viewport.width}x${viewport.height}.png`) });
    await page.getByRole("button", { name: "Management Overview" }).click();
    await page.waitForTimeout(300);
    await page.screenshot({ path: path.join(outDir, `overview-${viewport.width}x${viewport.height}.png`) });
    await context.close();
  }
} finally {
  await browser.close();
}
