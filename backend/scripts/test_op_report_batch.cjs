const fs=require('node:fs');
const assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
(async()=>{
  assert(process.env.QA_OPERATOR_FILE&&process.env.QA_REPORT_ID,'Set QA_OPERATOR_FILE and QA_REPORT_ID');
  const origin=process.env.QA_ORIGIN||'https://shop.kkzzzq.cyou';
  const lines=fs.readFileSync(process.env.QA_OPERATOR_FILE,'utf8').split(/\r?\n/);
  const browser=await chromium.launch({channel:process.platform==='win32'?'msedge':undefined,headless:true});
  const context=await browser.newContext({viewport:{width:1440,height:1000}});let token;
  try{
    const login=await context.request.post(origin+'/api/v1/auth/login',{data:{username:lines[1].slice(4).trim(),password:lines[2].slice(4).trim()}});assert(login.ok());token=(await login.json()).access_token;
    const response=await context.request.get(origin+'/api/v1/op/qa/runs/'+process.env.QA_REPORT_ID,{headers:{Authorization:'Bearer '+token}});assert(response.ok());const report=await response.json();assert(report.report_batch&&report.results.length>1);
    await context.addInitScript(t=>sessionStorage.setItem('token_op',t),token);const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(String(e)));
    await page.goto(origin+'/op.html#/testing/runs');const row=page.locator('[data-run-id="'+report.id+'"]');await row.waitFor();await row.locator('button').first().click();
    assert(await row.evaluate(n=>n.nextElementSibling.classList.contains('qa-run-detail')));
    assert.equal(await page.locator('.qa-evidence-column').first().locator('button').count(),report.results.length);
    for(const result of [report.results[0],report.results.at(-1),report.results.find(r=>r.evidence.artifacts?.length)].filter(Boolean)){
      await page.locator('.qa-evidence-column').first().getByRole('button').filter({hasText:result.id+' '}).click();
      const middle=page.locator('.qa-evidence-column').nth(1);await middle.getByRole('heading',{name:'测试步骤（中文）',exact:true}).waitFor();
      assert((await middle.innerText()).includes(result.doc.steps[0]));
      if(result.evidence.artifacts?.length)await page.waitForFunction(()=>document.querySelector('.qa-shot img')?.naturalWidth>0);
    }
    for(const child of report.source_run_ids)assert.equal(await page.locator('[data-run-id="'+child+'"]').count(),0);
    if(process.env.QA_SCREENSHOT){await page.screenshot({path:process.env.QA_SCREENSHOT,fullPage:false});}
    assert.deepEqual(errors,[]);console.log(JSON.stringify({report:report.id,cases:report.results.length,inline:true,switching:true,screenshot_loaded:true,hidden_child_reports:true,script_errors:errors}));
  }finally{if(token)await context.request.post(origin+'/api/v1/auth/logout',{headers:{Authorization:'Bearer '+token}});await browser.close();}
})().catch(e=>{console.error(e.message);process.exitCode=1;});
