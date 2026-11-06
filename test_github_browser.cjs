// Local synthetic browser coverage; no provider authentication or external calls.
// Run: node test_github_browser.cjs with an existing Playwright installation.
// Optional: PLAYWRIGHT_MODULE, BROWSER_ENGINE, BROWSER_EXECUTABLE, AXE_CORE_MODULE,
// UI_SCREENSHOT_DIR. Missing optional axe-core is explicitly skipped.
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {test, before, after} = require('node:test');
const playwright = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const engine = process.env.BROWSER_ENGINE || 'chromium';
assert.ok(['chromium', 'firefox', 'webkit'].includes(engine));
let axe, browser;
try { axe = require(process.env.AXE_CORE_MODULE || 'axe-core'); } catch (error) {
  if (process.env.AXE_CORE_MODULE) throw error;
}
before(async () => {
  const executable = process.env.BROWSER_EXECUTABLE || (engine === 'chromium' && process.env.CHROMIUM_EXECUTABLE);
  browser = await playwright[engine].launch({headless: true, ...(executable ? {executablePath: executable} : {})});
});
after(async () => { if (browser) await browser.close(); });
const origin = 'http://127.0.0.1:18765';
const auth = (status, extra = {}) => ({status, configured: true, session_only: true, generation: 1, github_session_id: 'fixture-session-a',
  user: status === 'connected' ? {id: 17, login: 'local-fixture'} : null, user_code: null,
  verification_uri: null, installation_url: 'https://github.com/apps/fixture-app/installations/new',
  expires_in: null, message: '', ...extra});
const repositories = [
  {id: 11, name: 'alpha', full_name: 'fixture/alpha', private: false, html_url: 'https://github.com/fixture/alpha'},
  {id: 12, name: 'beta', full_name: 'fixture/beta', private: true, html_url: 'https://github.com/fixture/beta'},
  {id: 13, name: 'gamma', full_name: 'fixture/gamma', private: false, html_url: 'https://github.com/fixture/gamma', archived: true},
];
async function until(check, message) {
  for (let i = 0; i < 150; i++) {
    if (await check()) return;
    await new Promise(resolve => setTimeout(resolve, 20));
  }
  assert.fail(message);
}
async function fixture(t, options = {}) {
  const context = await browser.newContext({viewport: {width: 1440, height: 1000}, reducedMotion: 'reduce'});
  t.after(() => context.close());
  const page = await context.newPage();
  page.setDefaultTimeout(10000);
  // Graphics have their own browser suite. Keep auth fixtures deterministic.
  await page.addInitScript(() => {
    const original = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function(type, ...args) {
      return this.id === 'topo-canvas' ? null : original.call(this, type, ...args);
    };
  });
  const errors = [], warnings = [], calls = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => { if (['warning', 'error'].includes(message.type())) warnings.push(message.text()); });
  t.after(() => assert.deepEqual(errors, [], 'no application errors'));
  t.after(() => assert.deepEqual(warnings.filter(message => !/Failed to load resource.*(?:409|503)/.test(message)), [], 'no unexpected console warnings'));
  const data = JSON.parse(fs.readFileSync(path.join(__dirname, 'demo.json'), 'utf8'));
  Object.assign(data, {live: !options.static, repository_management: !options.static, collection_running: false, github_session_id: 'fixture-session-a', github_generation: 1});
  if (options.configureData) options.configureData(data);
  const state = {auth: options.auth || auth('disconnected'), repositories: structuredClone(repositories)};
  const html = fs.readFileSync(path.join(__dirname, 'dashboard.html'), 'utf8')
    .replace('__GIT_DASHBOARD_DATA__', JSON.stringify(data).replaceAll('<', '\\u003c'));
  await page.clock.install();
  await page.route('**/*', async route => {
    const request = route.request(), url = new URL(request.url());
    assert.equal(url.origin, origin, 'fixture never calls GitHub or another external service');
    if (url.pathname === '/') return route.fulfill({contentType: 'text/html', body: html});
    if (url.pathname === '/api/snapshot') return options.snapshot ? options.snapshot(route, state, data) : route.fulfill({json: data});
    if (url.pathname.startsWith('/api/github/')) {
      const action = url.pathname.split('/').at(-1);
      calls.push({action, method: request.method(), body: request.postDataJSON()});
      if (options.handlers?.[action]) return options.handlers[action](route, state, calls);
      if (action === 'status') return route.fulfill({json: state.auth});
      if (action === 'start') state.auth = auth('pending', {generation: state.auth.generation + 1});
      if (action === 'cancel' || action === 'disconnect') state.auth = auth('disconnected', {generation: state.auth.generation + 1});
      if (action === 'repositories') return route.fulfill({json: {repositories: state.repositories, truncated: false, message: ''}});
      if (action === 'import') return route.fulfill({json: {imported: [], already_configured: [], failed: []}});
      return route.fulfill({json: state.auth});
    }
    assert.fail('Unexpected fixture route: ' + url.pathname);
  });
  await page.goto(origin);
  return {page, state, data, calls};
}
async function open(page) {
  await page.locator('#github-button').click();
  await until(() => page.locator('#github-dialog').evaluate(node => node.open), 'GitHub dialog opens');
}

