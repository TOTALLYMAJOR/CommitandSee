// Synthetic loopback fixtures; no GitHub calls or repository writes.
'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {test,before,after}=require('node:test');
const playwright=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const engine=process.env.BROWSER_ENGINE||'chromium';
const origin='http://127.0.0.1:18765';
let browser;
before(async()=>{const executablePath=process.env.BROWSER_EXECUTABLE||(engine==='chromium'&&process.env.CHROMIUM_EXECUTABLE);browser=await playwright[engine].launch({headless:true,...(executablePath?{executablePath}:{})});});
after(async()=>{await browser?.close();});
const choices={sources:[{id:'branch:topic',label:'Branch topic',kind:'branch'},{id:'worktree:a',label:'Working files',kind:'worktree'},{id:'index:a',label:'Staged files',kind:'index'},{id:'stash:a',label:'Stash 0',kind:'stash'}],targets:[{id:'refs/heads/main',label:'main'},{id:'refs/remotes/origin/main',label:'origin/main (cached)'}],default_target:'refs/heads/main',warnings:['Only bounded local locations are inspected.']};
const report={source:{id:'branch:topic',label:'Branch topic',kind:'branch'},target:{id:'refs/heads/main',label:'main'},generated_at:'2026-11-09T18:00:00Z',summary:{files:4,present:1,remaining:1,partial:1,uncertain:1,no_matching_saved_version:1},files:[
  {path:'src/present.py',integration:'present',explanation:'The target contains the same file contents.',preservation:'matching_saved_version',saved_copies:['main']},
  {path:'src/remaining.py',integration:'remaining',explanation:'The target still contains the original lines.',preservation:'no_matching_saved_version',saved_copies:[]},
  {path:'src/partial.py',integration:'partial',explanation:'Some edits match, and some remain.',preservation:'unknown',saved_copies:[]},
  {path:'image.png',integration:'uncertain',explanation:'Binary content was not compared.',preservation:'unknown',saved_copies:[]}
],warnings:['Binary files remain uncertain.'],coverage:{files_checked:4,saved_locations_checked:8,saved_search_limited:true}};
function deferred(){let resolve;const promise=new Promise(done=>resolve=done);return {promise,resolve};}
async function fixture(t,options={}){
  const context=await browser.newContext({viewport:{width:1440,height:1000},reducedMotion:'reduce'});t.after(()=>context.close());
  const page=await context.newPage();page.setDefaultTimeout(10000);
  await page.addInitScript(()=>{const original=HTMLCanvasElement.prototype.getContext;HTMLCanvasElement.prototype.getContext=function(type,...args){return this.id==='topo-canvas'?null:original.call(this,type,...args);};});
  const errors=[],warnings=[],calls=[];
  page.on('pageerror',error=>errors.push(error.message));page.on('console',message=>{if(['warning','error'].includes(message.type()))warnings.push(message.text());});
  t.after(()=>assert.deepEqual(errors,[],'no page exceptions'));
  t.after(()=>assert.deepEqual(warnings.filter(message=>!/Failed to load resource.*(?:409|429|503)/.test(message)),[],'no unexpected console messages'));
  const data=JSON.parse(fs.readFileSync(path.join(__dirname,'demo.json'),'utf8'));
  Object.assign(data,{live:!options.static,demo:Boolean(options.demo),repository_management:!options.static,collection_running:false});
  data.repositories=data.repositories.slice(0,2);data.repositories.forEach((repo,index)=>{repo.id='local-'+index;repo.status='ok';repo.source_kind='local';});
  options.prepare?.(data);
  const html=fs.readFileSync(path.join(__dirname,'dashboard.html'),'utf8').replace('__GIT_DASHBOARD_DATA__',JSON.stringify(data).replaceAll('<','\\u003c'));
  await page.clock.install();
  await page.route('**/*',async route=>{
    const url=new URL(route.request().url());assert.equal(url.origin,origin,'no external services');
    if(url.pathname==='/')return route.fulfill({contentType:'text/html',body:html});
    if(url.pathname==='/api/snapshot')return route.fulfill({json:data});
    if(url.pathname==='/api/local-insights/options'||url.pathname==='/api/local-insights'){
      const body=route.request().postDataJSON();calls.push({endpoint:url.pathname,body});
      if(url.pathname.endsWith('/options'))return options.options?options.options(route,body):route.fulfill({json:choices});
      return options.scan?options.scan(route,body):route.fulfill({json:structuredClone(report)});
    }
    return route.fulfill({status:404,body:'Not found'});
  });
  await page.goto(origin);return {page,data,calls};
}
async function choose(page){await page.selectOption('#insights-repository','local-0');await page.locator('#insights-source option[value="branch:topic"]').waitFor({state:'attached'});await page.selectOption('#insights-source','branch:topic');}
async function scan(page){await choose(page);await page.clock.fastForward(200);await page.locator('#insights-results .insights-file').first().waitFor();}

