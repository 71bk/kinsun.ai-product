async (page) => {
  const base = 'http://localhost:3108';
  const folder = 'D:/Hackthon/kinsun.ai/.qa/';
  const evidence = [];
  const errors = [];
  page.on('pageerror', error => errors.push(error.name));
  for (const [locale, width, height, state] of [
    ['zh-Hant',375,812,'note'],['zh-Hant',390,844,'note'],['zh-Hant',430,932,'note'],
    ['zh-Hant',768,1024,'note'],['zh-Hant',1440,900,'note'],['en',390,844,'note'],['en',768,1024,'note'],
    ['en',390,844,'empty'],['en',390,844,'error'],['en',390,844,'loading'],
    ['en',390,844,'denied'],['en',390,844,'noScope'],['en',390,844,'keyboard'],['en',390,844,'reduced'],
  ]) {
    await page.unrouteAll({behavior:'wait'});
    await page.setViewportSize({width,height});
    await page.emulateMedia({reducedMotion: state === 'reduced' ? 'reduce' : 'no-preference'});
    await page.context().addCookies([{name:'kinsun_ui_locale',value:locale,url:base}]);
    let reads = 0;
    let revoked = false;
    let release;
    const gate = new Promise(resolve => { release=resolve; });
    const visit = {
      assignment_id:'00000000-0000-4000-8000-000000000002',elder_id:'00000000-0000-4000-8000-000000000003',
      provider_tenant_id:'00000000-0000-4000-8000-000000000004',care_unit_id:'00000000-0000-4000-8000-000000000005',
      home_care_worker_id:'00000000-0000-4000-8000-000000000006',
      scheduled_start:new Date(Date.now()-3600000).toISOString(),scheduled_end:new Date(Date.now()+3600000).toISOString(),
      expires_at:new Date(Date.now()+3600000).toISOString(),status:'IN_PROGRESS',version:2,
      allowed_data_scopes:['assignment:read',...(state==='noScope'?[]:['service_record:history:read'])],
    };
    const content = locale==='en'
      ? 'Synthetic handover: completed the planned activity. The next worker can read this original note.\nThis is synthetic test data. '+ 'LongSyntheticWord'.repeat(12)
      : '合成測試交接：已完成本次安排的生活活動。接班居服員可查看這份人工原文。\n此內容僅供畫面測試，並非真實長者資料。';
    const envelope = data => ({data,meta:{correlation_id:'synthetic-history',schema_version:'1.0',timestamp:new Date().toISOString()}});
    const record = {service_record_id:'00000000-0000-4000-8000-000000000001',source_assignment_id:'00000000-0000-4000-8000-000000000007',service_date:'2026-09-13',service_timezone:'Asia/Taipei',completed_at:'2026-09-13T02:00:00Z',version:1,content};
    await page.route('**/backend/auth/session',route=>route.fulfill({json:{credential_present:true}}));
    await page.route('**/backend/core/**',async route=>{
      const path=route.request().url().split('?')[0];
      if(path.endsWith('/home-care/assignments')) return route.fulfill({json:envelope({items:revoked?[]:[visit]})});
      if(path.endsWith('/previous-service-record')) {
        reads++;
        if(state==='loading') await gate;
        if(state==='denied') {revoked=true;return route.fulfill({status:404,json:{error:{code:'not_found',message:'Resource not found'}}});}
        if(state==='error' && reads===1) return route.fulfill({status:503,json:{error:{code:'unavailable',message:'Unavailable'}}});
        return route.fulfill({json:envelope({assignment_id:visit.assignment_id,record:state==='empty'?null:record})});
      }
      return route.fulfill({status:404,json:{error:{code:'not_found',message:'Resource not found'}}});
    });
    await page.goto(`${base}/staff/assignments?qa=previous-${locale}-${width}-${state}`);
    await page.getByRole('article').waitFor();
    const toggle=page.getByRole('button',{name:locale==='en'?'View previous service record':'查看上次服務紀錄',exact:true});
    if(reads) throw new Error('History prefetched');
    if(state==='noScope') {
      if(await toggle.count()) throw new Error('History entry without scope');
    } else {
      if(state==='keyboard') {await toggle.focus();await page.keyboard.press('Enter');}
      else await toggle.click();
      if(state==='loading') await page.locator('article [role=status][aria-busy=true]').waitFor();
      else if(state==='empty') await page.getByText('No previous service record is currently available.',{exact:true}).waitFor();
      else if(state==='error') await page.getByText('The previous service record could not be loaded. Please retry.',{exact:true}).waitFor();
      else if(state==='denied') {
        await page.getByText('Content is unavailable',{exact:true}).waitFor();
        if(await page.getByRole('article').count()) throw new Error('Revoked card retained');
      }
      else await page.getByText(content,{exact:true}).waitFor();
    }
    await page.evaluate(()=>{ if(document.activeElement instanceof HTMLElement && document.activeElement.textContent?.includes('Skip')) document.activeElement.blur(); window.scrollTo(0,0); });
    const geometry=await page.evaluate(()=>({inner:innerWidth,client:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth,reduced:matchMedia('(prefers-reduced-motion: reduce)').matches}));
    if(geometry.scroll>geometry.client) throw new Error(`Overflow ${locale}/${width}/${state}`);
    const screenshot=`previous-record-${locale}-${width}-${state}.png`;
    await page.screenshot({path:folder+screenshot,fullPage:true});
    if(state==='loading') {release();await page.getByText(content,{exact:true}).waitFor();}
    if(state==='error') {await page.getByRole('button',{name:'Retry',exact:true}).click();await page.getByText(content,{exact:true}).waitFor();}
    if(!['denied','empty','noScope'].includes(state)) {
      await page.getByRole('button',{name:locale==='en'?'Hide previous service record':'收起上次服務紀錄',exact:true}).click();
      if(await page.getByText(content,{exact:true}).count()) throw new Error('Note retained after close');
    }
    evidence.push({locale,width,height,state,reads,geometry,screenshot});
  }
  if(errors.length) throw new Error(`Page errors: ${errors.join(',')}`);
  await page.emulateMedia({reducedMotion:'no-preference'});
  return evidence;
}