test('device sign-in polls safe status and reaches a searchable repository picker', async t => {
  const {page, state, calls} = await fixture(t);
  await open(page);
  await page.locator('#github-start').click();
  await until(() => page.locator('#github-pending').isVisible(), 'pending instructions appear');
  assert.equal(await page.locator('#github-verify').isVisible(), false, 'no empty device link');
  state.auth = auth('pending', {user_code: 'ABCD-EFGH', verification_uri: 'https://github.com/login/device', expires_in: 600});
  await page.clock.fastForward(2000);
  await until(async () => (await page.locator('#github-code').textContent()) === 'ABCD-EFGH', 'device code arrives');
  assert.equal(await page.locator('#github-verify').getAttribute('href'), 'https://github.com/login/device');
  assert.match(await page.locator('#github-verify').getAttribute('rel'), /noopener/);
  state.auth = auth('connected');
  await page.clock.fastForward(2000);
  await until(async () => await page.locator('[data-github-id]').count() === 3, 'connected list loads');
  assert.match(await page.locator('#github-account').textContent(), /local-fixture/);
  assert.match(await page.locator('#github-repositories').textContent(), /Private/);
  assert.match(await page.locator('#github-session-note').textContent(), /saved repository choices remain/);
  assert.deepEqual(calls.filter(call => call.action === 'start').map(call => [call.method, call.body]), [['POST', {}]]);
});

test('search retains selection and partial import reports added, existing and failed choices', async t => {
  let submitted;
  const {page} = await fixture(t, {auth: auth('connected'), handlers: {
    import: async route => {
      submitted = route.request().postDataJSON();
      return route.fulfill({json: {imported: [{id: 11, name: 'alpha', url: repositories[0].html_url}],
        already_configured: [{id: 12, name: 'beta', url: repositories[1].html_url}],
        failed: [{id: 13, code: 'unavailable', message: 'Permission changed; try again.'}]}});
    },
  }});
  await open(page);
  await page.locator('[data-github-id="11"]').check();
  await page.locator('#github-search').fill('BETA');
  assert.equal(await page.locator('[data-github-id]').count(), 1);
  await page.locator('[data-github-id="12"]').check();
  await page.locator('#github-search').fill('');
  assert.equal(await page.locator('[data-github-id="11"]').isChecked(), true);
  await page.locator('[data-github-id="13"]').check();
  await page.locator('#github-import').click();
  await until(async () => /Permission changed/.test(await page.locator('#github-results').textContent()), 'partial result shown');
  assert.deepEqual(submitted, {repository_ids: [11, 12, 13]});
  assert.match(await page.locator('#github-results').textContent(), /1 added.*1 already.*1 failed/s);
  assert.equal(await page.locator('[data-github-id="11"]').isChecked(), false);
  assert.equal(await page.locator('[data-github-id="13"]').isChecked(), true, 'failed choice remains selected for retry');
  assert.equal(await page.locator('#github-dialog').evaluate(node => node.open), true, 'results stay reviewable');
});