test('mixed local insights display evidence, scope and exact saved-version limits',async t=>{
  const {page,calls}=await fixture(t);assert.equal(calls.length,0,'no automatic inspection');
  await scan(page);
  assert.deepEqual(calls.map(call=>call.body),[{repository:'local-0'},{repository:'local-0',source:'branch:topic',target:'refs/heads/main'}]);
  assert.match(await page.locator('#insights-results').textContent(),/1 present · 1 remaining · 1 partly present · 1 uncertain files/);
  assert.match(await page.locator('#insights-results').textContent(),/No match does not prove that the edits are unique/);
  assert.match(await page.locator('#insights-results').textContent(),/No identical saved version found/);
  assert.match(await page.locator('#insights-results').textContent(),/Saved locations checked: 8/);
  assert.match(await page.locator('#insights-results').textContent(),/Saved-copy search limited/);
  assert.match(await page.locator('#insights-results').textContent(),/Binary files remain uncertain/);
  assert.equal(await page.locator('#insights-source option').count(),5,'staged and working files are separate choices');
});

test('static reports, demo data and remote-only selections explain local requirement',async t=>{
  for(const options of [{static:true},{demo:true},{prepare:data=>data.repositories.forEach(repo=>repo.source_kind='github')}]){
    const {page,calls}=await fixture(t,options);assert.equal(await page.locator('#insights-form').isVisible(),false);assert.match(await page.locator('#insights-availability').textContent(),/local checkout|local repository/);assert.equal(calls.length,0);
  }
});

test('changing source or target updates the comparison without a page reload',async t=>{
  const {page,calls}=await fixture(t);await scan(page);
  await page.selectOption('#insights-source','index:a');assert.equal(await page.locator('#insights-results').textContent(),'');assert.equal(calls.length,2);
  await page.clock.fastForward(200);await page.locator('#insights-results .insights-file').first().waitFor();
  assert.equal(calls.at(-1).body.source,'index:a');
  await page.selectOption('#insights-target','refs/remotes/origin/main');assert.equal(await page.locator('#insights-results').textContent(),'');assert.equal(calls.length,3);
  await page.clock.fastForward(200);await page.locator('#insights-results .insights-file').first().waitFor();
  assert.equal(calls.at(-1).body.target,'refs/remotes/origin/main');assert.equal(calls.length,4);
});

test('switching local repository keeps compatible choices and automatically updates evidence',async t=>{
  const {page,calls}=await fixture(t);await scan(page);
  await page.selectOption('#insights-repository','local-1');
  await page.waitForFunction(()=>document.querySelector('#insights-status').textContent==='Updating comparison…');
  await page.clock.fastForward(200);await page.locator('#insights-results .insights-file').first().waitFor();
  assert.deepEqual(calls.at(-1).body,{repository:'local-1',source:'branch:topic',target:'refs/heads/main'});
});

test('overview repository filter loads matching inspection choices without reloading the page',async t=>{
  const {page,data,calls}=await fixture(t);
  await page.selectOption('#repo-select',data.repositories[1].path);
  await page.locator('#insights-source option[value="branch:topic"]').waitFor({state:'attached'});
  assert.equal(await page.locator('#insights-repository').inputValue(),'local-1');
  assert.deepEqual(calls.map(call=>call.body),[{repository:'local-1'}]);
  assert.match(await page.locator('#selection-note').textContent(),/^1 repository selected/);
});

test('overview repository switching preserves compatible comparison choices',async t=>{
  const {page,data,calls}=await fixture(t);await scan(page);
  await page.selectOption('#repo-select',data.repositories[1].path);
  await page.waitForFunction(()=>document.querySelector('#insights-status').textContent==='Updating comparison…');
  await page.clock.fastForward(200);await page.locator('#insights-results .insights-file').first().waitFor();
  assert.deepEqual(calls.at(-1).body,{repository:'local-1',source:'branch:topic',target:'refs/heads/main'});
});

