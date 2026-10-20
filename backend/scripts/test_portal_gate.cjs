const fs=require('node:fs'), vm=require('node:vm'), assert=require('node:assert/strict');
const source=fs.readFileSync('web/portal.js','utf8');
async function run(role,loggedIn){
  const tokens=new Map([['portal_role',role],['token_b','merchant-token'],['token_c','customer-token']]);
  const calls=[],redirects=[];
  const context=vm.createContext({StoreAuth:{currentUser:async()=>loggedIn?{id:1}:null},
    sessionStorage:{getItem:key=>tokens.get(key)},location:{replace:url=>redirects.push(url)},
    fetch:async(path,options)=>{calls.push({path,options});return {status:401};}});
  await vm.runInContext(source,context);
  return {calls,redirects};
}
(async()=>{
  const anonymous=await run('merchant',false);
  assert.equal(anonymous.calls.length,0);
  assert.deepEqual(anonymous.redirects,['/account-login.html']);
  for(const role of ['merchant','customer']){
    const state=await run(role,true);
    assert.equal(state.calls[0].path,'/api/v1/auth/portal-session');
    assert.equal(state.calls[0].options.headers.Authorization,`Bearer ${role==='merchant'?'merchant':'customer'}-token`);
    assert.deepEqual(state.redirects,['/account-login.html']);
  }
  console.log('Portal gate: anonymous redirect, expired redirect and active legacy identity selection passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