test('unconfigured, denied and cancelled sign-in have useful recovery states', async t => {
  const {page, state, calls} = await fixture(t, {auth: auth('unconfigured', {configured: false, message: 'Publisher configuration is required.'})});
  await open(page);
  await until(() => page.locator('#github-setup').isVisible(), 'setup help appears');
  assert.equal(await page.locator('#github-setup').getAttribute('href'), '/github-setup');
  assert.equal(await page.locator('#github-start').isVisible(), false);
  await page.locator('#github-close').click();
  state.auth = auth('error', {message: 'The device code expired. Sign in again.'});
  await open(page);
  await until(async () => (await page.locator('#github-start').textContent()) === 'Retry sign-in', 'retry shown');
  assert.match(await page.locator('#github-error').textContent(), /expired/);
  await page.locator('#github-start').click();
  await page.locator('#github-cancel').click();
  await until(() => page.locator('#github-start').isVisible(), 'cancel returns to sign in');
  assert.equal(calls.filter(call => call.action === 'cancel').length, 1);
});

test('closed or disconnected dialogs ignore stale repository responses', async t => {
  let delayed;
  const {page, state} = await fixture(t, {auth: auth('connected'), handlers: {
    repositories: async route => { delayed = route; },
  }});
  await open(page);
  await until(() => Boolean(delayed), 'discovery started');
  await page.locator('#github-close').click();
  state.auth = auth('disconnected');
  await open(page);
  await page.locator('#github-start').waitFor({state: 'visible'});
  await delayed.fulfill({json: {repositories, truncated: false, message: ''}}).catch(() => {});
  assert.equal(await page.locator('[data-github-id]').count(), 0, 'old list cannot enter reopened form');
  await page.locator('#github-close').click();
  state.auth = auth('connected'); delayed = null;
  await open(page);
  await until(() => Boolean(delayed), 'second discovery started');
  await page.locator('#github-disconnect').click();
  await page.locator('#github-start').waitFor({state: 'visible'});
  await delayed.fulfill({json: {repositories, truncated: false, message: ''}}).catch(() => {});
  assert.equal(await page.locator('[data-github-id]').count(), 0, 'disconnect keeps private metadata cleared');
  assert.equal(await page.locator('#github-account').textContent(), '');
});

test('empty access, provider errors and unsafe links remain actionable and bounded', async t => {
  let attempts = 0;
  const {page} = await fixture(t, {auth: auth('connected'), handlers: {
    repositories: async route => ++attempts === 1
      ? route.fulfill({status: 503, json: {error: {code: 'provider_unavailable', message: 'GitHub is unavailable. Try again.'}}})
      : route.fulfill({json: {repositories: [], truncated: true, message: 'No accessible installations. Configure access, then refresh.'}}),
  }});
  await open(page);
  await until(async () => /unavailable/.test(await page.locator('#github-error').textContent()), 'discovery error appears');
  await page.locator('#github-refresh').click();
  await until(async () => /No accessible installations/.test(await page.locator('#github-count').textContent()), 'empty help appears');
  assert.equal(await page.locator('#github-access').getAttribute('href'), 'https://github.com/apps/fixture-app/installations/new');
  assert.equal(await page.locator('#github-import').isDisabled(), true);
  await page.locator('#github-close').click();
  const second = await fixture(t, {auth: auth('pending', {user_code: 'ABCD-EFGH', verification_uri: 'https://evil.test/login/device', installation_url: 'javascript:alert(1)'})});
  await open(second.page);
  await until(() => second.page.locator('#github-pending').isVisible(), 'pending state');
  assert.equal(await second.page.locator('#github-verify').isVisible(), false, 'only exact GitHub verification URI is linked');
  assert.equal(await second.page.locator('#github-access').getAttribute('href'), null);
});

