// User flows through the real UI, against a private backend in sample mode (see playwright.config.ts).
// No AI model runs here, so answers come from FinSight's own code and are the same on every run.
import { expect, test, type Page } from "@playwright/test";

const nav = (page: Page, name: string) =>
  page.getByRole("navigation").getByRole("button", { name, exact: true }).first().click(); // "Main" and "More" groups
const rail = (page: Page) => page.locator('aside[aria-label="Calendar and insights"]');

/** Investigate -> pick Northwind Motors -> ask -> wait for the finished investigation. */
async function askNorthwind(page: Page, question: string) {
  await page.goto("/");
  await nav(page, "Investigate");
  const ask = page.getByRole("region", { name: "Ask about a company" });
  await ask.getByRole("button", { name: /Northwind Motors/ }).click();
  await expect(ask.getByRole("heading", { name: "Ask about Northwind Motors" })).toBeVisible();
  await ask.getByLabel("Your question").fill(question);
  await ask.getByRole("button", { name: "Ask", exact: true }).click();
  await expect(page.getByText("Completed: Investigation finished.")).toBeVisible({ timeout: 45_000 });
}

test.describe.serial("FinSight AI", () => {
  test("home loads with the right rail and live service status", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toContainText(/Good (morning|afternoon|evening)/);
    await expect(rail(page)).toBeVisible();
    await expect(page.getByText("No company yet")).toBeVisible(); // fresh database: nothing invented
    await expect(page.getByText("No events yet.")).toBeVisible();
  });

  test("ask your own question about a sample company and get a direct answer", async ({ page }) => {
    await askNorthwind(page, "Is Northwind Motors' revenue still growing?");
    await expect(page.getByRole("heading", { name: "Northwind Motors", exact: true }).first()).toBeVisible();
    await expect(page.getByText(/Sample data \(fictional\)/).first()).toBeVisible();
    await expect(page.getByText("Your answer")).toBeVisible();
    // No model in this run: the answer is computed from the verified filings, and says so.
    await expect(page.getByText(/^(Yes|No): revenue (rose|fell) in the latest fiscal year/)).toBeVisible();
    await expect(page.getByText(/Answer computed by FinSight from the verified filings/)).toBeVisible();
    await expect(rail(page)).toHaveCount(0); // the rail is for Home only
  });

  test("every investigation tab renders, with charts where expected", async ({ page }) => {
    await askNorthwind(page, "Is Northwind Motors' profit backed by real cash?");
    for (const [tab, expectChart] of [["Financials", true], ["Risks", true], ["Sources", false], ["Stress-test", true], ["Notes & tripwires", false]] as const) {
      await page.getByRole("tab", { name: tab }).click();
      await expect(page.getByRole("tab", { name: tab })).toHaveAttribute("aria-selected", "true");
      if (expectChart) await expect(page.locator("main [_echarts_instance_] svg").first()).toBeVisible();
    }
    await page.getByRole("tab", { name: "Overview" }).click();
    await expect(page.getByRole("region", { name: "Ask about a company" })).toContainText("Ask another question about Northwind Motors");
  });

  test("a wrong claim in the question is checked against the filing", async ({ page }) => {
    await page.goto("/");
    await nav(page, "Investigate");
    await page.getByRole("button", { name: "Was Northwind Motors' 2024 revenue really $13.6 billion?" }).click();
    await expect(page.getByText("Completed: Investigation finished.")).toBeVisible({ timeout: 45_000 });
    await expect(page.getByText(/^Your claim is contradicted/)).toBeVisible();
  });

  test("glossary pop-ups explain financial terms", async ({ page }) => {
    await page.goto("/");
    const term = page.locator("main span[role=button].cursor-help", { hasText: "Operating Cash Flow" }).first();
    await term.hover();
    const tip = page.getByRole("tooltip");
    await expect(tip).toBeVisible();
    await expect(tip).toContainText("Operating cash flow");
    // It opens right under the word (checks the page-zoom maths).
    const [t, b] = [await term.boundingBox(), await tip.boundingBox()];
    expect(Math.abs(b!.y - (t!.y + t!.height))).toBeLessThan(20);
  });

  test("home dashboard shows the latest finished investigation", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Northwind Motors", exact: true }).first()).toBeVisible();
    await expect(page.getByText(/Revenue \(FY\d{4}\)/)).toBeVisible();
    await expect(page.getByText("Recent investigations")).toBeVisible();
    await page.getByRole("button", { name: /View Full Analysis/ }).click();
    await expect(page.getByRole("tab", { name: "Overview" })).toBeVisible();
  });

  test("compare two companies brand-blind, then reveal", async ({ page }) => {
    await page.goto("/");
    await nav(page, "Compare");
    const build = page.getByRole("button", { name: "Build the blind board" });
    await expect(build).toBeDisabled(); // needs at least two companies
    await page.getByRole("button", { name: /\+ Northwind Motors/ }).click();
    await expect(build).toBeDisabled();
    await page.getByRole("button", { name: /\+ Contoso Retail/ }).click();
    await build.click();
    await expect(page.locator("main table th", { hasText: "Company A" })).toBeVisible();
    await expect(page.locator("main table th", { hasText: "Company B" })).toBeVisible();
    await expect(page.locator("main table")).not.toContainText("Northwind"); // names stay hidden
    await page.getByRole("button", { name: "Company A", exact: true }).click();
    await page.getByRole("button", { name: "Reveal the names" }).click(); // only offered once a choice is made
    await expect(page.getByText(/On the evidence alone you chose A, which is (Northwind Motors|Contoso Retail)/)).toBeVisible();
  });

  test("check a post: numbers are verified against filings", async ({ page }) => {
    await page.goto("/");
    await nav(page, "Investigate");
    await page.getByRole("tab", { name: "Check a post" }).click();
    await page.getByRole("button", { name: "Sample post (fictional company)" }).click();
    await page.getByRole("button", { name: "Check claims" }).click();
    await expect(page.getByText(/\d+ claim\(s\) checked/)).toBeVisible();
    await expect(page.getByText("Contradicted").first()).toBeVisible();
  });

  test("savings and fees simulator calculates", async ({ page }) => {
    await page.goto("/");
    await nav(page, "Investigate");
    await page.getByRole("tab", { name: "Savings & fees" }).click();
    await expect(page.locator("main table th", { hasText: "Lost to fees" })).toBeVisible();
    await expect(page.locator("main table tbody tr").first()).toContainText("$");
  });

  test("watchlist: follow, publish a fictional amendment, detect the change", async ({ page }) => {
    await page.goto("/");
    await nav(page, "Watchlist");
    await page.getByRole("combobox").filter({ hasText: "Choose a sample company" }).selectOption("NWM");
    await page.getByRole("button", { name: "Follow", exact: true }).click();
    await expect(page.getByText("Started watching.")).toBeVisible();
    await page.getByRole("button", { name: "Publish fictional amended filing" }).click();
    await page.getByRole("button", { name: "Check now" }).first().click();
    await expect(page.getByText("Changed").first()).toBeVisible();
    await expect(page.getByText(/\$52\.40B → \$51\.90B/)).toBeVisible();
  });

  test("record a decision with tripwires in the diary", async ({ page }) => {
    await askNorthwind(page, "Is Northwind Motors' debt rising?");
    await page.getByRole("tab", { name: "Notes & tripwires" }).click();
    await expect(page.getByText(/now: /).first()).toBeVisible(); // tripwires show the current figure
    await page.getByLabel("I'll wait").check();
    await page.getByPlaceholder(/Profit looks good/).fill("E2E test: waiting for two more quarters.");
    await page.getByRole("button", { name: "Save to my decision diary" }).click();
    await expect(page.getByText("Decision recorded")).toBeVisible();
    await nav(page, "Decision Diary");
    await expect(page.getByText("E2E test: waiting for two more quarters.").first()).toBeVisible();
  });

  test("pre-mortem runs without a model and cites findings", async ({ page }) => {
    await page.goto("/");
    await nav(page, "Pre-Mortem");
    await page.getByRole("button", { name: /Is Northwind Motors' debt rising\?/ }).click(); // pick an investigation
    await page.getByRole("button", { name: "Run the pre-mortem" }).click();
    await expect(page.getByText("Assembled without a model")).toBeVisible();
    await expect(page.getByText(/The Skeptic/)).toBeVisible();
  });

  test("data sources page reports each service honestly", async ({ page }) => {
    await page.goto("/");
    await nav(page, "Data Sources");
    await expect(page.getByText("Meterless H-MEM").first()).toBeVisible();
    await expect(page.locator("main")).toContainText("online");
  });

  test("phone layout has no sideways scrolling", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    const [sw, cw] = await page.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]);
    expect(sw).toBeLessThanOrEqual(cw);
  });
});
