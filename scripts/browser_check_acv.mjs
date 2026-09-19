/** Real-browser check of the ACV tab and the How-it-works page against a running server.
 * DOORLENS_URL=http://127.0.0.1:8001 node scripts/browser_check_acv.mjs <acv-file> <expected-top-car>
 */
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { existsSync } from 'node:fs';
import { mkdir } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const app = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const { chromium } = createRequire(path.join(app, 'frontend', 'package.json'))('playwright');
const base = process.env.DOORLENS_URL || 'http://127.0.0.1:8000';
const [file, expected] = process.argv.slice(2);
const executablePath = process.env.DOORLENS_BROWSER || ['C:/Program Files/Google/Chrome/Application/chrome.exe', 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'].find(existsSync);
const shots = path.join(app, 'artifacts', 'screens'); await mkdir(shots, { recursive: true });
const browser = await chromium.launch({ headless: true, ...(executablePath ? { executablePath } : {}) });
const page = await (await browser.newContext({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true })).newPage();
const errors = []; page.on('pageerror', e => errors.push(e.message)); page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });

await page.goto(base);
await page.getByRole('button', { name: /ACV/ }).click();
await page.getByRole('heading', { name: /Which car is leaking/ }).waitFor();
await page.setInputFiles('input[aria-label="Choose ACV telemetry file"]', file);
await page.getByRole('button', { name: 'Rank the cars' }).click();
await page.getByText('Most likely leaking car').waitFor({ timeout: 120000 });
const top = await page.locator('div[class*="big"]').first().innerText();
console.log('top pick shown:', top);
if (expected) assert.equal(top.trim(), `Car ${expected}`);
await page.waitForSelector('.js-plotly-plot', { timeout: 20000 });
await page.screenshot({ path: path.join(shots, 'acv-result.png'), fullPage: true });
const [dl] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: 'acv_predictions.csv' }).click()]);
console.log('download:', dl.suggestedFilename());
assert.equal(dl.suggestedFilename(), 'acv_predictions.csv');

await page.getByRole('link', { name: /How this works/ }).click();
await page.getByRole('heading', { name: /What DoorLens does/ }).waitFor();
await page.screenshot({ path: path.join(shots, 'how-it-works.png'), fullPage: true });
await page.setViewportSize({ width: 390, height: 800 });
await page.screenshot({ path: path.join(shots, 'how-it-works-mobile.png'), fullPage: true });
console.log('page errors:', errors.length ? errors : 'none');
await browser.close();
assert.equal(errors.length, 0);
