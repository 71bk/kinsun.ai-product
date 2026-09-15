async (page) => {
  const base = 'http://localhost:3000';
  const results = [];
  const folder = 'D:/Hackthon/kinsun.ai/.qa/';
  for (const [locale,width,height] of [['en',390,844]]) {
    await page.context().unrouteAll({behavior:'wait'});
    await page.setViewportSize({width,height});
    await page.context().addCookies([{name:'kinsun_ui_locale',value:locale,url:base}]);
    const id = '00000000-0000-4000-8000-000000000002';
    const elder = '00000000-0000-4000-8000-000000000003';
    const visit = {assignment_id:id,elder_id:elder,provider_tenant_id:elder,care_unit_id:elder,home_care_worker_id:elder,
      scheduled_start:new Date(Date.now()-3600000).toISOString(),scheduled_end:new Date(Date.now()+3600000).toISOString(),expires_at:new Date(Date.now()+3600000).toISOString(),
      status:'CONFIRMED',version:1,allowed_data_scopes:['assignment:read','assignment:start','assignment:complete','service_record:read','service_record:write','service_record:history:read','care_action:read']};
    const calls=[];
    const envelope = data => ({data,meta:{correlation_id:'synthetic-workbench',schema_version:'1.0',timestamp:new Date().toISOString()}});
    const denied = {error:{code:'not_found',message:'Resource not found'}};
    await page.context().route(base+'/backend/auth/session',r=>r.fulfill({json:{credential_present:true}}));
    await page.context().route(base+'/backend/core/**',async r=>{
      const request=r.request(); const path=request.url().split('?')[0];
      if(path.endsWith('/me'))return r.fulfill({json:envelope({role:'HOME_CARE_WORKER',display_name:'Synthetic worker',tenant_id:elder,care_unit_ids:[]})});
      if(path.endsWith('/authorized-elders'))return r.fulfill({json:envelope({items:[],page:{next_cursor:null,has_more:false,limit:100}})});
      if(path.endsWith('/home-care-schedule'))return r.fulfill({json:envelope({as_of:new Date().toISOString(),items:visit.status==='COMPLETED'?[]:[{assignment_id:id,elder_id:elder,display_name:'合成長者 Synthetic Elder',status:visit.status,scheduled_start:visit.scheduled_start,scheduled_end:visit.scheduled_end,timezone:'UTC',local_date:new Date().toISOString().slice(0,10)}],page:{next_cursor:null,has_more:false,limit:20}})});
      if(path.endsWith('/start')){visit.status='IN_PROGRESS';visit.version=2;calls.push('start');return r.fulfill({json:envelope(visit)});}
      if(path.endsWith('/service-record/complete')){visit.status='COMPLETED';visit.version=3;calls.push('complete');return r.fulfill({status:201,json:envelope({service_record_id:elder,assignment_id:id,assignment_version:3,status:'COMPLETED'})});}
      if(path.endsWith('/assignments/'+id))return r.fulfill(visit.status==='COMPLETED'?{status:404,json:denied}:{json:envelope(visit)});
      if(path.endsWith('/previous-service-record')){calls.push('history');return r.fulfill({json:envelope({assignment_id:id,record:{service_record_id:elder,source_assignment_id:elder,service_date:'2026-09-13',service_timezone:'Asia/Taipei',completed_at:'2026-09-13T01:00:00Z',version:1,content:'合成上次紀錄：已完成生活活動並交班。 Synthetic previous handover.'}})});}
      if(path.endsWith('/care-actions')){if(!request.url().includes('assignment_id='+id))throw new Error('Unbound task request');calls.push('tasks');return r.fulfill({json:envelope({items:[{care_action_id:elder,elder_id:elder,title:'合成待追蹤事項 Synthetic follow-up task',description:'請於下次服務確認活動安排。 Synthetic follow-up details.',status:'OPEN',due_at:new Date(Date.now()+86400000).toISOString(),source_event_provenance:[]}],next_cursor:null,has_more:false})});}
      return r.fulfill({status:404,json:denied});
    });
    const text = (en,zh) => locale==='en'?en:zh;
    await page.goto(base+'/staff?qa=workbench-confirm-visual-'+locale+'-'+width);
    const link=page.getByRole('link',{name:text('Open this assignment','開啟這次派案'),exact:true});
    await link.waitFor();
    if(calls.length)throw new Error('Prefetched private content');
    await page.screenshot({path:folder+`workbench-confirm-visual-schedule-${locale}-${width}.png`,fullPage:true});
    await link.click();
    await page.getByRole('button',{name:text('Start service','開始服務'),exact:true}).click();
    await page.locator('dialog[open]').getByRole('button',{name:text('Start service','開始服務'),exact:true}).click();
    await page.getByRole('button',{name:text('View previous service record','查看上次服務紀錄'),exact:true}).click();
    await page.getByText(/Synthetic previous handover/).waitFor();
    await page.getByRole('button',{name:text('View follow-up tasks','查看待追蹤事項'),exact:true}).click();
    await page.getByText(/Synthetic follow-up details/).waitFor();
    await page.screenshot({path:folder+`workbench-confirm-visual-handover-${locale}-${width}.png`,fullPage:true});
    const geometry=await page.evaluate(()=>({inner:innerWidth,client:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth}));
    if(geometry.scroll>geometry.client)throw new Error('Handover overflow');
    await page.getByRole('button',{name:text('Open service record','開啟服務紀錄'),exact:true}).click();
    await page.locator('textarea').fill('Synthetic workbench completion note. 合成工作台服務紀錄。');
    await page.getByRole('checkbox').check();
    await page.getByRole('button',{name:text('Review and submit','檢查並提交'),exact:true}).click();
    await page.locator('dialog[open]').waitFor(); await page.evaluate(() => window.scrollTo(0,0)); await page.waitForFunction(() => { const d = document.querySelector('dialog[open]'); const r = d.getBoundingClientRect(); return r.top >= 0 && r.bottom <= innerHeight && d.getAnimations().every(a => a.playState !== 'running'); });
    await page.screenshot({path:folder+`workbench-confirm-visual-confirm-${locale}-${width}.png`});
    await page.locator('dialog[open]').getByRole('button',{name:text('Confirm submission and complete visit','確認提交並完成服務'),exact:true}).click();
    await page.getByText(text('This service is complete. Today’s schedule has been updated.','本次服務已完成，今日行程已更新。'),{exact:true}).waitFor();
    if(await page.locator('textarea').count()||await page.getByText(/Synthetic previous handover|Synthetic follow-up details/).count())throw new Error('Content retained after completion');
    await page.screenshot({path:folder+`workbench-confirm-visual-completed-${locale}-${width}.png`,fullPage:true});
    await page.getByRole('link',{name:text('Back to today’s schedule','返回今日行程'),exact:true}).click();
    await page.getByText(text('No viewable assignments for today.','目前沒有可預覽的今日派案。'),{exact:true}).waitFor();
    results.push({locale,width,geometry,started:calls.includes('start'),completed:calls.includes('complete'),tasksBound:true,contentCleared:true,scheduleRefreshed:true});
  }
  return results;
}
