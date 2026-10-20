const fs=require('node:fs'), vm=require('node:vm'), assert=require('node:assert/strict');
const source=fs.readFileSync('web/c.js','utf8');
class Element {
  constructor(tag,cls='',text=''){this.tag=tag;this.className=cls;this.textContent=text;this.children=[];this.events={};this.style={};this.disabled=false;this.classList={add(){},remove(){}};}
  append(...nodes){this.children.push(...nodes);}
  addEventListener(type,callback){this.events[type]=callback;}
  setAttribute(name,value){this[name]=value;}
  remove(){this.removed=true;}
  async click(){if(!this.disabled)await this.events.click?.({target:this});}
}
function all(node){return [node,...node.children.flatMap(all)];}
function setup(){
 const body=new Element('body'); let token='a',resolve;
 const context=vm.createContext({console,code:'nanzhi',cartCount:0,requireLogin:()=>true,
 sessionStorage:{getItem(){return token;},setItem(){}},document:{body,createElement:tag=>new Element(tag)},
 h:(...args)=>new Element(...args),cover:x=>x,money:x=>String(x),toast(){},render(){},go(){},calls:0,
 api:()=>{context.calls++;return new Promise(r=>resolve=r);}});
 context.switch=()=>{token='b';};context.finish=()=>resolve({items:[{quantity:1}]});
 vm.runInContext(source.slice(source.indexOf('function quickBuy('),source.indexOf('/* ---------------- 商品详情')),context);
 return {context,body};
}
(async()=>{
 const product={name:'杯子',category:'餐具',image_url:'',skus:[{id:1,spec:'有货',price_yuan:12,stock:5,purchasable:true},{id:2,spec:'缺货',price_yuan:10,stock:0,purchasable:false}]};
 const {context:c,body}=setup();c.quickBuy(product);const nodes=all(body), add=nodes.find(n=>n.textContent==='加入购物车'), buy=nodes.find(n=>n.textContent==='立即购买');
 await nodes.find(n=>n.textContent==='缺货').click();assert.equal(add.disabled,true);assert.equal(buy.disabled,true);
 await nodes.find(n=>n.textContent==='有货').click();assert.equal(add.disabled,false);
 const pending=add.click();assert.equal(add.disabled,true);await add.click();assert.equal(c.calls,1);c.finish();await pending;
 const inFlight=setup();inFlight.context.quickBuy(product);const sending=all(inFlight.body).find(n=>n.textContent==='加入购物车').click();inFlight.context.switch();inFlight.context.finish();await sending;assert.equal(inFlight.context.cartCount,0);
 const switched=setup();switched.context.quickBuy(product);switched.context.switch();await all(switched.body).find(n=>n.textContent==='加入购物车').click();assert.equal(switched.context.calls,0);
 // Card requests read live details and reject responses after an account switch.
 const card=setup(), log=new Element('log');card.context.log=log;card.context.requireLogin=()=>true;
 vm.runInContext(source.slice(source.indexOf('  const appendCards = (products) => {'),source.indexOf('  chatLines.forEach((line) => {'))+'\nthis.drawCards=appendCards;',card.context);
 card.context.drawCards([{id:1,name:'杯子',price_from:12}]);const button=all(log).find(n=>n['aria-label']);assert.ok(button);
 const request=button.click();card.context.switch();card.context.finish();await request;
 assert.equal(card.body.children.length,0);
 console.log('Agent purchase: unavailable SKU, repeated click, stale identity and live-detail request passed.');
})().catch(e=>{console.error(e);process.exitCode=1;});
