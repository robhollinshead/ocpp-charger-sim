/**
 * Capture screenshots of the simulator UI for documentation.
 * Requires the frontend to be running (e.g. npm run dev in frontend/) and optionally the backend.
 * Usage: from repo root, npm run docs:screenshots
 *        or: BASE_URL=http://localhost:8080 node scripts/capture-screenshots.js
 */

const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const BASE_URL = process.env.BASE_URL || 'http://localhost:8080';
const OUT_DIR = path.join(__dirname, '..', 'docs', 'screenshots');

const CAPTURES = [
  { name: 'location-list', url: '/' },
  { name: 'location-detail', url: '/location/ff447169-4f73-47f1-9d21-e1f757cb362e' },
  { name: 'charger-detail', url: '/location/ff447169-4f73-47f1-9d21-e1f757cb362e/charger/Charger-001' },
];

async function main() {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.setViewportSize({ width: 1200, height: 800 });

  for (const { name, url } of CAPTURES) {
    const fullUrl = new URL(url, BASE_URL).href;
    try {
      await page.goto(fullUrl, { waitUntil: 'networkidle', timeout: 10000 });
      await page.waitForTimeout(500);
      const outPath = path.join(OUT_DIR, `${name}.png`);
      await page.screenshot({ path: outPath, fullPage: false });
      console.log('Captured:', outPath);
    } catch (e) {
      console.warn('Skip', name, ':', e.message);
    }
  }

  await browser.close();
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
