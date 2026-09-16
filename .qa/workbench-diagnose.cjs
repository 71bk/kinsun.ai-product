const {chromium}=require('playwright');
const fs=require('node:fs');
const path=require('node:path');
(async()=>{
 const fixture=JSON.parse(fs.readFileSync(path.join(__dirname,'.env.workbench-real-auth'),'utf8'));
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try {
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 await page.context().addCookies([{name:'kinsun_ui_locale',value:'en',url:'http://localhost:3000'}]);
 page.on('response',r=>{const u=new URL(r.url());if(u.pathname.startsWith('/backend/core/'))console.log(JSON.stringify({path:u.pathname,status:r.status()}));});
 await page.goto('http://localhost:3000/staff/sign-in');
 await page.locator('[name=email]').fill(fixture.accounts.reader.email);
 await page.locator('[name=password]').fill(fixture.accounts.reader.password);
 await page.getByRole('button',{name:'登入 / Sign in',exact:true}).click();
 await page.waitForURL(u=>!u.pathname.includes('sign-in'));
 await page.goto('http://localhost:3000/staff');
 await page.waitForTimeout(4000);
 console.log(JSON.stringify(await page.evaluate(()=>({headings:[...document.querySelectorAll('h1,h2,h3')].map(e=>e.textContent),alerts:[...document.querySelectorAll('[role=alert]')].map(e=>e.textContent),links:[...document.querySelectorAll('main a')].map(e=>({label:e.textContent,href:e.getAttribute('href')}))}))));
 await page.screenshot({path:path.join(__dirname,'workbench-real-diagnose.png'),fullPage:true});
 }finally{await browser.close();}
})().catch(e=>{console.log(JSON.stringify({errorType:e.name}));process.exitCode=1;});
