// Optional browser regressions: node test_dashboard_browser.cjs
// Uses an existing Playwright installation; PLAYWRIGHT_MODULE,
// BROWSER_ENGINE, BROWSER_EXECUTABLE (or CHROMIUM_EXECUTABLE) are optional.
// Optional axe-core checks use AXE_CORE_MODULE or an installed axe-core.
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {test, before, after} = require('node:test');
const playwright = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const engine = process.env.BROWSER_ENGINE || 'chromium';
assert.ok(['chromium', 'firefox', 'webkit'].includes(engine), 'supported browser engine');
let axe;
try { axe = require(process.env.AXE_CORE_MODULE || 'axe-core'); } catch (error) {
  if (process.env.AXE_CORE_MODULE) throw error;
}
const origin = 'http://127.0.0.1:18765';
let browser;
before(async () => {
  const executable = process.env.BROWSER_EXECUTABLE || (engine === 'chromium' && process.env.CHROMIUM_EXECUTABLE);
  browser = await playwright[engine].launch({headless: true,
    ...(executable ? {executablePath: executable} : {})});
});
after(async () => { if (browser) await browser.close(); });

async function fixture(t, options = {}) {
  const context = await browser.newContext({viewport: {width: 1440, height: 1000}, reducedMotion: options.reducedMotion || 'reduce', hasTouch:Boolean(options.touch)});
  t.after(() => context.close());
  const page = await context.newPage();
  page.setDefaultTimeout(10000);
  if (options.graphics) await page.addInitScript(mode => {
    window.decorativeDraws = 0;
    window.decorativeAnimatedDraws = 0;
    const mediaQuery = window.matchMedia.bind(window);
    window.motionQueries = [];
    window.matchMedia = query => {
      const result = mediaQuery(query);
      if (query.includes('prefers-reduced-motion')) {
        window.motionQueries.push(result);
      }
      return result;
    };
    const original = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function(type, attributes) {
      if (this.id !== 'topo-canvas' || type !== 'webgl') return original.call(this, type, attributes);
      if (mode === 'unavailable') return null;
      const gl = original.call(this, type, attributes);
      if (!gl) return null;
      const extension = gl.getExtension.bind(gl), parameter = gl.getParameter.bind(gl), draw = gl.drawArrays.bind(gl), uniform = gl.uniform1f.bind(gl);
      let frameTime = 0;
      gl.getExtension = name => name === 'WEBGL_debug_renderer_info' ? {UNMASKED_RENDERER_WEBGL: 0x9246} : extension(name);
      gl.getParameter = key => key === 0x9246 || key === gl.RENDERER ? (mode === 'software' ? 'SwiftShader test renderer' : 'Hardware test renderer') : parameter(key);
      gl.uniform1f = (location, value) => { frameTime = value; return uniform(location, value); };
      gl.drawArrays = (...args) => { window.decorativeDraws++; if (frameTime !== 0) window.decorativeAnimatedDraws++; return draw(...args); };
      return gl;
    };
  }, options.graphics);
  const errors = [];
  const consoleMessages = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => {
    if (['error', 'warning'].includes(message.type())) consoleMessages.push(message.text());
  });
  t.after(() => assert.deepEqual(errors, [], 'no application page errors'));
  t.after(() => {
    const unexpected = consoleMessages.filter(message =>
      !(/Failed to load resource/.test(message) && /409|503/.test(message)) &&
      !/WebGL context was lost\.|GPU stall due to ReadPixels|Automatic fallback to software WebGL has been deprecated/.test(message));
    assert.deepEqual(unexpected, [], 'no unexpected browser console errors or warnings');
    if (consoleMessages.length) t.diagnostic('Console messages limited to fixture HTTP 409/503 responses, released WebGL contexts, or known software/readback warnings.');
  });
  const data = JSON.parse(fs.readFileSync(path.join(__dirname, 'demo.json'), 'utf8'));
  Object.assign(data, {live: true, repository_management: true, collection_running: true});
  for (const repo of data.repositories) repo.removable = true;
  if (options.prepare) options.prepare(data);
  const html = fs.readFileSync(path.join(__dirname, 'dashboard.html'), 'utf8')
    .replace('__GIT_DASHBOARD_DATA__', JSON.stringify(data).replaceAll('<', '\\u003c'));
  if (!options.nativeClock) await page.clock.install();
  await page.route('**/*', async route => {
    const url = new URL(route.request().url());
    assert.equal(url.origin, origin, 'fixture does not call external services');
    if (url.pathname === '/api/commit-pulls' && options.pulls) return options.pulls(route);
    if (url.pathname === '/api/snapshot') {
      if (options.snapshot) return options.snapshot(route, data);
      return route.fulfill({json: data});
    }
    if (url.pathname === '/api/repositories' && options.add) return options.add(route, data);
    if (url.pathname === '/api/repositories/remove' && options.remove) return options.remove(route, data);
    if (url.pathname !== '/') return route.fulfill({status: 404, body: 'Not found'});
    return route.fulfill({contentType: 'text/html', body: html});
  });
  await page.goto(origin);
  assert.equal(await page.title(), 'Git activity dashboard');
  assert.ok(await page.locator('#metrics .metric').count(), 'meaningful dashboard content');
  return {page, data};
}

