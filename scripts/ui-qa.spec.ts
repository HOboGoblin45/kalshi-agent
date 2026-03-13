import { test, expect, type Browser, type BrowserContext, type Page, chromium } from "@playwright/test";
import { spawn, type ChildProcess } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const ROOT = process.cwd();
const SHOT_DIR = path.join(ROOT, "qa-screenshots");

interface ServerInfo {
  proc: ChildProcess;
  baseUrl: string;
}

function startMockServer(scenario: "normal" | "empty_markets" | "error_state"): Promise<ServerInfo> {
  return new Promise((resolve, reject) => {
    const proc = spawn(
      "python",
      ["scripts/mock_dashboard_server.py", "--host", "127.0.0.1", "--port", "0", "--scenario", scenario],
      { cwd: ROOT }
    );

    let resolved = false;
    const timeout = setTimeout(() => {
      if (!resolved) {
        proc.kill("SIGTERM");
        reject(new Error(`Mock server did not start for scenario=${scenario}`));
      }
    }, 10000);

    proc.stdout?.on("data", (buf) => {
      const text = String(buf);
      const match = text.match(/READY:(\d+):/);
      if (match) {
        clearTimeout(timeout);
        resolved = true;
        resolve({ proc, baseUrl: `http://127.0.0.1:${match[1]}` });
      }
    });

    proc.stderr?.on("data", (buf) => {
      const text = String(buf).trim();
      if (text) process.stderr.write(`${text}\n`);
    });

    proc.on("exit", (code) => {
      if (!resolved) {
        clearTimeout(timeout);
        reject(new Error(`Mock server exited early with code ${code}`));
      }
    });
  });
}

async function stopMockServer(proc: ChildProcess | null): Promise<void> {
  if (!proc || proc.killed) return;
  proc.kill("SIGTERM");
  await new Promise((resolve) => setTimeout(resolve, 300));
}

async function openPage(browser: Browser, width: number, height: number): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ viewport: { width, height } });
  const page = await context.newPage();
  return { context, page };
}

async function assertGridColumns(page: Page, expected: number) {
  const cols = await page.evaluate(() => {
    const cards = Array.from(document.querySelectorAll(".card.cursor-pointer")) as HTMLElement[];
    if (cards.length === 0) return 0;
    const tops = cards.map((el) => Math.round(el.getBoundingClientRect().top));
    const firstTop = Math.min(...tops);
    const row = cards.filter((el) => Math.abs(Math.round(el.getBoundingClientRect().top) - firstTop) <= 2);
    const lefts = row.map((el) => Math.round(el.getBoundingClientRect().left));
    return new Set(lefts).size;
  });
  expect(cols).toBe(expected);
}

async function assertCardsDoNotOverlap(page: Page) {
  const overlaps = await page.evaluate(() => {
    const cards = Array.from(document.querySelectorAll(".card.cursor-pointer")) as HTMLElement[];
    const rects = cards.map((el) => el.getBoundingClientRect());
    let bad = 0;
    for (let i = 0; i < rects.length; i++) {
      for (let j = i + 1; j < rects.length; j++) {
        const a = rects[i];
        const b = rects[j];
        const intersect = a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
        if (intersect) bad += 1;
      }
    }
    return bad;
  });
  expect(overlaps).toBe(0);
}

