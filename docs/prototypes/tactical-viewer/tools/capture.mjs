import { mkdir, writeFile } from "node:fs/promises";
import { fileURLToPath, pathToFileURL } from "node:url";
import path from "node:path";

const playwrightModule = process.env.TACTICAL_PLAYWRIGHT_MODULE;
const chromePath = process.env.TACTICAL_CHROME_PATH;
const baseUrl = process.env.TACTICAL_PROTOTYPE_URL ?? "http://127.0.0.1:8787";
if (!playwrightModule || !chromePath) {
  throw new Error("需要 TACTICAL_PLAYWRIGHT_MODULE 与 TACTICAL_CHROME_PATH");
}

const { chromium } = await import(pathToFileURL(playwrightModule).href);
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const screenshots = path.join(root, "public", "artifacts", "screenshots");
await mkdir(screenshots, { recursive: true });
const browser = await chromium.launch({ executablePath: chromePath, headless: true });
const page = await browser.newPage({ viewport: { width: 1600, height: 1050 }, deviceScaleFactor: 1 });
page.setDefaultTimeout(120000);
const requestMethods = [];
page.on("request", (request) => requestMethods.push(request.method()));

async function open(route) {
  await page.goto(`${baseUrl}/${route}`, { waitUntil: "networkidle" });
  await page.waitForFunction(() => window.__TACTICAL_PROTOTYPE__?.ready === true);
}

async function clickCell(label) {
  await page.locator(`[data-cell="${label}"]`).click();
}

const performanceResults = {
  capturedAt: new Date().toISOString(),
  browser: "system Chromium via installed Google Chrome, headless",
  samples: {},
  runtimeChecks: {}
};

try {
  await open("?variant=A&map=small");
  await page.locator('[data-entity-id="pc-aria"]').click();
  await page.locator('[data-mode="dash"]').click();
  await clickCell("L7");
  performanceResults.samples.small = await page.evaluate(() => window.__TACTICAL_PROTOTYPE__.benchmark(20));
  performanceResults.runtimeChecks.smallState = await page.evaluate(() => window.__TACTICAL_PROTOTYPE__.getState());
  performanceResults.runtimeChecks.smallDigest = await page.evaluate(() => window.__TACTICAL_PROTOTYPE__.getSceneDigest());
  await page.screenshot({ path: path.join(screenshots, "small-a-dash-path.png"), fullPage: true });

  await open("?variant=B&map=small");
  await page.locator('[data-entity-id="pc-aria"]').click();
  await page.screenshot({ path: path.join(screenshots, "small-b-normal-range.png"), fullPage: true });

  await open("?variant=C&map=small");
  await page.locator('[data-entity-id="pc-aria"]').click();
  await page.locator('[data-mode="dash"]').click();
  await clickCell("L7");
  await page.screenshot({ path: path.join(screenshots, "small-c-quiet-table.png"), fullPage: true });

  await open("?variant=A&map=large");
  await page.locator('[data-entity-id="pc-large-1"]').click();
  await page.locator('[data-mode="dash"]').click();
  await clickCell("J42");
  performanceResults.samples.large = await page.evaluate(() => window.__TACTICAL_PROTOTYPE__.benchmark(20));
  performanceResults.runtimeChecks.largeState = await page.evaluate(() => window.__TACTICAL_PROTOTYPE__.getState());
  performanceResults.runtimeChecks.largeDigest = await page.evaluate(() => window.__TACTICAL_PROTOTYPE__.getSceneDigest());
  await page.screenshot({ path: path.join(screenshots, "large-50x50-dash.png"), fullPage: true });
  await page.evaluate(() => {
    const mapRoot = document.querySelector("#map-root");
    mapRoot.scrollTop = mapRoot.scrollHeight;
  });
  await page.screenshot({ path: path.join(screenshots, "large-50x50-bottom-path.png"), fullPage: true });

  await page.goto(`${baseUrl}/artifacts/static-fallback.svg`, { waitUntil: "networkidle" });
  await page.locator("svg").screenshot({ path: path.join(screenshots, "static-fallback.png"), timeout: 120000 });

  performanceResults.runtimeChecks.requestMethods = [...new Set(requestMethods)];
  performanceResults.runtimeChecks.allRequestsReadOnly = requestMethods.every((method) => method === "GET");
  performanceResults.runtimeChecks.authoritySnapshotsUnchanged = [
    performanceResults.runtimeChecks.smallDigest,
    performanceResults.runtimeChecks.largeDigest
  ].every(({ before, after }) => before === after);
  await writeFile(
    path.join(root, "public", "artifacts", "performance-results.json"),
    `${JSON.stringify(performanceResults, null, 2)}\n`
  );
  console.log(JSON.stringify(performanceResults, null, 2));
} finally {
  await browser.close();
}