async function until(check, message) {
  for (let i = 0; i < 100; i++) {
    if (await check()) return;
    await new Promise(resolve => setTimeout(resolve, 20));
  }
  assert.fail(message);
}

test('automatic refresh preserves chart date/focus and expanded worktree details', async t => {
  const {page, data} = await fixture(t);
  const detail = page.locator('#work-table .files').first();
  await detail.locator('summary').click();
  const plot = page.locator('#commits-chart [role=slider]');
  await plot.focus();
  await plot.press('ArrowRight');
  await plot.press('ArrowRight');
  const selected = await plot.getAttribute('aria-valuetext');
  const response = page.waitForResponse('**/api/snapshot');
  await page.clock.fastForward(3000);
  await response;
  await until(() => page.locator('#refresh-button').isEnabled(), 'refresh completes');
  assert.equal(await plot.evaluate(node => node === document.activeElement), true, 'chart keeps keyboard focus');
  assert.equal(await plot.getAttribute('aria-valuetext'), selected, 'selected chart date remains');
  assert.equal(await detail.evaluate(node => node.open), true, 'changed paths remain expanded');
  // The same calendar day must stay selected when history gains an earlier bucket.
  for (const repo of data.repositories) {
    if (!repo.history?.daily?.length) continue;
    const date = new Date(repo.history.daily[0].date + 'T12:00:00Z');
    date.setUTCDate(date.getUTCDate() - 1);
    repo.history.daily.unshift({date: date.toISOString().slice(0, 10), commits: 0, added: 0, deleted: 0});
  }
  await page.locator('#range-select').selectOption('all');
  await plot.focus();
  const next = page.waitForResponse('**/api/snapshot');
  await page.clock.fastForward(3000);
  await next;
  await until(() => page.locator('#refresh-button').isEnabled(), 'second refresh completes');
  assert.equal(await plot.getAttribute('aria-valuetext'), selected, 'selection follows date, not row index');
  if (process.env.UI_SCREENSHOT_DIR) {
    fs.mkdirSync(process.env.UI_SCREENSHOT_DIR, {recursive: true});
    await page.screenshot({path: path.join(process.env.UI_SCREENSHOT_DIR, 'refresh-desktop.png')});
  }
  const remove = page.getByRole('button', {name: 'Remove ' + data.repositories[0].name, exact: true});
  await remove.focus();
  const third = page.waitForResponse('**/api/snapshot');
  await page.clock.fastForward(3000);
  await third;
  await until(() => page.locator('#refresh-button').isEnabled(), 'third refresh completes');
  assert.equal(await remove.evaluate(node => node === document.activeElement), true, 'repository action keeps keyboard focus');
  await detail.locator('summary').focus();
  const fourth = page.waitForResponse('**/api/snapshot');
  await page.clock.fastForward(3000);
  await fourth;
  await until(() => page.locator('#refresh-button').isEnabled(), 'fourth refresh completes');
  assert.equal(await detail.locator('summary').evaluate(node => node === document.activeElement), true, 'worktree disclosure keeps keyboard focus');
});

test('late add success preserves a reopened dialog and its newer draft', async t => {
  let finish;
  const pending = new Promise(resolve => { finish = resolve; });
  const {page} = await fixture(t, {add: async route => {
    await pending;
    await route.fulfill({json: {repository: {name: 'First repository'}}});
  }});
  await page.locator('#add-button').click();
  await page.locator('#add-path').fill('https://github.com/example/first');
  const sent = page.waitForRequest('**/api/repositories');
  await page.locator('#add-submit').click();
  await sent;
  await page.locator('#add-cancel').click();
  await page.locator('#add-button').click();
  await page.locator('#add-path').fill('https://github.com/example/second');
  await page.locator('#add-name').fill('Second repository');
  finish();
  await until(async () => (await page.locator('#repository-message').textContent()).includes('First repository'), 'late result is reported');
  assert.equal(await page.locator('#add-dialog').evaluate(node => node.open), true);
  assert.equal(await page.locator('#add-path').inputValue(), 'https://github.com/example/second');
  assert.equal(await page.locator('#add-name').inputValue(), 'Second repository');
  assert.equal(await page.locator('#add-submit').isEnabled(), true);
});