test.describe("UI QA", () => {
  let browser: Browser;
  let server: ChildProcess | null = null;
  let baseUrl = "";

  test.beforeAll(async () => {
    fs.mkdirSync(SHOT_DIR, { recursive: true });
    browser = await chromium.launch({ headless: true });
    const started = await startMockServer("normal");
    server = started.proc;
    baseUrl = started.baseUrl;
  });

  test.afterAll(async () => {
    await stopMockServer(server);
    await browser.close();
  });

  test("desktop and small-window route coverage with screenshots", async () => {
    const { context, page } = await openPage(browser, 1440, 900);
    await page.goto(`${baseUrl}/`, { waitUntil: "networkidle" });
    await expect(page.getByRole("heading", { name: "Markets" })).toBeVisible();
    await assertGridColumns(page, 3);
    await assertCardsDoNotOverlap(page);
    await expect(page.locator("svg").first()).toBeVisible();
    await page.screenshot({ path: path.join(SHOT_DIR, "desktop-markets.png"), fullPage: true });

    await page.getByRole("textbox", { name: "" }).fill("no-match-xyz-123");
    await expect(page.getByText("No markets found")).toBeVisible();
    await page.screenshot({ path: path.join(SHOT_DIR, "desktop-markets-filtered-empty.png"), fullPage: true });
    await page.getByRole("textbox", { name: "" }).fill("");

    await page.locator(".card.cursor-pointer").first().click();
    await expect(page).toHaveURL(/\/market\//);
    await expect(page.getByText("Back")).toBeVisible();
    await page.screenshot({ path: path.join(SHOT_DIR, "desktop-market-detail.png"), fullPage: true });

    await page.goto(`${baseUrl}/positions`, { waitUntil: "networkidle" });
    await expect(page.getByRole("heading", { name: "Live Positions" })).toBeVisible();
    await page.screenshot({ path: path.join(SHOT_DIR, "desktop-positions.png"), fullPage: true });

    await page.goto(`${baseUrl}/alerts`, { waitUntil: "networkidle" });
    await expect(page.getByRole("heading", { name: "Activity Log" })).toBeVisible();
    await page.screenshot({ path: path.join(SHOT_DIR, "desktop-alerts.png"), fullPage: true });

    await page.goto(`${baseUrl}/bot`, { waitUntil: "networkidle" });
    await expect(page.getByPlaceholder("Ask about trades, P&L, scans...")).toBeVisible();
    await page.screenshot({ path: path.join(SHOT_DIR, "desktop-bot.png"), fullPage: true });

    await page.goto(`${baseUrl}/profile`, { waitUntil: "networkidle" });
    await expect(page.getByRole("heading", { name: "Kalshi Agent" })).toBeVisible();
    await page.screenshot({ path: path.join(SHOT_DIR, "desktop-profile.png"), fullPage: true });

    await context.close();

    const small = await openPage(browser, 900, 600);
    await small.page.goto(`${baseUrl}/`, { waitUntil: "networkidle" });
    await assertGridColumns(small.page, 2);
    await assertCardsDoNotOverlap(small.page);
    await small.page.screenshot({ path: path.join(SHOT_DIR, "small-markets.png"), fullPage: true });
    await small.context.close();
  });

  test("mobile single-column markets layout screenshot", async () => {
    const { context, page } = await openPage(browser, 390, 844);
    await page.goto(`${baseUrl}/`, { waitUntil: "networkidle" });
    await assertGridColumns(page, 1);
    await page.screenshot({ path: path.join(SHOT_DIR, "mobile-markets.png"), fullPage: true });
    await context.close();
  });

  test("empty markets state and error screen", async () => {
    await stopMockServer(server);
    {
      const started = await startMockServer("empty_markets");
      server = started.proc;
      baseUrl = started.baseUrl;
    }

    const emptyCtx = await openPage(browser, 900, 600);
    await emptyCtx.page.goto(`${baseUrl}/`, { waitUntil: "networkidle" });
    await expect(emptyCtx.page.getByText("No markets loaded yet")).toBeVisible();
    await emptyCtx.page.screenshot({ path: path.join(SHOT_DIR, "small-markets-empty.png"), fullPage: true });
    await emptyCtx.context.close();

    await stopMockServer(server);
    {
      const started = await startMockServer("error_state");
      server = started.proc;
      baseUrl = started.baseUrl;
    }

    const errCtx = await openPage(browser, 900, 600);
    await errCtx.page.goto(`${baseUrl}/`, { waitUntil: "networkidle" });
    await expect(errCtx.page.getByText("Agent Not Running")).toBeVisible();
    await errCtx.page.screenshot({ path: path.join(SHOT_DIR, "small-error-screen.png"), fullPage: true });
    await errCtx.context.close();

    await stopMockServer(server);
    {
      const started = await startMockServer("normal");
      server = started.proc;
      baseUrl = started.baseUrl;
    }
  });
});
