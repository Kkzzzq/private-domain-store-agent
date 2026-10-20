const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const saved=new Map(),listeners={};let view={filter:'home'},serial=0;
const win={scrollX:0,scrollY:0,addEventListener:(name,fn)=>listeners[name]=fn,scrollTo:({top,left})=>{win.scrollY=top;win.scrollX=left}};
const loc={pathname:'/c.html',search:'?code=nanzhi',href:'https://shop/c.html?code=nanzhi#/'};
const history={state:null,replaceState:s=>history.state=s};
const ctx={window:win,location:loc,history,document:{addEventListener(){},removeEventListener(){},getElementById(){return null;}},setTimeout:()=>0,clearTimeout(){},sessionStorage:{getItem:k=>saved.get(k),setItem:(k,v)=>saved.set(k,v)},requestAnimationFrame:fn=>fn(),Date,Math};
vm.runInNewContext(fs.readFileSync('web/scroll-history.js','utf8'),ctx);
const create=()=>win.StoreScrollHistory({readState:()=>({...view}),restoreState:s=>view=s});
const nav=create();const root=loc.href;
async function move(url,state=null, browserReset=false){loc.href=url;history.state=state;if(browserReset)win.scrollY=0;const ticket=nav.begin();await nav.finish(ticket);return history.state;}
(async()=>{
 const home=await move(root);listeners.wheel({type:'wheel'});win.scrollY=1400;view={filter:'category',loaded:24};listeners.scroll();
 const product=await move(root+'product',null,true);assert.equal(win.scrollY,0);
 listeners.wheel({type:'wheel'});win.scrollY=450;listeners.scroll();
 await move(root,home);assert.equal(win.scrollY,1400);assert.equal(view.loaded,24);
 await move(root+'product',product);assert.equal(win.scrollY,450);
 const repeated=await move(root);assert.equal(win.scrollY,0);assert.notEqual(repeated.storeScrollId,home.storeScrollId);
 await move(root,home);assert.equal(win.scrollY,1400);
 let done;const pending=new Promise(r=>done=r);const stale=nav.begin();const old=nav.finish(stale,pending);
 await move(root+'next');done();await old;assert.equal(win.scrollY,0);
 listeners.wheel({type:'wheel'});win.scrollY=275;listeners.scroll();listeners.pagehide();
 const reloaded=create();await reloaded.finish(reloaded.begin());assert.equal(win.scrollY,275);
 assert.equal(history.scrollRestoration,'manual');
 console.log('Scroll history: back/forward, distinct repeated URLs, restored view state, reload and stale async completion passed');
})().catch(e=>{console.error(e);process.exitCode=1});