test('removal supports cancellation, errors, success and selection fallback', async t => {
  let attempts = 0;
  const {page, data} = await fixture(t, {remove: async (route, snapshot) => {
    attempts++;
    if (attempts === 1) return route.fulfill({status: 409, json: {error: {message: 'Configuration changed. Restart to reload.'}}});
    const {path: removedPath} = route.request().postDataJSON();
    const repo = snapshot.repositories.find(repo => repo.path === removedPath);
    snapshot.repositories = snapshot.repositories.filter(repo => repo.path !== removedPath);
    return route.fulfill({json: {removed: {path: removedPath, name: repo.name, configured_paths: [removedPath]}}});
  }});
  const repo = data.repositories[0];
  await page.locator('#repo-select').selectOption(repo.path);
  const remove = page.getByRole('button', {name: 'Remove ' + repo.name, exact: true});
  page.once('dialog', dialog => dialog.dismiss());
  await remove.click();
  assert.equal(attempts, 0, 'cancel sends no mutation');
  page.once('dialog', dialog => { assert.match(dialog.message(), /files.*cache.*kept/i); return dialog.accept(); });
  await remove.click();
  await until(async () => (await page.locator('#repository-message').textContent()).includes('Configuration changed'), 'failure remains visible');
  assert.equal(await remove.isEnabled(), true, 'failure permits retry');
  assert.equal(await page.locator('#repo-select').inputValue(), repo.path, 'failed removal keeps selection');
  page.once('dialog', dialog => dialog.accept());
  await remove.click();
  await until(async () => (await page.locator('#repository-message').textContent()).includes('removed'), 'success is reported');
  assert.equal(await page.locator('#repo-select').inputValue(), '', 'removed selection falls back to all repositories');
  assert.equal(await page.getByRole('button', {name: 'Remove ' + repo.name, exact: true}).count(), 0);
  await page.setViewportSize({width: 390, height: 844});
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, 'mobile page fits');
  await page.getByRole('button', {name: /^Remove /}).first().scrollIntoViewIfNeeded();
  if (process.env.UI_SCREENSHOT_DIR) {
    fs.mkdirSync(process.env.UI_SCREENSHOT_DIR, {recursive: true});
    await page.screenshot({path: path.join(process.env.UI_SCREENSHOT_DIR, 'removal-mobile.png')});
  }
});

test('read-only rows do not offer removal', async t => {
  const {page, data} = await fixture(t);
  await page.getByRole('button', {name: 'Remove ' + data.repositories[0].name, exact: true}).focus();
  for (const repo of data.repositories) repo.removable = false;
  const response = page.waitForResponse('**/api/snapshot');
  await page.clock.fastForward(3000);
  await response;
  await until(() => page.locator('#refresh-button').isEnabled(), 'refresh completes');
  assert.equal(await page.getByRole('button', {name: /^Remove /}).count(), 0);
  assert.equal(await page.evaluate(() => document.activeElement.id), 'repo-select', 'removed action has a keyboard focus fallback');
});

test('a snapshot requested before removal cannot restore the removed row', async t => {
  let releaseSnapshot;
  const held = new Promise(resolve => { releaseSnapshot = resolve; });
  let snapshots = 0;
  const {page, data} = await fixture(t, {
    snapshot: async (route, snapshot) => {
      const body = JSON.stringify(snapshot);
      if (++snapshots === 1) await held;
      await route.fulfill({contentType: 'application/json', body});
    },
    remove: async (route, snapshot) => {
      const removedPath = route.request().postDataJSON().path;
      snapshot.repositories = snapshot.repositories.filter(repo => repo.path !== removedPath);
      await route.fulfill({json: {removed: {path: removedPath, configured_paths: [removedPath]}}});
    }
  });
  const repo = data.repositories[0];
  const pending = page.waitForRequest('**/api/snapshot');
  await page.clock.fastForward(3000);
  await pending;
  page.once('dialog', dialog => dialog.accept());
  await page.getByRole('button', {name: 'Remove ' + repo.name, exact: true}).click();
  await until(async () => (await page.locator('#repository-message').textContent()).includes('removed'), 'removal completes');
  const stale = page.waitForResponse('**/api/snapshot');
  const fresh = page.waitForResponse(response => response.url().endsWith('/api/snapshot') && snapshots >= 2);
  releaseSnapshot();
  await stale;
  await until(() => page.locator('#refresh-button').isEnabled(), 'old snapshot request completes');
  assert.equal(await page.getByRole('button', {name: 'Remove ' + repo.name, exact: true}).count(), 0, 'stale HTTP response is ignored');
  await page.clock.fastForward(1);
  await fresh;
  assert.equal(snapshots, 2, 'mutation triggers a fresh snapshot after the old request');
});

