const fs=require('node:fs');
const assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
(async()=>{
 if(!process.env.QA_OPERATOR_FILE)throw Error('Set QA_OPERATOR_FILE to the private operator credential file');
 const lines=fs.readFileSync(process.env.QA_OPERATOR_FILE,'utf8').split('\n');
 const origin=process.env.QA_ORIGIN||'http://127.0.0.1:8000';
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(origin+'/op.html#/testing/runs');
  await page.getByLabel('管理员账号',{exact:true}).fill(lines[1].slice(4).trim());
  await page.getByLabel('登录密码',{exact:true}).fill(lines[2].slice(4).trim());
  await page.getByRole('button',{name:'进入运营工作台'}).click();
  const row=page.locator('[data-run-id]').first();await row.waitFor();
  await row.locator('button').first().click();
  await page.locator('.qa-run-detail').waitFor();
  assert(await row.evaluate(n=>n.nextElementSibling?.classList.contains('qa-run-detail')),'detail must directly follow clicked report');
  assert.equal(await page.locator('.qa-run-detail').count(),1);
  if(process.env.QA_SCREENSHOT_DIR)await page.screenshot({path:process.env.QA_SCREENSHOT_DIR+'/op-inline-report.png',fullPage:true});
  await row.locator('button').first().click();assert.equal(await page.locator('.qa-run-detail').count(),0);
  await page.goto(origin+'/op.html#/testing/cases');
  await page.getByRole('heading',{name:'测试用例管理',exact:true}).waitFor();
  for(const name of ['Agent 测试用例','接口测试用例','UI 测试用例']){await page.getByRole('button',{name,exact:true}).click();assert(await page.locator('.qa-case-item').count()>0);}
  if(process.env.QA_SCREENSHOT_DIR)await page.screenshot({path:process.env.QA_SCREENSHOT_DIR+'/op-case-library.png',fullPage:false});
  await page.getByLabel('用例状态',{exact:true}).selectOption('active');
  await page.getByRole('searchbox',{name:'搜索用例'}).fill('不存在的测试用例xyz');
  await page.getByText('没有匹配当前筛选与搜索的用例。',{exact:true}).waitFor();
  assert.deepEqual(errors,[]);console.log('PASS: inline report expansion/collapse, three categories, state filter, empty search, zero JS errors');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
