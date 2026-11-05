import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

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
    _preview: { score: 100, status: "Ready for Submission", color: "green", error_count: 0, warning_count: 0 },
  };
});

const analytics = {
  available: true,
  kpis: { total_claims: 50, ready_percent: 72, rework_rate: 18, ledger_entries: 170 },
  claims_by_status: [{ status: "Ready for Submission", claim_count: 36 }, { status: "Needs Review", claim_count: 10 }],
  score_by_department: departments.map((department) => ({ department, avg_score: 88, claims: 12 })),
  top_failed_rules: [], rework_trend_weekly: [],
  signoff_progress: departments.map((department) => ({ department, pending: 3, signed_off: 9 })),
  ledger_status: { entries: 170, unanchored_entries: 170 },
};

async function mockApi(page, claimsResponder = async (route) => route.fulfill({ json: { claims, count: 50 } })) {
  await page.route("http://localhost:8001/**", async (route) => {
    const url = new URL(route.request().url());
    const pathname = decodeURIComponent(url.pathname);
    if (pathname === "/claims" && route.request().method() === "GET") return claimsResponder(route);
    if (pathname === "/analytics/overview") return route.fulfill({ json: analytics });
    if (pathname === "/outcomes") return route.fulfill({ json: { outcomes: [] } });
    if (pathname === "/ledger/verify-anchor") return route.fulfill({ json: { status: "not_anchored", anchors: [] } });
    if (pathname.endsWith("/audit")) return route.fulfill({ json: { history: [{ seq: 1, type: "claim_received", hash: "a".repeat(64), prev_hash: "0000000000000000", timestamp: "2026-11-05T10:00:00Z", version: 1 }], current_version: { status: "matches", version: 1, event_seq: 1 } } });
    if (/^\/claims\/[^/]+\/department-review$/.test(pathname) && route.request().method() === "GET") return route.fulfill({ json: { review: { completed: {}, evidence: {}, signedOffAt: null, reviewer: "", note: "" } } });
    if (/^\/claims\/[^/]+$/.test(pathname) && route.request().method() === "GET") return route.fulfill({ json: claims.find((claim) => claim.id === pathname.split("/").at(-1)) || claims[0] });
    return route.fulfill({ json: { recorded: true, review: null } });
  });
}

async function enterWorkspace(page) {
  await page.goto("/");
  await page.getByRole("button", { name: "Open Claims Workspace", exact: true }).click();
}

test("compact queue shows at least eight rows and keeps five sections reachable", async ({ page }) => {
  await page.setViewportSize({ width: 1366, height: 768 });
  await mockApi(page);
  await enterWorkspace(page);
  const visibleRows = await page.locator("aside[aria-label='Claims queue'] ul li button").evaluateAll((buttons) => {
    const height = window.innerHeight;
    return buttons.filter((button) => {
      const rect = button.getBoundingClientRect();
      return rect.top >= 0 && rect.bottom <= height;
    }).length;
  });
  expect(visibleRows).toBeGreaterThanOrEqual(8);
  await expect(page.getByRole("navigation", { name: "Claim sections" }).getByRole("button")).toHaveCount(5);
  await expect(page.getByRole("button", { name: "Add claim" })).toBeVisible();
  await page.getByRole("button", { name: "Details", exact: true }).click();
  await expect(page.getByText(/Technical details/)).toBeVisible();
});

test("workspace fits the supported desktop and tablet widths without horizontal page overflow", async ({ page }) => {
  await mockApi(page);
  await enterWorkspace(page);
  for (const viewport of [
    { width: 1024, height: 768 },
    { width: 1366, height: 768 },
    { width: 1920, height: 1080 },
  ]) {
    await page.setViewportSize(viewport);
    const dimensions = await page.evaluate(() => ({
      viewport: document.documentElement.clientWidth,
      page: document.documentElement.scrollWidth,
    }));
    expect(dimensions.page, `horizontal overflow at ${viewport.width}px`).toBeLessThanOrEqual(dimensions.viewport);
  }
});

test("workspace satisfies automated WCAG 2.1 AA checks in light mode", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light" });
  await mockApi(page);
  await enterWorkspace(page);
  const sections = ["Checks", "Details", "Departments", "Audit", "Outcome"];
  for (const section of sections) {
    if (section !== "Checks") await page.getByRole("button", { name: section, exact: true }).click();
    const { violations } = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
    expect(violations.map(({ id, help, nodes }) => ({ id, help, affected: nodes.map((node) => node.target) })), `Axe WCAG violations in ${section}`).toEqual([]);
  }
  await page.getByRole("button", { name: "Management Overview", exact: true }).click();
  const { violations } = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  expect(violations.map(({ id, help, nodes }) => ({ id, help, affected: nodes.map((node) => node.target) }))).toEqual([]);

  await page.getByRole("button", { name: "Claims", exact: true }).click();
  await page.getByRole("button", { name: "Toggle theme" }).click();
  for (const section of sections) {
    if (section !== "Checks") await page.getByRole("button", { name: section, exact: true }).click();
    const darkAudit = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
    expect(darkAudit.violations.map(({ id, help, nodes }) => ({ id, help, affected: nodes.map((node) => node.target) })), `Axe WCAG violations in dark ${section}`).toEqual([]);
  }
});

test("claims queue recovers automatically after the backend returns without reloading", async ({ page }) => {
  let online = true;
  let requests = 0;
  await page.clock.install();
  await mockApi(page, async (route) => {
    requests += 1;
    if (!online) return route.fulfill({ status: 503, json: { detail: "Oracle unavailable" } });
    return route.fulfill({ json: { claims, count: claims.length } });
  });
  await enterWorkspace(page);
  await expect(page.locator("aside[aria-label='Claims queue'] ul li")).toHaveCount(50);

  online = false;
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Database slow / unreachable");
  await expect(page.getByRole("alert")).toContainText("Offline: showing data saved at");
  expect(await page.locator("aside[aria-label='Claims queue'] ul li").count()).toBe(50);

  online = true;
  await page.clock.fastForward(15_000);
  await expect(page.getByRole("alert")).toHaveCount(0);
  await expect(page.locator("aside[aria-label='Claims queue'] ul li")).toHaveCount(50);
  expect(requests).toBeGreaterThanOrEqual(3);
});