test('late add failure cannot overwrite the status of a newer pending submission', async t => {
  const releases = [];
  const {page} = await fixture(t, {add: async route => {
    const index = releases.length;
    await new Promise(resolve => releases.push(resolve));
    await route.fulfill(index === 0
      ? {status: 409, json: {error: {message: 'The first repository failed.'}}}
      : {json: {repository: {name: 'Second repository'}}});
  }});
  await page.locator('#add-button').click();
  await page.locator('#add-path').fill('https://github.com/example/first');
  await page.locator('#add-submit').click();
  await until(() => releases.length === 1, 'first request reaches server');
  await page.locator('#add-path').press('Escape');
  await page.locator('#add-button').click();
  await page.locator('#add-path').fill('https://github.com/example/second');
  await page.locator('#add-submit').click();
  await until(() => releases.length === 2, 'second request reaches server');
  releases[0]();
  await until(async () => (await page.locator('#repository-message').textContent()).includes('first'), 'late failure is reported separately');
  assert.equal(await page.locator('#add-status').textContent(), 'Checking public repository…');
  assert.equal(await page.locator('#add-submit').isDisabled(), true, 'old request cannot enable a newer pending submission');
  releases[1]();
  await until(async () => (await page.locator('#repository-message').textContent()).includes('Second repository added'), 'new submission completes');
  assert.equal(await page.locator('#add-dialog').evaluate(node => node.open), false);
});

test('keyboard flow reaches tabs and panels and modal focus returns to its opener', async t => {
  const {page} = await fixture(t);
  await page.locator('#product-select').focus();
  for (const id of ['repo-select', 'range-select', 'add-button']) {
    await page.keyboard.press('Tab');
    assert.equal(await page.evaluate(() => document.activeElement.id), id);
  }
  await page.keyboard.press('Enter');
  assert.equal(await page.evaluate(() => document.activeElement.id), 'add-source');
  await page.keyboard.press('Shift+Tab');
  assert.equal(await page.evaluate(() => document.activeElement.id), 'add-submit', 'modal traps backwards Tab');
  await page.keyboard.press('Tab');
  assert.equal(await page.evaluate(() => document.activeElement.id), 'add-source', 'modal traps forwards Tab');
  await page.keyboard.press('Escape');
  assert.equal(await page.evaluate(() => document.activeElement.id), 'add-button', 'Escape restores opener focus');
  await page.locator('#tab-worktrees').focus();
  await page.keyboard.press('ArrowRight');
  assert.equal(await page.evaluate(() => document.activeElement.id), 'tab-branches');
  assert.equal(await page.locator('#tab-branches').getAttribute('aria-selected'), 'true');
  await page.keyboard.press('Tab');
  assert.equal(await page.evaluate(() => document.activeElement.id), 'work-table', 'active tab leads to its panel');
  assert.equal(await page.locator('#work-table').getAttribute('aria-labelledby'), 'tab-branches');
});

test('refresh keeps a keyboard focus destination when the selected worktree disappears', async t => {
  const {page, data} = await fixture(t);
  const summary = page.locator('#work-table .files summary').first();
  await summary.click();
  const key = await summary.evaluate(node => node.parentElement.dataset.worktree);
  const [repoKey, worktreePath] = JSON.parse(key);
  const repo = data.repositories.find(repo => (repo.id || repo.path) === repoKey);
  const worktree = repo.worktrees.find(worktree => worktree.path === worktreePath);
  Object.assign(worktree, {dirty: false, status: 'ok', files: [], staged: 0, unstaged: 0, untracked: 0, conflicts: 0});
  const response = page.waitForResponse('**/api/snapshot');
  await page.clock.fastForward(3000);
  await response;
  await until(() => page.locator('#refresh-button').isEnabled(), 'refresh completes');
  assert.equal(await page.evaluate(() => document.activeElement.id), 'work-table', 'disappearing focused row falls back to its panel');
});

test('empty/error states remain keyboard reachable and expose collector failure status', async t => {
  let fail = false;
  const {page, data} = await fixture(t, {snapshot: route => fail
    ? route.fulfill({status: 503, body: 'Fixture unavailable'})
    : route.fulfill({json: data})});
  for (const repo of data.repositories) Object.assign(repo, {
    status: 'error', history: null, worktrees: [], branches: [], stashes: [],
    source_status: {history: 'error', worktrees: 'error', branches: 'error', stashes: 'error'}
  });
  const response = page.waitForResponse('**/api/snapshot');
  await page.clock.fastForward(3000);
  await response;
  await until(() => page.locator('#refresh-button').isEnabled(), 'empty state refresh completes');
  assert.match(await page.locator('#work-table').textContent(), /Observation unavailable/);
  await page.locator('#tab-worktrees').focus();
  await page.keyboard.press('Tab');
  assert.equal(await page.evaluate(() => document.activeElement.id), 'work-table');
  fail = true;
  const failed = page.waitForResponse('**/api/snapshot');
  await page.locator('#refresh-button').click();
  await failed;
  await until(() => page.locator('#connection-banner').isVisible(), 'failure banner appears');
  assert.equal(await page.locator('#connection-banner').getAttribute('role'), 'status');
  assert.match(await page.locator('#connection-banner').textContent(), /Showing the last available observation/);
});

