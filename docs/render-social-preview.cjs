// Development-only asset rendering; uses an existing Playwright installation.
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const {pathToFileURL} = require('node:url');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
(async () => {
  const browser = await chromium.launch({headless: true,
    ...(process.env.CHROMIUM_EXECUTABLE ? {executablePath: process.env.CHROMIUM_EXECUTABLE} : {})});
  try {
    const page = await browser.newPage({viewport: {width: 1280, height: 1200}, deviceScaleFactor: 1, reducedMotion: 'reduce'});
    await page.route(/^https?:/, route => route.abort());
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(pathToFileURL(path.resolve(__dirname, '../demo.html')).href);
    await page.locator('#metrics .metric').first().waitFor();
    assert.equal(await page.locator('#demo-banner').isVisible(), true);
    const metrics = await page.locator('#metrics').boundingBox();
    await page.screenshot({path: path.join(__dirname, 'images/social-preview-demo.png'),
      clip: {x: 0, y: Math.max(0, metrics.y - 16), width: 1280, height: 680}});
    await page.setViewportSize({width: 1280, height: 640});
    await page.goto(pathToFileURL(path.join(__dirname, 'social-preview.html')).href);
    await page.locator('img').evaluate(image => image.decode());
    await page.screenshot({path: path.join(__dirname, 'images/social-preview.png')});
    assert.deepEqual(errors, []);
    const bytes = fs.statSync(path.join(__dirname, 'images/social-preview.png')).size;
    assert.ok(bytes < 1000000, 'GitHub social preview must be under 1 MB');
    console.log(JSON.stringify({width: 1280, height: 640, bytes, data: 'bundled synthetic demo', pageErrors: errors}));
  } finally { await browser.close(); }
})().catch(error => {console.error(error); process.exitCode = 1;});
