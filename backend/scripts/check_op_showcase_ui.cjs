/* Real read-only production UI acceptance. Only login/logout writes occur. */
const fs=require('fs');
const assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
(async()=>{
  assert(process.env.QA_OPERATOR_FILE,'Set QA_OPERATOR_FILE to the private operator credential file');
  const lines=fs.readFileSync(process.env.QA_OPERATOR_FILE,'utf8').split(/\r?\n/);
  const origin=process.env.QA_ORIGIN||'https://shop.kkzzzq.cyou';
  const browser=await chromium.launch({channel:process.platform==='win32'?'msedge':undefined,headless:true});
  const context=await browser.newContext({viewport:{width:1440,height:1000}});const page=await context.newPage();
  page.setDefaultTimeout(15000);const errors=[];page.on('pageerror',e=>errors.push(String(e)));
  let token;
  try{
    const response=await context.request.post(origin+'/api/v1/auth/login',{data:{username:lines[1].slice(4).trim(),password:lines[2].slice(4).trim()}});
    assert(response.ok());token=(await response.json()).access_token;
    await context.addInitScript(t=>sessionStorage.setItem('token_op',t),token);
    await page.goto(origin+'/op.html');await page.locator('#content .cards').waitFor();
    const opened=[];
    async function tab(id){await page.locator('nav [data-page="'+id+'"]').click();await page.waitForFunction(()=>!document.querySelector('#content').textContent.includes('正在读取'));opened.push(id);}
    for(const id of ['overview','accounts','reviews','workspace-audits','shops','products','orders','shipments','after-sales','coupons','agent-logs','operation-logs','management-audits']){
      await tab(id);assert((await page.locator('#content').innerText()).trim());
    }
    const checks=[];
    for(const [id,query,parameter,states,field] of [
      ['products','【演示】','status',['on','off','draft','banned'],'status'],
      ['shipments','NZSHOW20261021','shipment_status',['shipped','transit','exception','delivered'],'shipment_status'],
      ['after-sales','NZSHOW20261021','after_sale_status',['requested','accepted','rejected','return_shipped','resolved','withdrawn'],'after_sale_status'],
      ['coupons','【演示】','status',['active','scheduled','expired','disabled','exhausted'],'issuance_state']
    ]){
      await tab(id);await page.getByLabel('选择店铺',{exact:true}).selectOption('1');
      await page.getByLabel('搜索关键词',{exact:true}).fill(query);
      for(const state of states){
        await page.getByLabel('状态筛选',{exact:true}).selectOption(state);
        const [response]=await Promise.all([page.waitForResponse(r=>r.url().includes('/api/v1/op/')&&new URL(r.url()).searchParams.get(parameter)===state&&r.request().method()==='GET'),page.getByRole('button',{name:'查询',exact:true}).click()]);
        assert(response.ok());const data=await response.json();assert(data.items.length>0,id+' '+state+' has actual data');assert(data.items.every(r=>r[field]===state));
        checks.push(id+':'+state);
      }
      if(process.env.QA_SCREENSHOT_DIR){fs.mkdirSync(process.env.QA_SCREENSHOT_DIR,{recursive:true});await page.screenshot({path:process.env.QA_SCREENSHOT_DIR+'/'+id+'.png',fullPage:true});}
    }
    const result=await context.request.get(origin+'/api/v1/op/qa/cases',{headers:{Authorization:'Bearer '+token}});assert(result.ok());const cases=await result.json();assert.equal(cases.length,76);
    for(const [prefix,count] of [['RF',40],['RA',16],['RE',20]])assert.equal(cases.filter(r=>r.id.startsWith(prefix)).length,count);
    assert.deepEqual(errors,[]);console.log(JSON.stringify({opened:opened.slice(0,13),state_checks:checks,cases:76,script_errors:errors,business_writes:false}));
  }finally{
    if(token)await context.request.post(origin+'/api/v1/auth/logout',{headers:{Authorization:'Bearer '+token}});
    await browser.close();
  }
})().catch(error=>{console.error(error.message);process.exitCode=1;});