test('decorative graphics use CSS fallback for software or unavailable WebGL', async t => {
  for (const graphics of ['software', 'unavailable']) {
    const {page} = await fixture(t, {graphics, reducedMotion: 'no-preference'});
    await page.clock.fastForward(1000);
    assert.equal(await page.locator('#topo-canvas').isVisible(), false, graphics + ' renderer uses CSS fallback');
    assert.equal(await page.evaluate(() => window.decorativeDraws), 0, 'fallback performs no decorative drawing');
    assert.notEqual(await page.locator('#ambient').evaluate(node => getComputedStyle(node).backgroundImage), 'none');
  }
});

test('capable graphics honor reduced motion and pause while hidden', async t => {
  // Use native animation frames here: emulated media events and virtual clocks
  // otherwise race differently across browser engines.
  const {page} = await fixture(t, {graphics: 'hardware', reducedMotion: 'no-preference', nativeClock: true});
  await until(() => page.evaluate(() => window.decorativeAnimatedDraws > 1), 'motion remains enabled for capable contexts');
  await page.evaluate(() => {
    Object.defineProperty(document, 'hidden', {configurable: true, get: () => true});
    document.dispatchEvent(new Event('visibilitychange'));
  });
  const hidden = await page.evaluate(() => window.decorativeDraws);
  await page.waitForTimeout(200);
  assert.equal(await page.evaluate(() => window.decorativeDraws), hidden, 'hidden tab does not draw');
  await page.evaluate(() => {
    Object.defineProperty(document, 'hidden', {configurable: true, get: () => false});
    document.dispatchEvent(new Event('visibilitychange'));
  });
  await until(() => page.evaluate(count => window.decorativeDraws > count, hidden), 'visible tab resumes drawing');
  await page.emulateMedia({reducedMotion: 'reduce'});
  // Existing MediaQueryList objects update asynchronously; Chromium's media
  // emulation may update matches without dispatching a change event.
  await until(() => page.evaluate(() => window.motionQueries[0].matches), 'browser applies reduced motion to the app subscription');
  await page.waitForTimeout(100);
  const reduced = await page.evaluate(() => window.decorativeAnimatedDraws);
  await page.waitForTimeout(200);
  // A late media-change event may repaint the same static frame; it must never
  // advance the animation's time uniform while reduced motion is selected.
  assert.equal(await page.evaluate(() => window.decorativeAnimatedDraws), reduced, 'reduced motion stops animation');
});

test('automated WCAG A/AA checks cover desktop, mobile and add dialog', {skip: !axe}, async t => {
  const {page} = await fixture(t);
  await page.addScriptTag({content: axe.source});
  for (const state of ['desktop', 'mobile', 'dialog']) {
    if (state === 'mobile') await page.setViewportSize({width: 390, height: 844});
    if (state === 'dialog') await page.locator('#add-button').click();
    const result = await page.evaluate(async () => (await axe.run(document, {
      runOnly: {type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']}
    })).violations.map(violation => ({id: violation.id, impact: violation.impact, nodes: violation.nodes.map(node => node.target)})));
    assert.deepEqual(result, [], state + ' automated accessibility violations');
  }
});

test('intraday intervals distinguish repeated hours and resolve a 125k spike', async t => {
  const day = {date:'2026-11-01',start:1793509200,end:1793599200,commits:3,added:125001,deleted:0};
  const {page} = await fixture(t, {
    prepare(data) {
      const repo=data.repositories[0];data.repositories=[repo];repo.github_url='https://github.com/octocat/example';
      repo.history.daily=[day];repo.history.commits=3;
      repo.history.events=[{epoch:day.start+3660,sha:'a'.repeat(40),added:125000,deleted:0},
        {epoch:day.start+7260,sha:'b'.repeat(40),added:1,deleted:0},
        {epoch:day.start+7380,sha:'c'.repeat(40),added:0,deleted:0}];
    },
    pulls(route){
      const {sha}=route.request().postDataJSON();
      const pulls=sha.startsWith('a')?[{number:42,title:'Introduce feature'}, {number:43,title:'Backport'}]:[];
      return route.fulfill({json:{pulls,limited:false}});
    }
  });
  await page.setViewportSize({width:390,height:844});
  await page.selectOption('#interval-select','60');
  assert.equal(await page.locator('#weekly-data tbody tr').count(),25);
  const rows=page.locator('#weekly-data tbody tr');
  assert.match(await rows.nth(1).textContent(),/1:00\sAM CDT/);
  assert.match(await rows.nth(2).textContent(),/1:00\sAM CST/);
  const plot=page.locator('#frequency-chart [role=slider]');
  await plot.focus();await plot.press('ArrowRight');await plot.press('Enter');
  const dialog=page.locator('#point-dialog');
  assert.match(await dialog.locator('#point-summary').innerText(),/125,000/);
  await dialog.getByRole('link',{name:'#42 Introduce feature'}).waitFor();
  assert.equal(await dialog.getByRole('link',{name:'#42 Introduce feature'}).getAttribute('href'),'https://github.com/octocat/example/pull/42');
  assert.match(await dialog.innerText(),/1:01:00\sAM CDT/);
  await page.keyboard.press('Escape');
  await page.selectOption('#interval-select','15');
  assert.equal(await page.locator('#weekly-data tbody tr').count(),100);
  await page.locator('#frequency-chart').locator('..').locator('summary').click();
  await page.locator('#weekly-data tbody tr').nth(8).locator('button').click();
  await until(async()=> (await dialog.innerText()).includes('GitHub found no associated PR.'),'no-match state');
  assert.match(await dialog.locator('#point-summary').innerText(),/2 commits/);
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'mobile layout fits');
});

