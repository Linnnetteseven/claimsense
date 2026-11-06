import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mkdir } from "node:fs/promises";
import process from "node:process";
import path from "node:path";

const departments = ["outpatient", "maternity", "renal", "surgical"];
const claims = Array.from({ length: 50 }, (_, index) => {
  const number = String(index + 1).padStart(6, "0");
  return {
    id: `SYN-CLM-${number}`,
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
const outpatientClaimCount = claims.filter((claim) => claim.department === "outpatient").length;

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

test("capture review screenshots for the queue, work tabs, and overview at supported widths", async ({ page }) => {
  await mockApi(page);
  await enterWorkspace(page);
  const screenshotDir = path.resolve(process.cwd(), "screenshots", "review");
  await mkdir(screenshotDir, { recursive: true });

  for (const viewport of [
    { width: 1366, height: 768 },
    { width: 1920, height: 1080 },
    { width: 1024, height: 768 },
  ]) {
    await page.setViewportSize(viewport);
    const prefix = `${viewport.width}x${viewport.height}`;
    const save = (name) => page.screenshot({ path: path.join(screenshotDir, `${prefix}-${name}.png`), fullPage: false });
    await save("claim-list");
    for (const [section, filename] of [
      ["Checks", "claim-checks"],
      ["Audit", "audit-trail"],
      ["Departments", "department-workspace"],
    ]) {
      await page.getByRole("navigation", { name: "Claim sections" }).getByRole("button", { name: section, exact: true }).click();
      await page.waitForTimeout(100);
      await save(filename);
    }
    await page.getByRole("button", { name: "Management Overview", exact: true }).click();
    await page.waitForTimeout(100);
    await save("management-overview");
    await page.reload();
    await enterWorkspace(page);
  }
});

test("workspace satisfies automated WCAG 2.1 AA checks on key light and dark views", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light" });
  await mockApi(page);
  await enterWorkspace(page);
  const { violations: checksViolations } = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  expect(checksViolations.map(({ id, help, nodes }) => ({ id, help, affected: nodes.map((node) => node.target) })), "Axe WCAG violations in Checks").toEqual([]);
  await page.getByRole("button", { name: "Audit", exact: true }).click();
  const { violations: auditViolations } = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  expect(auditViolations.map(({ id, help, nodes }) => ({ id, help, affected: nodes.map((node) => node.target) })), "Axe WCAG violations in Audit").toEqual([]);
  await page.getByRole("button", { name: "Management Overview", exact: true }).click();
  const { violations } = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  expect(violations.map(({ id, help, nodes }) => ({ id, help, affected: nodes.map((node) => node.target) }))).toEqual([]);

  await page.reload();
  await enterWorkspace(page);
  await page.getByRole("button", { name: "Toggle theme" }).click();
  const darkAudit = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  expect(darkAudit.violations.map(({ id, help, nodes }) => ({ id, help, affected: nodes.map((node) => node.target) })), "Axe WCAG violations in dark Checks").toEqual([]);
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
  await expect(page.locator("aside[aria-label='Claims queue'] ul li")).toHaveCount(outpatientClaimCount);

  online = false;
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Database slow / unreachable");
  await expect(page.getByRole("alert")).toContainText("Offline: showing data saved at");
  expect(await page.locator("aside[aria-label='Claims queue'] ul li").count()).toBe(outpatientClaimCount);

  online = true;
  await page.clock.fastForward(15_000);
  await expect(page.getByRole("alert")).toHaveCount(0);
  await expect(page.locator("aside[aria-label='Claims queue'] ul li")).toHaveCount(outpatientClaimCount);
  expect(requests).toBeGreaterThanOrEqual(3);
});

test("submitted claim stays locked, supports read-only recheck, and opens a correction version", async ({ page }) => {
  const lifecycleClaim = {
    ...claims[0], department: "outpatient",
    _lifecycle: { status: "needs_revalidation", version: 1, version_fingerprint: "a".repeat(64) },
  };
  let lifecycle = lifecycleClaim._lifecycle;
  await page.route("http://localhost:8001/**", async (route) => {
    const url = new URL(route.request().url());
    const pathname = decodeURIComponent(url.pathname);
    const method = route.request().method();
    if (pathname === "/settings/ui") return route.fulfill({ json: { departments_enabled: false } });
    if (pathname === "/claims" && method === "GET") return route.fulfill({ json: { claims: [{ ...lifecycleClaim, _lifecycle: lifecycle }], count: 1 } });
    if (pathname === `/claims/${lifecycleClaim.id}` && method === "GET") return route.fulfill({ json: { ...lifecycleClaim, _lifecycle: lifecycle } });
    if (pathname.endsWith("/validate")) {
      lifecycle = { status: "ready", version: 2, version_fingerprint: "b".repeat(64) };
      return route.fulfill({ json: { score: 100, status: "Ready for Submission", error_count: 0, warning_count: 0, results: [], explanations: {}, lifecycle, version: 2, version_fingerprint: lifecycle.version_fingerprint } });
    }
    if (pathname.endsWith("/submit")) {
      lifecycle = { ...lifecycle, status: "submitted" };
      return route.fulfill({ json: { submitted: true, mode: "mock", score: 100, version: 2, version_fingerprint: lifecycle.version_fingerprint, lifecycle } });
    }
    if (pathname.endsWith("/recheck")) return route.fulfill({ json: { validation: { informational: true, version: 2, status: "Ready for Submission", score: 100 }, lifecycle } });
    if (pathname.endsWith("/correction")) {
      lifecycle = { status: "needs_revalidation", version: 3, version_fingerprint: "b".repeat(64) };
      return route.fulfill({ json: { lifecycle, correction: { ...lifecycle, claim: lifecycleClaim } } });
    }
    if (pathname.endsWith("/department-review")) return route.fulfill({ json: { review: null } });
    if (pathname === "/outcomes") return route.fulfill({ json: { outcomes: [] } });
    if (pathname.endsWith("/audit")) return route.fulfill({ json: { history: [], current_version: { status: "matches" } } });
    return route.fulfill({ json: { recorded: true, review: null } });
  });

  await enterWorkspace(page);
  const sampleRow = page.locator("aside[aria-label='Claims queue'] ul li button").filter({ hasText: "SYN-CLM-000001" }).first();
  await expect(sampleRow).toBeVisible();
  await sampleRow.click();
  await page.getByRole("button", { name: "Re-run checks" }).click();
  await expect(page.getByRole("button", { name: "Submit claim →" })).toBeEnabled();
  await page.getByRole("button", { name: "Submit claim →" }).click();
  await expect(page.getByRole("heading", { name: "Submitted, locked" })).toBeVisible();
  await expect(page.getByText("b".repeat(64))).toBeVisible();
  await page.getByRole("button", { name: "Re-check against current rules (read-only)" }).click();
  await expect(page.getByText(/Informational result for submitted version 2/)).toBeVisible();
  await page.getByLabel(/Correction reason/).fill("Fix a coding detail");
  await page.getByRole("button", { name: "Create correction version" }).click();
  await expect(page.getByRole("button", { name: "Re-run checks" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Makena Wanjala Nyongesa", exact: true })).toBeVisible();
});
