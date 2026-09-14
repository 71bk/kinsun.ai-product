async(page)=>{
  const base='http://localhost:3107',folder='D:/Hackthon/kinsun.ai/.qa/',results=[];
  for(const mode of ['empty','error','loading','denied','noScope','keyboard','reduced']){
    await page.context().unrouteAll({behavior:'wait'});
    await page.setViewportSize({width:390,height:844});
    await page.emulateMedia({reducedMotion:mode==='reduced'?'reduce':'no-preference'});
    await page.context().addCookies([{name:'kinsun_ui_locale',value:'en',url:base}]);
    const id='00000000-0000-4000-8000-000000000002',elder='00000000-0000-4000-8000-000000000003';
    const visit={assignment_id:id,elder_id:elder,provider_tenant_id:elder,care_unit_id:elder,home_care_worker_id:elder,
      scheduled_start:new Date(Date.now()-3600000).toISOString(),scheduled_end:new Date(Date.now()+3600000).toISOString(),expires_at:new Date(Date.now()+3600000).toISOString(),status:'IN_PROGRESS',version:2,
      allowed_data_scopes:mode==='noScope'?['assignment:read']:['assignment:read','care_action:read']};
    const envelope=data=>({data,meta:{correlation_id:'synthetic-states',timestamp:new Date().toISOString(),schema_version:'1.0'}});
    let pending,revoked=false;
    await page.context().route(base+'/backend/auth/session',r=>r.fulfill({json:{credential_present:true}}));
    await page.context().route(base+'/backend/core/**',r=>{
      const path=r.request().url().split('?')[0];
      if(revoked)return r.fulfill({status:401,json:{error:{code:'authentication_required',message:'Authentication required'}}});
      if(path.endsWith('/assignments/'+id))return r.fulfill({json:envelope(visit)});
      if(path.endsWith('/care-actions')){
        if(mode==='loading'){pending=r;return;}
        if(mode==='error')return r.fulfill({status:500,json:{error:{code:'unavailable',message:'Synthetic failure'}}});
        return r.fulfill({json:envelope({items:mode==='empty'?[]:[{care_action_id:elder,elder_id:elder,title:'Synthetic follow-up',description:'Synthetic private task content',due_at:new Date().toISOString(),status:'OPEN',source_event_provenance:[]}],next_cursor:null,has_more:false})});
      }
      return r.fulfill({status:404,json:{error:{code:'not_found',message:'Resource not found'}}});
    });
    await page.goto(base+'/staff/assignments/'+id+'?qa='+mode);
    if(mode==='noScope'){
      await page.getByText('Version 2',{exact:true}).waitFor();
      if(await page.getByRole('button',{name:'View follow-up tasks'}).count())throw new Error('No scope entry');
    }else{
      const button=page.getByRole('button',{name:'View follow-up tasks',exact:true});await button.waitFor();
      if(mode==='keyboard'){await button.focus();await page.keyboard.press('Enter');}else await button.click();
      if(mode==='loading'){await page.waitForTimeout(150);}
      else if(mode==='empty')await page.getByText('There are no follow-up tasks available to view.',{exact:true}).waitFor();
      else if(mode==='error')await page.getByRole('alert').waitFor();
      else await page.getByText('Synthetic private task content',{exact:true}).waitFor();
      if(mode==='denied'){
        revoked=true;await page.evaluate(()=>window.dispatchEvent(new Event('focus')));
        await page.getByRole('alert').waitFor();
        if(await page.getByText('Synthetic private task content',{exact:true}).count())throw new Error('Revoked content retained');
      }
    }
    await page.screenshot({path:folder+'workbench-state-'+mode+'-en-390.png',fullPage:true});
    const geometry=await page.evaluate(()=>({inner:innerWidth,client:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth,reduced:matchMedia('(prefers-reduced-motion: reduce)').matches}));
    if(geometry.scroll>geometry.client)throw new Error('State overflow');
    if(pending)await pending.fulfill({json:envelope({items:[],next_cursor:null,has_more:false})});
    results.push({mode,geometry});
  }
  await page.emulateMedia({reducedMotion:'no-preference'});
  return results;
}
