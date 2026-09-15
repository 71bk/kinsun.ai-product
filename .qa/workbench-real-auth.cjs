// Real form login and real BFF/Core/DB; no response mocks or session injection.
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const folder = __dirname;
const fixture = JSON.parse(fs.readFileSync(path.join(folder, '.env.workbench-real-auth'), 'utf8'));
const base = 'http://localhost:3000';
const note = 'Synthetic workbench handover 20260915: human-authored planned activity, no live care data.';
const newNote = 'Synthetic real workbench record 20260915: read handover and follow-up tasks, completed this test visit.';
const evidence = {campaign:fixture.campaign, startedAt:new Date().toISOString(), checks:[], screenshots:[], errors:[]};
let browser, stage = 'launch';
const mode = process.argv[2] || 'flow';
const check = (name, details={}) => {evidence.checks.push({name,...details});console.log(JSON.stringify({stage:name,...details}));};
const visitPath = key => '/api/v1/home-care/assignments/'+fixture.ids[key];
const taskPath = key => '/api/v1/elders/'+fixture.ids.elder+'/care-actions?assignment_id='+fixture.ids[key]+'&status=OPEN&status=IN_PROGRESS&status=POSTPONED';
const workbench = key => base+'/staff/assignments/'+fixture.ids[key];
const delay = ms => new Promise(resolve=>setTimeout(resolve,ms));
async function get(page, apiPath) {
  return page.evaluate(async apiPath=>{
    const response=await fetch('/backend/core'+apiPath,{cache:'no-store'});
    return {status:response.status,cache:response.headers.get('cache-control'),body:await response.json()};
  },apiPath);
}
async function login(who) {
  stage='login-'+who;
  const context=await browser.newContext({viewport:{width:1440,height:1000}});
  await context.addCookies([{name:'kinsun_ui_locale',value:'en',url:base}]);
  const page=await context.newPage();
  page.on('pageerror',error=>evidence.errors.push({kind:'pageerror',name:error.name}));
  await page.goto(base+'/staff/sign-in');
  await page.locator('input[name="email"]').fill(fixture.accounts[who].email);
  await page.locator('input[name="password"]').fill(fixture.accounts[who].password);
  await page.getByRole('button',{name:'登入 / Sign in',exact:true}).click();
  await page.waitForURL(url=>!url.pathname.includes('sign-in'),{timeout:30000});
  const me=await get(page,'/api/v1/me');
  assert.equal(me.status,200);
  assert.equal(me.body.data.actor_id,fixture.ids[who]);
  check('real-login-'+who,{actorId:fixture.ids[who]});
  return page;
}
async function shot(page,label,fullPage=true) {
  const geometry=await page.evaluate(()=>({inner:innerWidth,client:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth}));
  assert.ok(geometry.scroll<=geometry.client,'Horizontal overflow');
  const filename='workbench-real-'+label+'.png';
  await page.screenshot({path:path.join(folder,filename),fullPage});
  evidence.screenshots.push({filename,geometry,viewport:page.viewportSize()});
}
async function openPanels(page,locale='en') {
  const text=(en,zh)=>locale==='en'?en:zh;
  await page.getByRole('button',{name:text('View previous service record','查看上次服務紀錄'),exact:true}).click();
  await page.getByText(note,{exact:true}).waitFor();
  await page.getByRole('button',{name:text('View follow-up tasks','查看待追蹤事項'),exact:true}).click();
  await page.getByRole('heading',{name:'Synthetic workbench OPEN',exact:true}).waitFor();
  for(const state of ['OPEN','IN_PROGRESS','POSTPONED'])
    assert.equal(await page.getByRole('heading',{name:'Synthetic workbench '+state,exact:true}).count(),1);
}
async function noPrivate(page) {
  assert.equal(await page.getByText(note,{exact:true}).count(),0);
  assert.equal(await page.getByRole('heading',{name:/Synthetic workbench (OPEN|IN_PROGRESS|POSTPONED)/}).count(),0);
  assert.equal(await page.locator('textarea').count(),0);
}
(async()=>{
  try {
    assert.ok(!fixture.retired && fixture.accounts,'Retired campaign');
    assert.ok(['flow','expiry'].includes(mode));
    browser=await chromium.launch({channel:'chrome',headless:true});
    if(mode==='flow') {
      const reader=await login('reader');
      stage='negative-gates';
      const missing=await get(reader,visitPath('current').replace(fixture.ids.current,'00000000-0000-4000-8000-000000000099'));
      assert.equal(missing.status,404);
      const denied=[];
      for(const key of ['source','writer_current','foreign_assignment']) {
        const result=await get(reader,visitPath(key));
        assert.equal(result.status,404,key);
        assert.equal(result.body.error.code,missing.body.error.code);
        assert.equal(result.body.error.message,missing.body.error.message);
        denied.push({key,status:result.status});
      }
      for(const key of ['current','no_history','writer_current','foreign_assignment']) {
        assert.equal((await get(reader,visitPath(key)+'/previous-service-record')).status,404);
        assert.equal((await get(reader,taskPath(key))).status,404);
      }
      check('pre-start-and-cross-scope-denied',{denied,historyAndTaskDenials:8});
      await reader.goto(workbench('no_history'));
      await reader.getByRole('button',{name:'Open service record',exact:true}).waitFor();
      assert.equal(await reader.getByRole('button',{name:/View previous service record|View follow-up tasks/}).count(),0);
      await shot(reader,'no-scope');
      check('missing-scopes-hide-panels');
      stage='schedule-to-start';
      await reader.goto(base+'/staff');
      const link=reader.locator('a[href="/staff/assignments/'+fixture.ids.current+'"]');
      await link.waitFor();
      await shot(reader,'schedule-en-1440');
      const schedule=await reader.context().newPage();
      const scheduleStates=[];
      schedule.on('response',async response=>{
        if(response.url().includes('/home-care-schedule')&&response.status()===200) {
          const data=(await response.json()).data;
          scheduleStates.push(data.items.find(row=>row.assignment_id===fixture.ids.current)?.status||'ABSENT');
        }
      });
      await schedule.goto(base+'/staff');
      await schedule.locator('a[href="/staff/assignments/'+fixture.ids.current+'"]') .waitFor();
      await link.click();
      await reader.getByRole('button',{name:'Start service',exact:true}).waitFor();
      const sibling=await reader.context().newPage();
      await sibling.goto(workbench('current'));
      await sibling.getByRole('button',{name:'Start service',exact:true}).waitFor();
      const started=reader.waitForResponse(r=>r.url().endsWith('/'+fixture.ids.current+'/start')&&r.request().method()==='POST');
      await reader.getByRole('button',{name:'Start service',exact:true}).click();
      await reader.getByRole('dialog').getByRole('button',{name:'Start service',exact:true}).click();
      const start=await started;
      assert.equal(start.status(),200);
      const startData=(await start.json()).data;
      assert.equal(startData.status,'IN_PROGRESS');
      assert.equal(startData.version,2);
      await reader.getByRole('button',{name:'View previous service record',exact:true}).waitFor();
      await sibling.getByRole('button',{name:'View previous service record',exact:true}).waitFor();
      // Wait for the actual background schedule response, not a fixed delay.
      for(let i=0;i<100&&!scheduleStates.includes('IN_PROGRESS');i++)await delay(100);
      assert.ok(scheduleStates.includes('IN_PROGRESS'));
      check('start-real-200-and-cross-tab-refresh',{version:2,scheduleStates:[...scheduleStates]});
      stage='live-history-and-tasks';
      const history=await get(reader,visitPath('current')+'/previous-service-record');
      const tasks=await get(reader,taskPath('current'));
      assert.equal(history.status,200);assert.equal(tasks.status,200);
      assert.equal(history.body.data.record.service_record_id,fixture.ids.source_note);
      assert.equal(history.body.data.record.content,note);
      assert.ok(history.cache.includes('no-store'));assert.ok(tasks.cache.includes('no-store'));
      assert.deepEqual(tasks.body.data.items.map(row=>row.status).sort(),['IN_PROGRESS','OPEN','POSTPONED']);
      check('real-cross-worker-history-and-three-task-states',{historyStatus:200,tasksStatus:200,sourceId:fixture.ids.source_note,noStore:true});
      const taskRequests=[];
      reader.on('request',request=>{const url=new URL(request.url());if(url.pathname.endsWith('/care-actions'))taskRequests.push(url.searchParams.get('assignment_id'));});
      for(const [locale,width,height] of [['en',1440,1000],['en',390,844],['en',768,1024],['zh-Hant',375,812],['zh-Hant',390,844],['zh-Hant',430,932],['zh-Hant',768,1024]]) {
        stage='view-'+locale+'-'+width;
        await reader.context().addCookies([{name:'kinsun_ui_locale',value:locale,url:base}]);
        await reader.setViewportSize({width,height});
        await reader.goto(workbench('current')+'?qa='+locale+'-'+width);
        await openPanels(reader,locale);
        await shot(reader,'handover-'+locale+'-'+width);
      }
      assert.ok(taskRequests.length>=7&&taskRequests.every(id=>id===fixture.ids.current));
      check('seven-real-data-viewport-checks-and-task-binding',{count:7});
      stage='submit-complete';
      await reader.context().addCookies([{name:'kinsun_ui_locale',value:'en',url:base}]);
      await reader.setViewportSize({width:390,height:844});
      await reader.goto(workbench('current'));
      await openPanels(reader);
      await openPanels(sibling);
      await reader.getByRole('button',{name:'Open service record',exact:true}).click();
      await reader.locator('textarea').fill(newNote);
      await reader.getByRole('checkbox').check();
      await reader.getByRole('button',{name:'Review and submit',exact:true}).click();
      await reader.getByRole('dialog').waitFor();
      await shot(reader,'confirm-en-390',false);
      const completed=reader.waitForResponse(r=>r.url().endsWith('/'+fixture.ids.current+'/service-record/complete')&&r.request().method()==='POST');
      await reader.getByRole('dialog').getByRole('button',{name:'Confirm submission and complete visit',exact:true}).click();
      const response=await completed;
      assert.equal(response.status(),201);
      const receipt=(await response.json()).data;
      assert.equal(receipt.status,'COMPLETED');assert.equal(receipt.assignment_version,3);
      check('real-ui-submit-and-complete',{status:201,receipt});
      await reader.getByText('This service is complete. Today’s schedule has been updated.',{exact:true}).waitFor();
      await noPrivate(reader);
      await shot(reader,'completed-en-390');
      await sibling.getByText('This assignment is unavailable. It may have ended or your access may have changed.',{exact:true}).waitFor({timeout:1000}).catch(()=>{});
      for(let i=0;i<100 && await sibling.getByText(note,{exact:true}).count();i++)await delay(100);
      await noPrivate(sibling);
      for(let i=0;i<100&&!scheduleStates.includes('ABSENT');i++)await delay(100);
      assert.ok(scheduleStates.includes('ABSENT'));
      assert.equal((await get(reader,visitPath('current'))).status,404);
      assert.equal((await get(reader,taskPath('current'))).status,404);
      assert.equal((await get(reader,visitPath('current')+'/previous-service-record')).status,404);
      await reader.getByRole('link',{name:'Back to today’s schedule',exact:true}).click();
      await reader.locator('a[href="/staff/assignments/'+fixture.ids.expiry+'"]') .waitFor();
      assert.equal(await reader.locator('a[href="/staff/assignments/'+fixture.ids.current+'"]') .count(),0);
      check('completion-clears-both-tabs-and-refreshes-schedule',{scheduleStates});
      await reader.context().close();
    }
    stage='writer-ready-for-retirement';
    const writer=await login('writer');
    await writer.setViewportSize({width:390,height:844});
    await writer.goto(workbench('writer_current'));
    await openPanels(writer);
    await writer.getByRole('button',{name:'Open service record',exact:true}).click();
    await writer.locator('textarea').fill('Synthetic unsent form: must disappear after access is revoked.');
    await shot(writer,'before-retirement-en-390');
    fs.writeFileSync(path.join(folder,'workbench-ready-to-retire.json'),JSON.stringify({campaign:fixture.campaign,ready:true}));
    check('ready-to-retire');
    stage='waiting-for-retirement';
    const deadline=Date.now()+600000;
    while(!fs.existsSync(path.join(folder,'workbench-retired.json'))) {
      if(Date.now()>deadline)throw new Error('Retirement wait expired');
      await delay(500);
    }
    stage='retirement-ui-clear';
    await writer.waitForFunction(()=>document.querySelectorAll('textarea').length===0&&![...document.querySelectorAll('h4')].some(el=>el.textContent.startsWith('Synthetic workbench')),{},{timeout:45000});
    await noPrivate(writer);
    assert.equal((await get(writer,visitPath('writer_current'))).status,401);
    await shot(writer,'after-retirement-en-390');
    check('real-retirement-401-clears-handover-tasks-and-unsent-form');
    evidence.status='PASS';
  } catch(error) {
    evidence.status='FAIL';evidence.failure={stage,errorType:error.name};
    console.log(JSON.stringify({result:'FAIL',stage,errorType:error.name}));
    process.exitCode=1;
  } finally {
    evidence.finishedAt=new Date().toISOString();
    fs.writeFileSync(path.join(folder,'workbench-real-'+mode+'-evidence.json'),JSON.stringify(evidence,null,2));
    if(browser)await browser.close();
    console.log(JSON.stringify({result:evidence.status,checks:evidence.checks.length,screenshots:evidence.screenshots.length}));
  }
})();
