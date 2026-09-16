// Real form login -> BFF -> Core -> Supabase. No route mocks or session injection.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const {createRequire} = require('node:module');
const frontendRoot = process.argv[2];
if (!frontendRoot) throw new Error('Provide the frontend checkout path');
const {chromium} = createRequire(path.join(frontendRoot, 'package.json'))('playwright');
const fixture = JSON.parse(fs.readFileSync(path.join(__dirname,'.env.b03-b04-real-auth'),'utf8'));
assert.equal(fixture.campaign,'b03-b04-real-auth-20260916');
assert.ok(!fixture.retired && fixture.account);
const folder=path.join(__dirname,'local');fs.mkdirSync(folder,{recursive:true});
const base='http://localhost:3000';
const evidence={campaign:fixture.campaign,checks:[],screenshots:[],startedAt:new Date().toISOString()};
let stage='launch',browser;
const check=(name,details={})=>{evidence.checks.push({name,...details});console.log(JSON.stringify({check:name,...details}));};
const apiPath='/api/v1/elders/'+fixture.ids.elder+'/care-events';
const target=base+'/staff/elders/'+fixture.ids.elder;
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function api(page,route,body,key){return page.evaluate(async({route,body,key})=>{
  const response=await fetch('/backend/core'+route,{method:body?'POST':'GET',cache:'no-store',
    headers:body?{'Content-Type':'application/json','Idempotency-Key':key}:undefined,
    body:body?JSON.stringify(body):undefined});
  return {status:response.status,body:await response.json()};
},{route,body,key});}
function card(page,label){return page.locator('section[data-state], tbody tr').filter({hasText:'Synthetic B03 '+label}).filter({visible:true}).last();}
async function open(page,label){const c=card(page,label);await c.getByRole('button',{name:'Review',exact:true}).click();await c.getByRole('combobox',{name:'Review decision',exact:true}).selectOption('CORRECT');return c;}
async function submit(page,c,id,expected=200){
  await c.getByRole('button',{name:'Submit review',exact:true}).click();
  const responsePromise=page.waitForResponse(r=>r.url().endsWith('/'+id+'/review')&&r.request().method()==='POST');
  await page.getByRole('dialog').filter({visible:true}).getByRole('button',{name:'Submit review',exact:true}).click();
  const response=await responsePromise;
  assert.equal(response.status(),expected);
  return {status:response.status(),body:await response.json(),request:response.request().postDataJSON(),key:response.request().headers()['idempotency-key']};
}
async function shot(page,label){
  const geometry=await page.evaluate(()=>({width:innerWidth,client:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth}));
  assert.ok(geometry.scroll<=geometry.client);
  const filename='b03-real-'+label+'.png';await page.screenshot({path:path.join(folder,filename)});
  evidence.screenshots.push({filename,geometry});
}
(async()=>{
 try{
  browser=await chromium.launch({channel:'chrome',headless:true});
  const context=await browser.newContext({viewport:{width:1440,height:900},timezoneId:'Asia/Taipei'});
  await context.addCookies([{name:'kinsun_ui_locale',value:'en',url:base}]);
  const page=await context.newPage();
  stage='login';await page.goto(base+'/staff/sign-in');
  await page.locator('input[name="email"]').fill(fixture.account.email);
  await page.locator('input[name="password"]').fill(fixture.account.password);
  await page.locator('form').filter({has:page.locator('input[name="email"]')}).locator('button[type="submit"]').click();
  await page.waitForURL(url=>!url.pathname.includes('sign-in'),{timeout:30000});
  const me=await api(page,'/api/v1/me');assert.equal(me.status,200);assert.equal(me.body.data.actor_id,fixture.ids.worker);
  check('real-form-login',{status:me.status});
  stage='create-candidates';const ids={};
  for(const label of ['Changed','Clear','Keep','Expire']){
    const created=await api(page,'/api/v1/elders/'+fixture.ids.elder+'/care-event-candidates',{
      source_type:'MANUAL',event_type:'MEAL',event_time:'2026-09-16T01:10:45Z',
      structured_payload:{summary:'Synthetic B03 '+label},evidence_refs:[],confidence_band:'LOW',
      extractor_version:'synthetic-human-qa.v1'},fixture.campaign+'-create-'+label);
    assert.equal(created.status,201);ids[label]=created.body.data.event_id;
  }
  evidence.ids=ids;check('four-real-manual-candidates',{ids});
  fs.writeFileSync(path.join(folder,'b03-created.json'),JSON.stringify({campaign:fixture.campaign,ids}));
  stage='negative-scope';
  for(const id of [fixture.ids.unassigned,'00000000-0000-4000-8000-000000000099']){
    assert.equal((await api(page,'/api/v1/elders/'+id+'/care-events')).status,404);
  }
  check('unassigned-and-missing-elder-denied');
  const sibling=await context.newPage();await sibling.goto(target+'?review=pending');
  const staleCard=await open(sibling,'Changed');await staleCard.getByRole('textbox',{name:'Corrected content',exact:true}).fill('Synthetic B03 stale draft');
  const geo=[];
  stage='responsive-live-form';
  for(const [width,height] of [[375,812],[390,844],[430,932],[1440,900]]){
    await page.setViewportSize({width,height});await page.goto(target+'?review=pending&qa='+width);
    const c=await open(page,'Changed');
    assert.equal(await c.getByRole('textbox',{name:'Corrected event time',exact:true}).inputValue(),'2026-09-16T09:10');
    await c.getByRole('textbox',{name:'Corrected event time',exact:true}).scrollIntoViewIfNeeded();
    await shot(page,'form-'+width);geo.push(width);
  }
  check('live-form-four-viewports',{widths:geo});
  stage='correct-type-time';const c=card(page,'Changed');
  await c.getByRole('combobox',{name:'Corrected event type',exact:true}).selectOption('SLEEP');
  await c.getByRole('textbox',{name:'Corrected event time',exact:true}).fill('2026-09-16T21:30');
  await c.getByRole('textbox',{name:'Corrected content',exact:true}).fill('Synthetic B03 Changed corrected');
  const changed=await submit(page,c,ids.Changed);evidence.changed=changed;
  assert.equal(changed.body.data.event_type,'SLEEP');assert.equal(changed.body.data.event_time,'2026-09-16T13:30:00Z');assert.equal(changed.body.data.version,2);
  const replay=await api(page,apiPath+'/'+ids.Changed+'/review',changed.request,changed.key);
  assert.equal(replay.status,200);assert.deepEqual(replay.body.data,changed.body.data);
  check('ui-correction-and-same-key-replay',{version:2,time:changed.body.data.event_time});
  stage='stale-tab';const stale=await submit(sibling,staleCard,ids.Changed,409);
  await sibling.getByText('This record has been updated. Please reload before acting on it.',{exact:true}).waitFor();
  assert.equal(await staleCard.getByRole('textbox',{name:'Corrected content',exact:true}).inputValue(),'Synthetic B03 stale draft');
  check('real-stale-tab-409-draft-retained',{status:stale.status});
  stage='clear-and-keep';await page.goto(target+'?review=pending');
  const clear=await open(page,'Clear');await clear.getByRole('checkbox',{name:'This event has no recorded time',exact:true}).check();
  const cleared=await submit(page,clear,ids.Clear);assert.equal(cleared.request.corrected_event_time,null);assert.equal(cleared.body.data.event_time,null);
  await page.goto(target+'?review=pending');const keep=await open(page,'Keep');
  await keep.getByRole('textbox',{name:'Corrected content',exact:true}).fill('Synthetic B03 Keep corrected');
  const kept=await submit(page,keep,ids.Keep);assert.ok(!Object.hasOwn(kept.request,'corrected_event_time'));assert.ok(!Object.hasOwn(kept.request,'corrected_event_type'));
  assert.equal(kept.body.data.event_time,'2026-09-16T01:10:45Z');
  check('ui-clear-and-omit-preserve-seconds',{cleared:null,kept:kept.body.data.event_time});
  stage='source-filters';await page.goto(target);
  await page.getByRole('combobox',{name:'Source',exact:true}).waitFor();
  for(const [source,expected] of [['MANUAL',[ids.Changed,ids.Clear,ids.Keep]],['CONVERSATION_SESSION',[fixture.ids.legacy_conversation]],['UNKNOWN',[fixture.ids.legacy_unknown]]]){
    const responsePromise=page.waitForResponse(r=>r.url().includes('/care-events?')&&r.url().includes('source_type='+source)&&r.status()===200);
    await page.getByRole('combobox',{name:'Source',exact:true}).selectOption(source);const response=await responsePromise;
    const data=(await response.json()).data;assert.deepEqual(data.items.map(x=>x.event_id).sort(),expected.sort());
    assert.ok(!new URL(response.url()).searchParams.has('cursor'));check('real-source-'+source,{count:data.items.length});
  }
  const resetResponse=page.waitForResponse(r=>r.url().endsWith('/care-events?limit=100')&&r.status()===200);
  await page.getByRole('button',{name:'Clear filters',exact:true}).click();assert.equal((await (await resetResponse).json()).data.items.length,5);
  const first=await api(page,apiPath+'?limit=2');assert.equal(first.status,200);assert.equal(first.body.data.items.length,2);
  const next=await api(page,apiPath+'?limit=2&cursor='+encodeURIComponent(first.body.data.next_cursor));assert.equal(next.status,200);
  assert.equal(new Set([...first.body.data.items,...next.body.data.items].map(x=>x.event_id)).size,4);
  const combined=await api(page,apiPath+'?source_type=MANUAL&event_type=SLEEP&status=CORRECTED&date_from=2026-09-16&date_to=2026-09-16');
  assert.equal(combined.status,200);assert.deepEqual(combined.body.data.items.map(x=>x.event_id),[ids.Changed]);
  check('real-filter-reset-cursor-and-intersection');
  stage='prepare-expiry';await page.setViewportSize({width:390,height:844});await page.goto(target+'?review=pending');
  const expiry=await open(page,'Expire');await expiry.getByRole('textbox',{name:'Corrected content',exact:true}).fill('Synthetic B03 unsent expiry draft');
  await shot(page,'before-expiry');
  fs.writeFileSync(path.join(folder,'b03-ready-to-expire.json'),JSON.stringify({campaign:fixture.campaign,ready:true}));
  check('ready-to-expire');
  stage='wait-for-expiry';const deadline=Date.now()+600000;
  while(!fs.existsSync(path.join(folder,'b03-expired.json'))){if(Date.now()>deadline)throw Error('Expiry wait timed out');await pause(500);}
  stage='expired-submit';await submit(page,expiry,ids.Expire,404);
  await page.getByText('Your current identity does not have permission to view or act on this elder’s data.',{exact:true}).waitFor({timeout:3000}).catch(()=>{});
  await page.waitForFunction(()=>document.querySelectorAll('textarea').length===0);
  assert.ok(!(await page.locator('body').innerText()).includes('Synthetic B03'));
  assert.equal((await api(page,apiPath+'/'+ids.Changed+'/review',changed.request,changed.key)).status,404);
  assert.equal((await api(page,apiPath)).status,404);await shot(page,'after-expiry');
  check('expired-ui-submit-and-replay-denied',{status:404});
  evidence.status='PASS';
 }catch(error){evidence.status='FAIL';evidence.failure={stage,errorType:error.name};console.log(JSON.stringify(evidence.failure));process.exitCode=1;
 }finally{evidence.finishedAt=new Date().toISOString();fs.writeFileSync(path.join(folder,'b03-real-evidence.json'),JSON.stringify(evidence,null,2));if(browser)await browser.close();console.log(JSON.stringify({result:evidence.status,checks:evidence.checks.length}));}
})();
