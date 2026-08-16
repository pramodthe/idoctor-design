#!/usr/bin/env node
/**
 * Record a headed-quality e2e video of the iDoctor Design Trust UI.
 * Requires frontend :3000 and API :8080.
 *
 *   node scripts/e2e_ui_video.mjs
 *
 * Env:
 *   E2E_URL                 default http://127.0.0.1:3000/
 *   E2E_MODE                live | fixture | tour  (default live)
 *   E2E_LIVE_TIMEOUT_MS     wait for live completion (default 1500000 = 25 min)
 */
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const OUT = path.join(ROOT, "output", "playwright");
const URL = process.env.E2E_URL || "http://127.0.0.1:3000/";
const MODE = (process.env.E2E_MODE || "live").toLowerCase();
const LIVE_TIMEOUT_MS = Number(process.env.E2E_LIVE_TIMEOUT_MS || 1_500_000);

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

async function clickIfVisible(locator, timeout = 3000) {
  try {
    if (await locator.isVisible({ timeout: 800 })) {
      await locator.click({ timeout });
      return true;
    }
  } catch {
    /* ignore */
  }
  return false;
}

try {
  log(`open ${URL} mode=${MODE}`);
  await page.goto(URL, { waitUntil: "domcontentloaded", timeout: 30_000 });
  await page.waitForTimeout(1200);

  for (const name of ["Open console", "Open lab"]) {
    if (await clickIfVisible(page.getByRole("button", { name }))) {
      log(`dismissed ${name}`);
      await page.waitForTimeout(600);
      break;
    }
  }

  await page.getByRole("heading", { name: "iDoctor Design" }).first().waitFor({
    timeout: 15_000,
  });
  log("landing");
  await page.screenshot({ path: path.join(OUT, "01-landing.png"), fullPage: false });
  await page.waitForTimeout(800);

  const workflow = page.getByRole("heading", { name: "Autonomous scientist workflow" });
  if (await workflow.isVisible().catch(() => false)) {
    await workflow.scrollIntoViewIfNeeded();
    await page.waitForTimeout(500);
  }

  const firstNode = page.getByText(/Literature|Paperclip|evidence/i).first();
  if (await firstNode.count()) {
    await firstNode.click({ timeout: 3000 }).catch(() => {});
    await page.waitForTimeout(700);
  }
  await page.screenshot({ path: path.join(OUT, "02-agents.png"), fullPage: false });

  async function waitForPipeline(timeoutMs) {
    await page.getByText(/Designing \(\d+\/9\)/).first().waitFor({ timeout: 20_000 });
    await page.waitForTimeout(1500);
    await page.screenshot({ path: path.join(OUT, "03-running.png"), fullPage: false });
    await page.getByRole("button", { name: "Run New Live Campaign" }).waitFor({
      timeout: timeoutMs,
    });
    await page.getByText("No candidate loaded").waitFor({ state: "hidden", timeout: 15_000 }).catch(() => {});
  }

  if (MODE === "live") {
    log("run live scientist");
    await page
      .locator("header")
      .getByRole("button", { name: /Run Live Scientist|Run New Live Campaign/ })
      .click();
    await waitForPipeline(LIVE_TIMEOUT_MS);
    log("live completed");
  } else if (MODE === "fixture") {
    log("run demo fixture");
    await page.getByRole("button", { name: "Load Data" }).click();
    await page.getByRole("button", { name: "Open Demo Fixture" }).click();
    await waitForPipeline(120_000);
    log("fixture completed");
  } else {
    log("tour existing run (no new pipeline)");
    await page.screenshot({ path: path.join(OUT, "03-running.png"), fullPage: false });
  }

  await page.waitForTimeout(1200);
  await page.screenshot({ path: path.join(OUT, "04-results.png"), fullPage: false });

  const critic = page.getByText(/Scientist critic|adversarial reject/i).first();
  if (await critic.isVisible().catch(() => false)) {
    await critic.click().catch(() => {});
    await page.waitForTimeout(800);
  }

  const candidate = page.getByRole("heading", { name: "Candidate decision" });
  if (await candidate.isVisible().catch(() => false)) {
    await candidate.scrollIntoViewIfNeeded();
    await page.waitForTimeout(800);
  }

  await page.mouse.wheel(0, 700);
  await page.waitForTimeout(1000);
  await page.screenshot({ path: path.join(OUT, "05-scroll.png"), fullPage: false });

  const experiment = page.getByRole("heading", { name: "Experiment handoff" });
  if (await experiment.isVisible().catch(() => false)) {
    await experiment.scrollIntoViewIfNeeded();
    await page.waitForTimeout(1000);
  }
  await page.mouse.wheel(0, 900);
  await page.waitForTimeout(1200);
  await page.screenshot({ path: path.join(OUT, "06-designs.png"), fullPage: false });

  const body = await page.locator("body").innerText();
  const checks = {
    mode: MODE,
    demoBanner: /Demo data|demo fixture|Data source warning/i.test(body),
    liveBadge: /\blive\b/i.test(body),
    workflow: /Autonomous scientist workflow/i.test(body),
    candidate: /Candidate decision/i.test(body),
    experiment: /Experiment handoff/i.test(body),
    labLog: /Live activity|Paperclip|evidence/i.test(body),
  };
  fs.writeFileSync(path.join(OUT, "checks.json"), JSON.stringify(checks, null, 2));
  log(`checks ${JSON.stringify(checks)}`);
  if (!checks.candidate) throw new Error("did not reach Candidate decision");
} finally {
  const video = page.video();
  await context.close();
  await browser.close();
  if (video) {
    const raw = await video.path();
    const dest = path.join(OUT, MODE === "live" ? "e2e-live.webm" : "e2e-fixture.webm");
    fs.renameSync(raw, dest);
    log(`video ${dest}`);
  }
}
