// Delayed support responses must never paint a different account or reopened panel.
const fs=require('node:fs'), vm=require('node:vm'), assert=require('node:assert/strict');
const source=fs.readFileSync('web/support-ui.js','utf8');
const call=source.slice(source.indexOf('  async function call('),source.indexOf('  const json ='));
const load=source.slice(source.indexOf('  async function loadOrders('),source.indexOf('  function events('));
function setup(){
  let finish; const response=new Promise(resolve=>finish=resolve);
  const context=vm.createContext({key:'token_c',token:'old',sessionToken:'old',panel:{},merchant:false,code:'nanzhi',
    controller:new AbortController(),DOMException,orders:['previous'],
    sessionStorage:{getItem:()=>context.sessionToken},createApi:()=>()=>response});
  vm.runInContext(call+load,context);return {context,finish};
}
(async()=>{
  const normal=setup(), pending=normal.context.call('/conversations');normal.finish(['hello']);assert.deepEqual(await pending,['hello']);
  for(const method of ['call','loadOrders']){
    const account=setup(), request=account.context[method]('/conversations');
    account.context.sessionToken='new';account.context.token='new';account.context.panel={};account.finish(['private old data']);
    await assert.rejects(request,error=>error.name==='AbortError');assert.deepEqual(account.context.orders,['previous']);
    const closed=setup(), old=closed.context[method]('/conversations');closed.context.panel={};closed.finish(['old panel']);
    await assert.rejects(old,error=>error.name==='AbortError');
  }
  console.log('Support requests: normal replies, switched accounts and reopened panels passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
