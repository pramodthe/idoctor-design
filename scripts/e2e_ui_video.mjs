#!/usr/bin/env node
/**
 * Record a headed-quality e2e video of the iDoctor Design UI.
 * Requires frontend :3000 and API :8080.
 *
 *   node scripts/e2e_ui_video.mjs
 */
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const OUT = path.join(ROOT, "output", "playwright");
const URL = process.env.E2E_URL || "http://127.0.0.1:3000/";

fs.mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  recordVideo: { dir: OUT, size: { width: 1440, height: 900 } },
});
const page = await context.newPage();

function log(msg) {
  console.log(`[e2e] ${msg}`);
}

try {
  log(`open ${URL}`);
  await page.goto(URL, { waitUntil: "domcontentloaded", timeout: 30_000 });
  await page.waitForTimeout(1200);

  const openLab = page.getByRole("button", { name: "Open lab" });
  if (await openLab.isVisible().catch(() => false)) {
    await openLab.click();
    await page.waitForTimeout(600);
  }

  await page.getByRole("heading", { name: "iDoctor Design" }).first().waitFor({
    timeout: 15_000,
  });
  log("landing");
  await page.screenshot({ path: path.join(OUT, "01-landing.png"), fullPage: false });
  await page.waitForTimeout(800);

  const graph = page.getByText("The seven graph nodes");
  if (await graph.isVisible().catch(() => false)) {
    await graph.scrollIntoViewIfNeeded();
    await page.waitForTimeout(500);
  }

  const firstRow = page.locator("button, [role='button']").filter({
    hasText: /Literature|evidence/i,
  }).first();
  if (await firstRow.count()) {
    await firstRow.click({ timeout: 3000 }).catch(() => {});
    await page.waitForTimeout(700);
  }
  await page.screenshot({ path: path.join(OUT, "02-agents.png"), fullPage: false });

  log("run fixture");
  await page.getByRole("button", { name: "Run fixture" }).click();
  await page.getByText("Agents at work").waitFor({ timeout: 20_000 });
  await page.waitForTimeout(1500);
  await page.screenshot({ path: path.join(OUT, "03-running.png"), fullPage: false });

  await page.getByRole("heading", { name: "Trust results" }).waitFor({
    timeout: 120_000,
  });
  log("completed");
  await page.waitForTimeout(1200);
  await page.screenshot({ path: path.join(OUT, "04-results.png"), fullPage: false });

  const critic = page.getByText(/Scientist critic|critic/i).first();
  if (await critic.isVisible().catch(() => false)) {
    await critic.click().catch(() => {});
    await page.waitForTimeout(800);
  }

  await page.mouse.wheel(0, 700);
  await page.waitForTimeout(1000);
  await page.screenshot({ path: path.join(OUT, "05-scroll.png"), fullPage: false });
  await page.mouse.wheel(0, 900);
  await page.waitForTimeout(1200);
  await page.screenshot({ path: path.join(OUT, "06-designs.png"), fullPage: false });

  const body = await page.locator("body").innerText();
  const checks = {
    demoBanner: /Demo data/i.test(body),
    trustResults: /Trust results/i.test(body),
    claudeZero: /Claude × 0|called Claude 0 times/i.test(body),
    labLog: /lab log|Paperclip|evidence/i.test(body),
  };
  fs.writeFileSync(path.join(OUT, "checks.json"), JSON.stringify(checks, null, 2));
  log(`checks ${JSON.stringify(checks)}`);
  if (!checks.trustResults) throw new Error("did not reach Trust results");
} finally {
  const video = page.video();
  await context.close();
  await browser.close();
  if (video) {
    const raw = await video.path();
    const dest = path.join(OUT, "e2e-fixture.webm");
    fs.renameSync(raw, dest);
    log(`video ${dest}`);
  }
}