test('keyboard, mobile layout and safe-field rendering keep auth state out of exports', async t => {
  const sentinel = 'SENSITIVE_FIXTURE_SENTINEL';
  const {page} = await fixture(t, {auth: auth('connected', {access_token: sentinel, refresh_token: sentinel, device_code: sentinel})});
  await open(page);
  await page.locator('[data-github-id="11"]').waitFor();
  await page.locator('#github-close').focus();
  await page.keyboard.press('Tab');
  assert.equal(await page.locator('#github-disconnect').evaluate(node => node === document.activeElement), true, 'Tab wraps within native dialog');
  await page.keyboard.press('Shift+Tab');
  assert.equal(await page.locator('#github-close').evaluate(node => node === document.activeElement), true);
  await page.keyboard.press('Escape');
  assert.equal(await page.locator('#github-dialog').evaluate(node => node.open), false);
  assert.equal(await page.locator('#github-button').evaluate(node => node === document.activeElement), true, 'dismiss returns focus');
  await open(page);
  for (const width of [1440, 390]) {
    await page.setViewportSize({width, height: width === 390 ? 844 : 1000});
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, 'no page overflow at ' + width);
    assert.equal(await page.locator('#github-dialog').evaluate(node => node.scrollWidth <= node.clientWidth), true, 'no dialog overflow at ' + width);
    if (axe) {
      await page.evaluate(axe.source);
      const result = await page.evaluate(() => axe.run(document.querySelector('#github-dialog'), {runOnly: {type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa']}}));
      assert.deepEqual(result.violations.map(v => ({id: v.id, nodes: v.nodes.map(n => n.target)})), [], 'dialog axe violations at ' + width);
    }
    if (process.env.UI_SCREENSHOT_DIR) {
      fs.mkdirSync(process.env.UI_SCREENSHOT_DIR, {recursive: true});
      await page.screenshot({path: path.join(process.env.UI_SCREENSHOT_DIR, 'github-picker-' + width + '.png')});
    }
  }
  assert.equal((await page.content()).includes(sentinel), false, 'unknown sensitive fields never enter DOM');
  assert.equal(await page.evaluate(() => localStorage.length + sessionStorage.length), 0, 'credentials never stored in browser storage');
  await page.locator('#github-close').click();
  const downloadEvent = page.waitForEvent('download');
  await page.locator('#export-button').click();
  const download = await downloadEvent;
  const exported = fs.readFileSync(await download.path(), 'utf8');
  assert.equal(exported.includes(sentinel), false, 'export contains only observation snapshot');
  assert.equal(exported.includes('user_code'), false);
  if (!axe) t.diagnostic('Optional axe-core unavailable; native keyboard/layout assertions ran.');
});

test('static demo never advertises live authentication', async t => {
  const {page, calls} = await fixture(t, {static: true});
  assert.equal(await page.locator('#github-button').isVisible(), false);
  assert.equal(await page.locator('#github-dialog').evaluate(node => node.open), false);
  assert.equal(calls.length, 0);
});

test('disconnect rejects stale private snapshots and a verified server restart resets the generation', async t => {
  const {page, state, data, calls} = await fixture(t, {auth: auth('connected'), configureData: data => {
    const repo = data.repositories[0];
    Object.assign(repo, {source_kind: 'github', private: true, name: 'Private fixture', path: 'https://github.com/fixture/private'});
    repo.history.recent[0].subject = 'PRIVATE_HISTORY_SENTINEL';
  }});
  await page.locator('#tab-recent').click();
  assert.match(await page.locator('#work-table').textContent(), /PRIVATE_HISTORY_SENTINEL/);
  await open(page);
  await page.locator('[data-github-id="11"]').waitFor();
  await page.locator('#github-disconnect').click();
  await page.locator('#github-start').waitFor({state: 'visible'});
  await page.locator('#github-close').click();
  await until(() => page.locator('#refresh-button').isEnabled(), 'disconnect refresh ends');
  assert.match(await page.locator('#repository-table').textContent(), /Sign in required/);
  assert.doesNotMatch(await page.locator('#work-table').textContent(), /PRIVATE_HISTORY_SENTINEL/, 'old generation cannot restore private history');
  assert.match(await page.locator('#repository-table').textContent(), /Not observed \(remote\)/);
  // A restarted backend starts a new epoch at generation zero. Verify status first.
  state.auth = auth('disconnected', {generation: 0, github_session_id: 'fixture-session-b'});
  data.github_session_id = 'fixture-session-b'; data.github_generation = 0;
  Object.assign(data.repositories[0], {history: null, status: 'auth_required', authentication_required: true});
  data.repositories[0].name = 'Restarted private fixture';
  const checks = calls.filter(call => call.action === 'status').length;
  await page.locator('#refresh-button').click();
  await until(async () => /Restarted private fixture/.test(await page.locator('#repository-table').textContent()), 'verified restart snapshot accepted');
  assert.equal(calls.filter(call => call.action === 'status').length, checks + 1);
  data.github_session_id = 'fixture-session-a'; data.github_generation = 1;
  data.repositories[0].name = 'STALE_SERVER_SENTINEL';
  await page.locator('#refresh-button').click();
  await until(() => page.locator('#refresh-button').isEnabled(), 'old server response checked');
  assert.doesNotMatch(await page.locator('#repository-table').textContent(), /STALE_SERVER_SENTINEL/);
});

test('large repository lists retain a 50-choice limit and reachable mobile actions', async t => {
  const {page, state} = await fixture(t, {auth: auth('connected')});
  state.repositories = Array.from({length: 500}, (_, i) => ({id: i + 100, full_name: 'fixture/repository-' + String(i).padStart(3, '0'), private: i % 2 === 0}));
  await page.setViewportSize({width: 390, height: 844});
  await open(page);
  await until(async () => await page.locator('[data-github-id]').count() === 500, 'large list loads');
  assert.equal(await page.locator('#github-import').isDisabled(), true);
  // Use the actual checkbox events; the list stays bounded and scrollable.
  for (let i = 0; i < 50; i++) await page.locator('[data-github-id="' + (i + 100) + '"]').check();
  await page.locator('[data-github-id="150"]').click();
  assert.equal(await page.locator('[data-github-id="150"]').isChecked(), false);
  assert.match(await page.locator('#github-error').textContent(), /up to 50/);
  assert.equal(await page.locator('#github-dialog').evaluate(node => node.scrollHeight > node.clientHeight), true, 'dialog can scroll on mobile');
  assert.equal(await page.locator('#github-repositories').evaluate(node => node.scrollHeight > node.clientHeight), true, '500-row list has its own scroll region');
  for (const id of ['github-import', 'github-close']) {
    await page.locator('#' + id).scrollIntoViewIfNeeded();
    const box = await page.locator('#' + id).boundingBox();
    assert.ok(box.x >= 0 && box.x + box.width <= 390 && box.y >= 0 && box.y + box.height <= 844, id + ' reachable within viewport');
    await page.locator('#' + id).focus();
    assert.equal(await page.locator('#' + id).evaluate(node => node === document.activeElement), true);
  }
  await page.locator('#github-close').click();
});

test('an import failure preserves choices and a late import cannot reset a reopened dialog', async t => {
  let delayed, attempts = 0;
  const {page} = await fixture(t, {auth: auth('connected'), handlers: {
    import: async route => {
      if (++attempts === 1) return route.fulfill({status: 409, json: {error: {code: 'configuration_changed', message: 'Configuration changed. Try again.'}}});
      delayed = route;
    },
  }});
  await open(page);
  await page.locator('[data-github-id="11"]').check();
  await page.locator('#github-import').click();
  await until(async () => /Configuration changed/.test(await page.locator('#github-error').textContent()), 'import error shown');
  assert.equal(await page.locator('[data-github-id="11"]').isChecked(), true);
  await page.locator('#github-import').click();
  await until(() => Boolean(delayed), 'second import sent');
  await page.locator('#github-close').click();
  assert.match(await page.locator('#repository-message').textContent(), /does not undo saved choices/);
  await open(page);
  await page.locator('#github-search').fill('beta');
  await page.locator('[data-github-id="12"]').check();
  await delayed.fulfill({json: {imported: [{id: 11, name: 'alpha'}], already_configured: [], failed: []}}).catch(() => {});
  assert.equal(await page.locator('#github-search').inputValue(), 'beta');
  assert.equal(await page.locator('[data-github-id="12"]').isChecked(), true);
  assert.doesNotMatch(await page.locator('#github-results').textContent(), /1 added/);
});

test('optional axe checks cover setup, sign-in, pending code and expired states', {skip: !axe && 'Optional axe-core is not installed'}, async t => {
  for (const status of [auth('unconfigured', {configured: false}), auth('disconnected'),
    auth('pending', {user_code: 'ABCD-EFGH', verification_uri: 'https://github.com/login/device'}),
    auth('error', {message: 'Authorization expired. Sign in again.'})]) {
    const {page} = await fixture(t, {auth: status});
    await page.setViewportSize({width: 390, height: 844});
    await open(page);
    const section = {unconfigured: 'unconfigured', disconnected: 'signin', pending: 'pending', error: 'signin'}[status.status];
    await page.locator('#github-' + section).waitFor({state: 'visible'});
    await page.evaluate(axe.source);
    const result = await page.evaluate(() => axe.run(document.querySelector('#github-dialog'), {runOnly: {type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa']}}));
    assert.deepEqual(result.violations.map(v => ({id: v.id, nodes: v.nodes.map(n => n.target)})), [], status.status + ' axe violations');
    await page.locator('#github-close').click();
    assert.equal(await page.locator('#github-button').evaluate(node => node === document.activeElement), true);
  }
});

test('a newer snapshot reconciles an open picker and rejects late discovery after another tab disconnects', async t => {
  let delayed, discoveries = 0;
  const {page, state, data} = await fixture(t, {auth: auth('connected'), configureData: data => { data.refresh_seconds = 5; }, handlers: {
    repositories: async route => {
      if (++discoveries === 1) return route.fulfill({json: {repositories, github_session_id: 'fixture-session-a', github_generation: 1}});
      delayed = route;
    },
  }});
  await open(page);
  await page.locator('[data-github-id="12"]').waitFor();
  await page.locator('#github-refresh').click();
  await until(() => Boolean(delayed), 'second discovery in flight');
  state.auth = auth('disconnected', {generation: 2}); data.github_generation = 2;
  await page.clock.fastForward(5000);
  await until(() => page.locator('#github-start').isVisible(), 'newer snapshot clears the other tab\'s disconnected picker');
  await delayed.fulfill({json: {repositories, github_session_id: 'fixture-session-a', github_generation: 1}}).catch(() => {});
  assert.equal(await page.locator('[data-github-id]').count(), 0);
  assert.equal(await page.locator('#github-account').textContent(), '');
});

test('a discovery response with a changed auth version is reconciled before rendering repository metadata', async t => {
  let delayed;
  const {page, state} = await fixture(t, {auth: auth('connected'), handlers: {
    repositories: async route => { delayed = route; },
  }});
  await open(page);
  await until(() => Boolean(delayed), 'discovery is pending');
  state.auth = auth('disconnected', {generation: 2});
  await delayed.fulfill({json: {repositories, github_session_id: 'fixture-session-a', github_generation: 2}});
  await until(() => page.locator('#github-start').isVisible(), 'changed response version requires current auth status');
  assert.equal(await page.locator('[data-github-id]').count(), 0);
});

test('a failed changed-session status check cannot keep old private observations visible', async t => {
  let checks = 0;
  const {page, data} = await fixture(t, {auth: auth('connected'), configureData: data => {
    data.refresh_seconds = 5;
    Object.assign(data.repositories[0], {source_kind: 'github', private: true});
    data.repositories[0].history.recent[0].subject = 'OLD_PRIVATE_HISTORY';
  }, handlers: {
    status: async (route, state) => ++checks === 1 ? route.fulfill({json: state.auth})
      : route.fulfill({status: 503, json: {error: {code: 'unavailable', message: 'Status unavailable.'}}}),
  }});
  await page.locator('#tab-recent').click();
  assert.match(await page.locator('#work-table').textContent(), /OLD_PRIVATE_HISTORY/);
  await open(page);
  await page.locator('[data-github-id="11"]').waitFor();
  data.github_generation = 2;
  Object.assign(data.repositories[0], {history: null, status: 'auth_required', authentication_required: true});
  await page.clock.fastForward(5000);
  await until(async () => /Could not verify/.test(await page.locator('#github-error').textContent()), 'changed-session check failed visibly');
  assert.equal(await page.locator('[data-github-id]').count(), 0);
  assert.doesNotMatch(await page.locator('#work-table').textContent(), /OLD_PRIVATE_HISTORY/, 'old private observations are removed before verification');
});