test('busy previous inspection retries choices and stops retrying when selection changes',async t=>{
  let blocked=0;
  const {page,calls}=await fixture(t,{options:(route,body)=>body.repository==='local-0'&&++blocked<3?
    route.fulfill({status:429,json:{error:{code:'scan_busy',message:'Another local inspection is running.'}}}):route.fulfill({json:choices})});
  const first=page.waitForResponse(response=>response.status()===429);await page.selectOption('#insights-repository','local-0');await first;
  const second=page.waitForResponse(response=>response.status()===429);await page.clock.fastForward(2000);await second;
  await page.clock.fastForward(2000);await page.locator('#insights-source option[value="branch:topic"]').waitFor({state:'attached'});
  assert.equal(blocked,3);
  blocked=0;const response=page.waitForResponse(response=>response.status()===429);
  await page.locator('#insights-reload').click();await response;
  await page.selectOption('#insights-repository','local-1');await page.locator('#insights-source option[value="branch:topic"]').waitFor({state:'attached'});
  const count=calls.length;await page.clock.fastForward(10000);assert.equal(calls.length,count,'aborted retry cannot issue another old request');
});

test('rapid target changes debounce to the latest comparison',async t=>{
  const {page,calls}=await fixture(t);await scan(page);
  await page.selectOption('#insights-target','refs/remotes/origin/main');
  await page.selectOption('#insights-target','refs/heads/main');
  await page.clock.fastForward(200);await page.locator('#insights-results .insights-file').first().waitFor();
  assert.equal(calls.length,3);assert.equal(calls.at(-1).body.target,'refs/heads/main');
});

test('late options cannot replace choices for a newer repository selection',async t=>{
  const gate=deferred(),arrived=deferred();
  const {page}=await fixture(t,{options:async(route,body)=>{if(body.repository==='local-0'){arrived.resolve();await gate.promise;return route.fulfill({json:{...choices,sources:[{id:'obsolete',label:'OBSOLETE_CHOICE'}]}}).catch(()=>{});}return route.fulfill({json:choices});}});
  await page.selectOption('#insights-repository','local-0');await arrived.promise;
  await page.selectOption('#insights-repository','local-1');await page.locator('#insights-source option[value="branch:topic"]').waitFor({state:'attached'});gate.resolve();
  await page.waitForTimeout(30);assert.doesNotMatch(await page.locator('#insights-source').textContent(),/OBSOLETE/);assert.equal(await page.locator('#insights-repository').inputValue(),'local-1');
});

test('late scan cannot restore evidence after changing the source',async t=>{
  const gate=deferred(),arrived=deferred();
  const {page}=await fixture(t,{scan:async route=>{arrived.resolve();await gate.promise;return route.fulfill({json:report}).catch(()=>{});}});
  await choose(page);await page.clock.fastForward(200);await arrived.promise;
  await page.selectOption('#insights-source','stash:a');gate.resolve();await page.waitForTimeout(30);
  assert.equal(await page.locator('#insights-results').textContent(),'');assert.equal(await page.locator('#insights-source').inputValue(),'stash:a');assert.equal(await page.locator('#insights-scan').isEnabled(),true);
});

test('removed repository invalidates a pending scan and its evidence',async t=>{
  const gate=deferred(),arrived=deferred();
  const {page,data}=await fixture(t,{scan:async route=>{arrived.resolve();await gate.promise;return route.fulfill({json:report}).catch(()=>{});}});
  await choose(page);await page.clock.fastForward(200);await arrived.promise;
  data.repositories=data.repositories.slice(1);await page.locator('#refresh-button').click();await page.waitForFunction(()=>!document.querySelector('#insights-repository option[value="local-0"]'));
  gate.resolve();await page.waitForTimeout(30);assert.equal(await page.locator('#insights-results').textContent(),'');assert.equal(await page.locator('#insights-repository').inputValue(),'');
});

test('ordinary polling preserves choices, focus and dated results without new scans',async t=>{
  const {page,calls}=await fixture(t);await scan(page);await page.locator('#insights-source').focus();
  const refreshed=page.waitForResponse('**/api/snapshot');await page.clock.fastForward(30000);await refreshed;await page.waitForFunction(()=>!document.getElementById('refresh-button').disabled);
  assert.equal(await page.locator('#insights-source').inputValue(),'branch:topic');assert.equal(await page.locator('#insights-source').evaluate(node=>node===document.activeElement),true);assert.equal(await page.locator('#insights-results .insights-file').count(),4);assert.equal(calls.length,2);
});