test('clicking a bar opens the single PR common to every contributor', async t=>{
  const requests=[];
  const {page}=await fixture(t,{
    prepare(data){
      const repo=data.repositories[0];data.repositories=[repo];repo.github_url='https://github.com/octocat/example';
      const day=repo.history.daily.at(-1);repo.history.daily=[day];
      day.commits=2;repo.history.commits=2;day.added=125000;day.deleted=0;
      repo.history.events=['d','e'].map(letter=>({sha:letter.repeat(40),epoch:day.start+10,added:62500,deleted:0}));
    },
    pulls(route){
      requests.push(route.request().postDataJSON().sha);
      return route.fulfill({json:{pulls:[{number:42,title:'One shared PR'}],limited:false}});
    }
  });
  await page.route('https://github.com/octocat/example/pull/42',route=>route.fulfill({body:'PR 42'}));
  await page.selectOption('#interval-select','day');
  await page.locator('#frequency-chart [role=slider]').click();
  await page.waitForURL('https://github.com/octocat/example/pull/42');
  assert.equal(new Set(requests).size,2);
});

function selectionFixture(data) {
  const repo=data.repositories[0];
  data.repositories=[repo];
  repo.github_url='https://github.com/octocat/example';
  repo.collected_at=data.generated_at='2026-11-05T18:30:00Z';
  repo.history.collected_at=data.generated_at;
  const start=Date.parse('2026-11-01T05:00:00Z')/1000;
  repo.history.daily=[
    {date:'2026-11-01',start,end:start+90000,commits:1,added:100,deleted:10},
    {date:'2026-11-02',start:start+90000,end:start+176400,commits:2,added:300,deleted:30},
    {date:'2026-11-03',start:start+176400,end:start+262800,commits:1,added:600,deleted:60},
    {date:'2026-11-04',start:start+262800,end:start+349200,commits:0,added:0,deleted:0}
  ];
  repo.history.events=[
    {sha:'a'.repeat(40),epoch:start+3600,added:100,deleted:10,subject:'Baseline'},
    {sha:'b'.repeat(40),epoch:start+93600,added:100,deleted:10,subject:'First PR commit'},
    {sha:'c'.repeat(40),epoch:start+94200,added:200,deleted:20,subject:'Second PR commit'},
    {sha:'d'.repeat(40),epoch:start+180000,added:600,deleted:60,subject:'Large change'}
  ];
  repo.history.commits=4;repo.history.total_added=1000;repo.history.total_deleted=100;
  repo.history.shallow=false;repo.history.truncated=false;
  repo.status='ok';repo.source_status={history:'ok'};
}

test('selection panel reconciles totals, zooms by keyboard and compares preceding duration',async t=>{
  const {page}=await fixture(t,{prepare:selectionFixture,pulls:route=>route.fulfill({json:{pulls:[],limited:false}})});
  await page.selectOption('#interval-select','day');
  assert.match(await page.locator('#selection-totals').textContent(),/1,000/);
  const plot=page.locator('#frequency-chart [role=slider]');
  await plot.focus();await plot.press('Home');await plot.press('ArrowRight');
  await plot.press('Shift+ArrowRight');await plot.press('Enter');
  assert.equal(await page.locator('#reset-zoom').isVisible(),true);
  assert.equal(await page.locator('#point-dialog').isVisible(),false);
  assert.match(await page.locator('#selection-totals').textContent(),/900/);
  assert.match(await page.locator('#selection-coverage').textContent(),/4 commits|3 commits/);
  await page.getByRole('button',{name:'Reset zoom',exact:true}).click();
  assert.match(await page.locator('#selection-totals').textContent(),/1,000/);
  // Select one completed day with equal-duration preceding coverage.
  await page.locator('#frequency-chart').locator('..').locator('summary').click();
  await page.locator('#weekly-data tbody tr').nth(2).getByRole('button').click();
  await page.locator('#point-close').click();
  assert.match(await page.locator('#selection-comparison').textContent(),/600/);
  assert.match(await page.locator('#selection-comparison').textContent(),/300/);
  assert.match(await page.locator('#selection-comparison').textContent(),/100%/);
});

