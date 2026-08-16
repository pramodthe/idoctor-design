#!/usr/bin/env node
/**
 * Short hackathon product demo of the trust UI.
 *
 *   E2E_URL=http://localhost:3001/?viewer-check=1 node scripts/hackathon_demo_video.mjs
 */
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const OUT = path.join(ROOT, "output", "hackathon-demo");
const URL =
  process.env.E2E_URL || "http://127.0.0.1:3001/?viewer-check=1";

fs.mkdirSync(OUT, { recursive: true });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function smoothScroll(page, y, steps = 18) {
  const start = await page.evaluate(() => window.scrollY);
  const delta = y - start;
  for (let i = 1; i <= steps; i++) {
    const next = start + (delta * i) / steps;
    await page.evaluate((top) => window.scrollTo({ top, behavior: "instant" }), next);
    await sleep(45);
  }
}

async function scrollInto(page, locator, pause = 900) {
  if (!(await locator.count())) return false;
  await locator.first().scrollIntoViewIfNeeded();
  await sleep(pause);
  return true;
}

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  deviceScaleFactor: 1,
  recordVideo: { dir: OUT, size: { width: 1440, height: 900 } },
});
const page = await context.newPage();

function log(msg) {
  console.log(`[demo] ${msg}`);
}

try {
  log(`open ${URL}`);
  await page.goto(URL, { waitUntil: "networkidle", timeout: 45_000 });
  await page.getByRole("heading", { name: "iDoctor Design" }).first().waitFor({
    timeout: 20_000,
  });
  await sleep(1200);

  // Ensure a full run is on screen (auto-load can race; Load Data is explicit).
  const hasCandidate = await page.getByText("Candidate review").isVisible().catch(() => false);
  if (!hasCandidate) {
    log("load latest run");
    await page.getByRole("button", { name: "Load Data" }).click();
    await sleep(350);
    const latest = page.getByRole("button", { name: /Load Latest Saved Run/i });
    if (await latest.isVisible().catch(() => false)) {
      await latest.click();
    } else {
      await page.getByRole("button", { name: /Open Demo Fixture/i }).click();
    }
    await page.getByText("Candidate review").waitFor({ timeout: 45_000 });
  }
  await sleep(1400);
  await page.screenshot({ path: path.join(OUT, "01-hero.png") });

  // Hero metrics / rejection story
  log("hero metrics");
  await sleep(1100);

  // Candidate review table — click a reject row if present
  log("candidate review");
  await scrollInto(page, page.getByRole("heading", { name: "Candidate review" }), 1000);
  await page.screenshot({ path: path.join(OUT, "02-candidates.png") });
  const rejectRow = page.locator("button, tr, [role='row'], [role='button']").filter({
    hasText: /reject/i,
  }).first();
  if (await rejectRow.count()) {
    await rejectRow.click({ timeout: 3000 }).catch(() => {});
    await sleep(900);
  }
  const anyDesign = page.getByText(/des_00\d/i).first();
  if (await anyDesign.isVisible().catch(() => false)) {
    await anyDesign.click().catch(() => {});
    await sleep(800);
  }

  // Verification loop
  log("verification loop");
  await scrollInto(page, page.getByRole("heading", { name: /Verification loop/i }), 1000);

  // Agent graph — expand one node
  log("agent graph");
  await scrollInto(page, page.getByRole("heading", { name: "Autonomous scientist workflow" }), 1100);
  await page.screenshot({ path: path.join(OUT, "03-graph.png") });
  const criticNode = page.getByRole("button", { name: /Scientist critic|adversarial reject/i }).first();
  if (await criticNode.count()) {
    await criticNode.click({ timeout: 4000 }).catch(() => {});
    await sleep(1200);
  }
  const literature = page.getByRole("button", { name: /Literature|Paperclip/i }).first();
  if (await literature.count()) {
    await literature.click({ timeout: 3000 }).catch(() => {});
    await sleep(1000);
  }

  // Structure / complex panel
  log("structure viewer");
  await scrollInto(
    page,
    page.getByRole("heading", { name: /complex|structure|pocket|WT|mutant|binder/i }),
    1200
  );
  await page.screenshot({ path: path.join(OUT, "04-structure.png") });
  await sleep(1400);

  // Selected candidate + sequence + critic summary
  log("selected candidate");
  await scrollInto(page, page.getByRole("heading", { name: "Selected candidate" }), 1100);
  await page.screenshot({ path: path.join(OUT, "05-candidate.png") });
  await sleep(900);

  // Lab log + experiment handoff
  log("lab log + experiment");
  await scrollInto(page, page.getByRole("heading", { name: /Live activity|lab log/i }), 900);
  await scrollInto(page, page.getByRole("heading", { name: "Experiment handoff" }), 1200);
  await page.screenshot({ path: path.join(OUT, "06-experiment.png") });
  await sleep(1400);

  // Final slow sweep back to top for a clean end card
  log("return to hero");
  await smoothScroll(page, 0, 24);
  await sleep(1200);
  await page.screenshot({ path: path.join(OUT, "07-end.png") });
} catch (err) {
  console.error("[demo] FAILED", err);
  await page.screenshot({ path: path.join(OUT, "error.png"), fullPage: true }).catch(() => {});
  throw err;
} finally {
  const video = page.video();
  await context.close();
  await browser.close();
  if (video) {
    const raw = await video.path();
    const dest = path.join(OUT, "idoctor-hackathon-demo.webm");
    fs.renameSync(raw, dest);
    log(`video ${dest}`);
  }
}
