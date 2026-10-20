const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
class Element{constructor(tag){this.tag=tag;this.children=[];this.events={};}append(...nodes){this.children.push(...nodes);}setAttribute(k,v){this[k]=v;}addEventListener(k,v){this.events[k]=v;}click(){this.events.click?.();}}
const events=[],document={createElement:tag=>new Element(tag),dispatchEvent:event=>events.push(event)};
const context=vm.createContext({window:{},document,CustomEvent:class{constructor(type,options){this.type=type;this.detail=options.detail;}}});
vm.runInContext(fs.readFileSync('web/assistant-actions.js','utf8'),context);
const api=context.window.StoreAssistantActions;
let requested='';const customer=api.toolbar({role:'customer',ask:x=>requested=x,orders(){},shopCode:'nanzhi'});
assert.deepEqual(customer.children.map(x=>x.textContent),['查我的订单','订单中心','订单物流','联系商家','申请售后']);
customer.children[0].click();assert.equal(requested,'查询我的订单');customer.children[3].click();assert.equal(events.at(-1).detail.tab,'chat');
const merchant=api.toolbar({role:'merchant',ask:x=>requested=x,orders(){}});
assert.ok(merchant.children.some(x=>x.textContent==='配置商品'));assert.ok(!merchant.children.some(x=>x.textContent==='联系商家'));assert.ok(!customer.children.some(x=>x.textContent==='经营概览'));
const orders=new Element('div');api.orderActions(orders,'订单 PS202601150001 已支付',{role:'customer',orders(){},shopCode:'nanzhi'});
assert.equal(orders.children.length,1);orders.children[0].children.find(x=>x.textContent==='就此订单联系商家').click();assert.equal(events.at(-1).detail.orderNo,'PS202601150001');
api.orderActions(orders,'没有找到这个订单 PS202601150002',{role:'customer',orders(){}});assert.equal(orders.children.length,1);
console.log('Assistant hub: role menus, queries, order context and support event routing passed.');