test('PR groups count shared and ambiguous commits once and preserve unknown lookup status',async t=>{
  const {page}=await fixture(t,{prepare:selectionFixture,pulls(route){
    const letter=route.request().postDataJSON().sha[0];
    if(letter==='a')return route.fulfill({status:503,json:{error:{message:'Rate limited'}}});
    const pulls=letter==='d'?[{number:2,title:'A'},{number:3,title:'B'}]:[{number:42,title:'Shared PR'}];
    return route.fulfill({json:{pulls,limited:false}});
  }});
  await page.getByRole('button',{name:'Group by PR',exact:true}).click();
  await until(async()=>!(await page.locator('#group-prs').isDisabled()),'PR grouping finishes');
  assert.match(await page.locator('#selection-pr-groups').textContent(),/Not looked up/);
  await page.locator('#group-prs').click();
  await until(async()=>!(await page.locator('#group-prs').isDisabled()),'remaining lookups finish');
  const groups=await page.locator('#selection-pr-groups').textContent();
  assert.match(groups,/Shared PR/);assert.match(groups,/30%/);
  assert.match(groups,/Multiple associated PRs/);assert.match(groups,/60%/);
  assert.match(groups,/Lookup unavailable/);assert.match(groups,/10%/);
  await page.selectOption('#share-metric','deleted');
  assert.match(await page.locator('#selection-pr-groups').textContent(),/30%/);
});

test('mouse drag zooms both charts and refresh preserves the selected range',async t=>{
  const {page}=await fixture(t,{prepare:selectionFixture});
  await page.selectOption('#interval-select','day');
  const svg=page.locator('#frequency-chart svg'),box=await svg.boundingBox();
  const originX=box.x+box.width*(52+651/4*1.5)/720;
  const endX=box.x+box.width*(52+651/4*2.5)/720;
  const y=box.y+box.height/2;
  await page.mouse.move(originX,y);await page.mouse.down();
  await page.mouse.move(endX,y,{steps:8});await page.mouse.up();
  assert.equal(await page.locator('#point-dialog').isVisible(),false);
  assert.match(await page.locator('#selection-totals').textContent(),/900/);
  assert.equal(await page.locator('#commits-chart [role=slider]').getAttribute('aria-label'),'Hourly commit inspection');
  const before=await page.locator('#selection-period').textContent();
  const response=page.waitForResponse('**/api/snapshot');await page.clock.fastForward(3000);await response;
  assert.equal(await page.locator('#selection-period').textContent(),before);
  await page.setViewportSize({width:390,height:844});
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'selection panel fits mobile');
});

test('baselines expose zero activity, partial history and missing event detail',async t=>{
  const {page,data}=await fixture(t,{prepare:selectionFixture,pulls:route=>route.fulfill({json:{pulls:[],limited:false}})});
  await page.selectOption('#interval-select','day');
  await page.locator('#frequency-chart').locator('..').locator('summary').click();
  await page.locator('#weekly-data tbody tr').nth(3).getByRole('button').click();
  await page.locator('#point-close').click();
  assert.match(await page.locator('#selection-comparison').textContent(),/decreased 100%/);
  data.repositories[0].history.truncated=true;
  await page.getByRole('button',{name:'Refresh view'}).click();
  assert.match(await page.locator('#selection-comparison').textContent(),/complete preceding period is unavailable/);
  assert.match(await page.locator('#selection-coverage').textContent(),/Partial/);
  delete data.repositories[0].history.events;
  await page.getByRole('button',{name:'Refresh view'}).click();
  assert.equal(await page.locator('#selection-totals').textContent(),'Commit details unavailable');
  assert.equal(await page.locator('#group-prs').isDisabled(),true);
});

