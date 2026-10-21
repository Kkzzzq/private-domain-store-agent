const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
class Node{constructor(tag,cls='',text=''){this.tagName=tag.toUpperCase();this.children=[];this.className=cls;this.textContent=text;this.dataset={};this.classList={add(){}};}append(...nodes){this.children.push(...nodes);}setAttribute(k,v){this[k]=v;}}
const context=vm.createContext({window:{},document:{createElement:tag=>new Node(tag)},WeakMap,Object});
vm.runInContext(fs.readFileSync('web/op-agent-experience.js','utf8'),context);
const api=context.window.OPAgentExperience;
const content=node=>(node.textContent||'')+' '+node.children.map(content).join(' ');
const data={runs:[{id:'r',status:'completed',target:{environment_id:'synthetic'},results:[{id:'A',status:'failed'}]}],plans:[{status:'draft'}],capabilities:{retention:{days:7}}};
const root=new Node('div');api.overview(root,{agents:[],data,go(){}});assert.ok(content(root).includes('三个 Agent'));assert.ok(content(root).includes('含失败或阻塞的报告 1'));
const result={id:'A',status:'failed',evidence:{requests:[{path:'/api/chat',input:{message:'70元买两件'},output:{answer:'错误回答<script>bad()</script>'}}],assertions:[{name:'总价符合',passed:false,expected:70,actual:74}],cleanup_ok:true}};
const focused=api.focus(result,{diagnostic:false,target:{environment_id:'synthetic'}},'evaluator');const text=content(focused);
assert.ok(text.includes('70元买两件'));assert.ok(text.includes('错误回答<script>bad()</script>'));assert.ok(text.includes('失败'));assert.ok(text.includes('74'));
const missing=content(api.focus({id:'F',status:'blocked',evidence:{}},{},'functional'));assert.ok(missing.includes('未采集逐项断言'));assert.ok(!missing.includes('通过 0'));
const source=fs.readFileSync('web/op-agent-experience.js','utf8');assert.ok(!source.includes('innerHTML'));assert.ok(!source.includes('fetch('));
console.log('OP experience: real counts, evaluator comparison, missing evidence and safe text passed.');
