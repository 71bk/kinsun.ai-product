// Real form login against local production BFF/Core. No route mocks or cookie injection.
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..');
const fixture = JSON.parse(fs.readFileSync(path.join(__dirname, '.env.previous-record-real-auth'), 'utf8'));
const base = 'http://localhost:3000';
const mode = process.argv[2] || 'read';
const note = 'Synthetic handover fixture 20260914: completed a planned activity. Human-authored test source, not live care data.';
let stage = 'launch';
let browser;
const evidence = {mode, checks: [], screenshots: []};
const check = (name, details = {}) => evidence.checks.push({name, ...details});
async function login(who) {
  stage = 'login-' + who;
  const context = await browser.newContext({viewport: {width:1440,height:1000}});
  await context.addCookies([{name:'kinsun_ui_locale',value:'en',url:base}]);
  const page = await context.newPage();
  await page.goto(base + '/staff/sign-in');
  await page.locator('input[name="email"]').fill(fixture.accounts[who].email);
  await page.locator('input[name="password"]').fill(fixture.accounts[who].password);
  await page.getByRole('button',{name:'登入 / Sign in',exact:true}).click();
  stage = 'login-redirect-' + who;
  await page.waitForURL(url => !url.pathname.includes('sign-in'), {timeout:30000});
  const me = await get(page, '/api/v1/me');
  assert.equal(me.status, 200);
  assert.equal(me.body.data.actor_id, fixture.ids[who]);
  check(who + '-real-principal', {actor: me.body.data.actor_id});
  return page;
}
async function get(page, apiPath) {
  return page.evaluate(async apiPath => {
    const response=await fetch('/backend/core'+apiPath,{cache:'no-store'});
    return {status:response.status,cache:response.headers.get('cache-control'),body:await response.json()};
  },apiPath);
}
const history = key => '/api/v1/home-care/assignments/'+fixture.ids[key]+'/previous-service-record';
async function cards(page) {
  const response = page.waitForResponse(r=>r.url().includes('/backend/core/api/v1/home-care/assignments?'));
  await page.goto(base+'/staff/assignments');
  const list = await (await response).json();
  assert.ok(Array.isArray(list.data?.items));
  await page.getByRole('article').first().waitFor();
  assert.equal(await page.getByRole('article').count(),list.data.items.length);
  return key => {
    const index=list.data.items.findIndex(row=>row.assignment_id===fixture.ids[key]);
    assert.ok(index>=0,'Expected owned assignment');
    return page.getByRole('article').nth(index);
  };
}
async function screenshot(page, name) {
  const geometry=await page.evaluate(()=>({inner:innerWidth,client:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth}));
  assert.equal(geometry.scroll,geometry.client);
  const filename='previous-real-'+name+'.png';
  await page.screenshot({path:path.join(__dirname,filename),fullPage:true});
  evidence.screenshots.push({filename,geometry});
}
(async()=>{
  try {
    assert.ok(['read','write-expiry','expiry','writer-expiry'].includes(mode));
    assert.ok(!fixture.retired && fixture.accounts, 'Campaign already retired');
    browser=await chromium.launch({channel:'chrome',headless:true});
    if(mode==='read') {
      const writer=await login('writer');
      stage='writer-source-denied';
      assert.equal((await get(writer,history('source'))).status,404);
      const writerCard=await cards(writer);
      await writerCard('writer_current').getByRole('button',{name:'View previous service record',exact:true}).click();
      await writer.getByText(note,{exact:true}).waitFor();
      await screenshot(writer,'writer');
      check('writer-current-allowed-historical-direct-denied');
      await writer.context().close();
      const reader=await login('reader');
      stage='reader-negative-gates';
      const denied=[];
      for(const key of ['source','no_history','writer_current','foreign_assignment']) {
        const response=await get(reader,history(key));
        console.log(JSON.stringify({negativeCase:key,status:response.status,errorKeys:Object.keys(response.body.error || {}),code:response.body.error?.code}));
        assert.equal(response.status,404,key);
        denied.push({key,status:response.status,error:{code:response.body.error?.code,message:response.body.error?.message}});
      }
      const absent=await get(reader,'/api/v1/home-care/assignments/00000000-0000-4000-8000-000000000099/previous-service-record');
      assert.equal(absent.status,404);
      for(const response of denied) assert.deepEqual(response.error,{code:absent.body.error?.code,message:absent.body.error?.message});
      check('four-denials-match-missing-resource',{statuses:denied.map(({key,status})=>({key,status}))});
      stage='reader-cross-worker-history';
      const source=await get(reader,history('current'));
      assert.equal(source.status,200);
      assert.ok(source.cache.includes('no-store'));
      assert.equal(source.body.data.record.service_record_id,fixture.ids.source_note);
      assert.equal(source.body.data.record.content,note);
      assert.equal(source.body.data.record.version,1);
      assert.equal(source.body.data.record.service_timezone,'Asia/Taipei');
      assert.equal('worker_id' in source.body.data.record,false);
      check('cross-worker-history',{source:fixture.ids.source_note,cache:source.cache});
      const card=await cards(reader);
      assert.equal(await card('no_history').getByRole('button',{name:'View previous service record',exact:true}).count(),0);
      await card('current').getByRole('button',{name:'View previous service record',exact:true}).click();
      await reader.getByText(note,{exact:true}).waitFor();
      await screenshot(reader,'reader-desktop');
      await reader.setViewportSize({width:390,height:844});
      await screenshot(reader,'reader-mobile');
      await card('current').getByRole('button',{name:'Hide previous service record',exact:true}).click();
      assert.equal(await reader.getByText(note,{exact:true}).count(),0);
      check('real-history-ui-and-close-no-scope-hidden');
    } else {
      const reader=await login(mode === 'writer-expiry' ? 'writer' : 'reader');
      let card=await cards(reader);
      if(mode === 'write-expiry') {
      stage='manual-record-completion';
      await card('current').getByRole('button',{name:'Open service record',exact:true}).click();
      await card('current').getByRole('textbox').fill('Synthetic live browser record 20260914: reviewed the previous handover and completed this test visit.');
      await card('current').getByRole('checkbox').check();
      await card('current').getByRole('button',{name:'Review and submit',exact:true}).click();
      await screenshot(reader,'confirmation');
      const submitted=reader.waitForResponse(r=>r.request().method()==='POST' && r.url().includes(fixture.ids.current));
      await reader.getByRole('dialog').getByRole('button',{name:'Confirm submission and complete visit',exact:true}).click();
      const response=await submitted;
      assert.equal(response.status(),201);
      await reader.getByText('Service record submitted and visit completed.',{exact:true}).waitFor();
      await screenshot(reader,'completed');
      assert.equal((await get(reader,history('current'))).status,404);
      check('real-ui-manual-record-and-completion',{status:response.status(),closedHistoryStatus:404});
      } else {
        assert.equal((await get(reader,history('current'))).status,404);
        await screenshot(reader,'completed-reload');
        check(mode === 'writer-expiry' ? 'other-worker-visit-remains-inaccessible' : 'completed-visit-remains-inaccessible-after-reload',{status:404});
      }
      stage='expiry-open';
      card=await cards(reader);
      const expiryKey = mode === 'writer-expiry' ? 'writer_current' : 'expiry';
      await card(expiryKey).getByRole('button',{name:'View previous service record',exact:true}).click();
      await reader.getByText(note,{exact:true}).waitFor();
      await screenshot(reader,'before-expiry');
      console.log(JSON.stringify({checkpoint:mode === 'writer-expiry' ? 'READY_FOR_WRITER_RETIRE' : 'READY_FOR_READER_EXPIRY'}));
      stage='expiry-clears-ui';
      await reader.getByText('Content is unavailable',{exact:true}).waitFor({timeout:600000});
      assert.equal(await reader.getByText(note,{exact:true}).count(),0);
      assert.equal(await reader.getByRole('article').count(),0);
      await screenshot(reader,'after-expiry');
      const denied=await get(reader,history(expiryKey));
      assert.ok([401,403,404].includes(denied.status));
      check('membership-expiry-poll-clears-history-and-cards',{status:denied.status});
    }
    fs.writeFileSync(path.join(__dirname,'previous-real-'+mode+'-evidence.json'),JSON.stringify(evidence,null,2));
    console.log(JSON.stringify({result:'passed',...evidence}));
  } catch(error) {
    // Never log Playwright's call history; it may contain credential field values.
    console.log(JSON.stringify({result:'failed',stage,errorType:error.name}));
    process.exitCode=1;
  } finally { if(browser) await browser.close(); }
})();