test('PR batches are bounded, cached, and never included in exported snapshots',async t=>{
  let calls=0;
  const {page}=await fixture(t,{prepare(data){
    selectionFixture(data);
    const repo=data.repositories[0],start=repo.history.daily[1].start;
    repo.history.events=Array.from({length:22},(_,i)=>({sha:i.toString(16).padStart(40,'0'),epoch:start+i,added:1,deleted:0,subject:'Change '+i}));
    repo.history.commits=22;repo.history.total_added=22;
  },pulls(route){calls++;return route.fulfill({json:{pulls:[{number:42,title:'Grouped change'}],limited:false}});}});
  await page.locator('#group-prs').click();
  await until(async()=>!(await page.locator('#group-prs').isDisabled()),'first batch completes');
  assert.equal(calls,20);
  assert.match(await page.locator('#selection-pr-status').textContent(),/20 \/ 22/);
  await page.locator('#group-prs').click();
  await until(async()=> (await page.locator('#selection-pr-status').textContent()).includes('22 / 22'),'second batch completes');
  assert.equal(calls,22);
  assert.match(await page.locator('#selection-pr-groups').textContent(),/100%/);
  // Changing interval resets the grouping display but reuses scoped in-memory results.
  await page.selectOption('#interval-select','day');
  await page.locator('#group-prs').click();
  await until(async()=>!(await page.locator('#group-prs').isDisabled()),'cached batch completes');
  assert.equal(calls,22);
  assert.equal(await page.evaluate(()=>JSON.stringify(data).includes('Grouped change')),false);
});

test('late PR lookups cannot restore results from an earlier repository selection',async t=>{
  let release,arrived;
  const incoming=new Promise(resolve=>arrived=resolve);
  const {page}=await fixture(t,{prepare(data){
    selectionFixture(data);
    const other=JSON.parse(JSON.stringify(data.repositories[0]));
    other.id='another';other.name='Another';other.path='/another';other.github_url='https://github.com/octocat/another';
    data.repositories.push(other);
  },async pulls(route){
    arrived();
    await new Promise(resolve=>release=resolve);
    await route.fulfill({json:{pulls:[{number:42,title:'Old private PR title'}],limited:false}}).catch(()=>{});
  }});
  await page.selectOption('#repo-select','/demo/frontend');
  await page.locator('#group-prs').click();await incoming;
  await page.selectOption('#repo-select','/another');release();
  await page.waitForTimeout(150);
  assert.equal(await page.locator('#selection-pr-groups').textContent(),'');
  assert.match(await page.locator('#selection-pr-status').textContent(),/0 \/ 4/);
});

test('touch drag selects a range on a narrow screen', {skip:engine!=='chromium'}, async t=>{
  const {page}=await fixture(t,{prepare:selectionFixture,touch:true});
  await page.setViewportSize({width:390,height:844});
  await page.selectOption('#interval-select','day');
  const plot=page.locator('#frequency-chart [role=slider]');
  await plot.scrollIntoViewIfNeeded();
  const svg=await page.locator('#frequency-chart svg').boundingBox();
  const x1=svg.x+svg.width*(52+651/4*1.5)/720, x2=svg.x+svg.width*(52+651/4*2.5)/720,y=svg.y+svg.height/2;
  const client=await page.context().newCDPSession(page);
  await client.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:x1,y}]});
  for(let i=1;i<=8;i++)await client.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:x1+(x2-x1)*i/8,y}]});
  await client.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
  assert.equal(await page.locator('#reset-zoom').isVisible(),true);
  assert.match(await page.locator('#selection-totals').textContent(),/900/);
  assert.equal(await page.locator('#point-dialog').isVisible(),false);
  await client.detach();
});

test('static selections zoom without network lookups and show missing comparison coverage',async t=>{
  const {page}=await fixture(t,{prepare(data){selectionFixture(data);data.live=false;}});
  await page.selectOption('#interval-select','day');
  assert.equal(await page.locator('#group-prs').isDisabled(),true);
  const plot=page.locator('#frequency-chart [role=slider]');
  await plot.focus();await plot.press('Home');await plot.press('Shift+ArrowRight');await plot.press('Enter');
  assert.match(await page.locator('#selection-totals').textContent(),/400/);
  assert.match(await page.locator('#selection-comparison').textContent(),/preceding period is unavailable/);
  assert.match(await page.locator('#selection-pr-note').textContent(),/Live PR grouping requires/);
  assert.equal(await page.locator('#reset-zoom').isVisible(),true);
});

test('a zero preceding period keeps actual counts and omits an infinite percentage',async t=>{
  const {page}=await fixture(t,{prepare(data){
    selectionFixture(data);
    const repo=data.repositories[0];
    repo.history.events=repo.history.events.filter(e=>e.sha[0]!=='a');
    Object.assign(repo.history.daily[0],{commits:0,added:0,deleted:0});
  },pulls:route=>route.fulfill({json:{pulls:[],limited:false}})});
  await page.selectOption('#interval-select','day');
  await page.locator('#frequency-chart').locator('..').locator('summary').click();
  await page.locator('#weekly-data tbody tr').nth(1).getByRole('button').click();
  await page.locator('#point-close').click();
  const text=await page.locator('#selection-comparison').textContent();
  assert.match(text,/300/);assert.match(text,/previous period has zero added lines/);
  assert.doesNotMatch(text,/Infinity|NaN/);
});
