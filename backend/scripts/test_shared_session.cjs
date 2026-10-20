const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const disk=new Map();
function tab(initial={}) {
 const mem=new Map(Object.entries(initial));
 const storage=m=>({getItem:k=>m.get(k)||null,setItem:(k,v)=>m.set(k,v),removeItem:k=>m.delete(k)});
 const ctx={window:{},localStorage:storage(disk),sessionStorage:storage(mem),fetch:async()=>({ok:true,status:200,json:async()=>({id:1})})};
 vm.runInNewContext(fs.readFileSync('web/auth-ui.js','utf8'),ctx);
 return {auth:ctx.window.StoreAuth,mem};
}
(async()=>{
 const first=tab();first.auth.saveSession({token_b:'b1',token_c:'c1'});
 const second=tab();assert.equal(second.mem.get('token_b'),'b1');assert.equal(second.mem.get('token_c'),'c1');
 assert.equal((await second.auth.currentUser()).id,1);
 second.auth.saveSession({token_b:'',token_c:'buyer-only'});
 const third=tab();assert.equal(third.mem.has('token_b'),false);assert.equal(third.mem.get('token_c'),'buyer-only');
 await third.auth.logout('token_c');assert.equal(disk.get('store_account_session'),'null');
 await first.auth.currentUser();assert.equal(first.mem.has('token_b'),false);
 assert.equal(tab().mem.has('token_c'),false);
 console.log('Same-origin new-tab session, buyer-only session and logout passed');
})().catch(e=>{console.error(e);process.exitCode=1});