test('same repository id with a changed local identity invalidates old results',async t=>{
  const {page,data,calls}=await fixture(t);await scan(page);
  data.repositories[0].common_dir='/different/checkout/.git';await page.locator('#refresh-button').click();await page.waitForFunction(()=>document.getElementById('insights-results').textContent==='');
  assert.equal(await page.locator('#insights-scan').isDisabled(),true);assert.equal(calls.length,2,'identity changes never trigger an implicit new inspection');
});

test('busy scan disables duplicate submission and reports a backend limit error',async t=>{
  const gate=deferred(),arrived=deferred();
  const {page,calls}=await fixture(t,{scan:async route=>{arrived.resolve();await gate.promise;return route.fulfill({status:503,json:{error:{code:'busy',message:'Another local inspection is running. Try again shortly.'}}});}});
  await choose(page);await page.clock.fastForward(200);await arrived.promise;
  assert.equal(await page.locator('#insights-scan').isDisabled(),true);await page.locator('#insights-scan').evaluate(node=>node.click());assert.equal(calls.length,2);
  gate.resolve();await page.waitForFunction(()=>document.getElementById('insights-error').textContent.includes('Another local inspection'));
  assert.equal(await page.locator('#insights-results').textContent(),'');assert.equal(await page.locator('#insights-scan').isEnabled(),true);
});

test('options failure is recoverable with Refresh choices',async t=>{
  let attempts=0;
  const {page}=await fixture(t,{options:route=>++attempts===1?route.fulfill({status:409,json:{error:{code:'changed',message:'Repository changed. Refresh choices.'}}}):route.fulfill({json:choices})});
  await page.selectOption('#insights-repository','local-0');await page.waitForFunction(()=>document.getElementById('insights-error').textContent.includes('Repository changed'));
  assert.equal(await page.locator('#insights-scan').isDisabled(),true);await page.locator('#insights-reload').click();await page.locator('#insights-source option[value="branch:topic"]').waitFor({state:'attached'});assert.equal(await page.locator('#insights-error').textContent(),'');
});

test('empty choices stay disabled and explain missing comparable history',async t=>{
  const {page}=await fixture(t,{options:route=>route.fulfill({json:{sources:[],targets:[],default_target:null,warnings:['No starting commit is available.']}})});
  await page.selectOption('#insights-repository','local-0');await page.waitForFunction(()=>document.getElementById('insights-status').textContent.includes('No comparable'));
  assert.equal(await page.locator('#insights-scan').isDisabled(),true);assert.match(await page.locator('#insights-option-warnings').textContent(),/No starting commit/);
});

test('untrusted paths are text, mobile fits, and inspection does not enter exported JSON',async t=>{
  const unsafe='<img src=x onerror="window.insightInjected=true">',result=structuredClone(report);result.files[1].path=unsafe;result.files[1].explanation='INSIGHT_EXPORT_SENTINEL';
  const {page}=await fixture(t,{scan:route=>route.fulfill({json:result})});await scan(page);
  assert.equal(await page.locator('#insights-results img').count(),0);assert.match(await page.locator('#insights-results').textContent(),/onerror/);assert.equal(await page.evaluate(()=>window.insightInjected),undefined);
  await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  await page.evaluate(()=>{const original=URL.createObjectURL;URL.createObjectURL=blob=>{window.lastExport=blob;return original(blob);};});
  await page.locator('#export-button').click();const exported=await page.evaluate(()=>window.lastExport.text());assert.doesNotMatch(exported,/INSIGHT_EXPORT_SENTINEL|insightInjected|saved_copies/);
  if(process.env.UI_SCREENSHOT_DIR){fs.mkdirSync(process.env.UI_SCREENSHOT_DIR,{recursive:true});await page.screenshot({path:path.join(process.env.UI_SCREENSHOT_DIR,'local-insights-mobile.png'),fullPage:true});await page.setViewportSize({width:1440,height:1000});await page.locator('#local-insights-panel').screenshot({path:path.join(process.env.UI_SCREENSHOT_DIR,'local-insights-desktop.png')});}
});
