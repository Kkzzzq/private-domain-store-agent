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

// 报告标题：以登记用例名称为主，时间与编号退居次要。
vm.runInContext(fs.readFileSync('web/op-report-names.js','utf8'),context);
const names=context.window.OPReportName;
const run={id:'16a5b0ffffffffffffffffffffffffff',created_at:'2026-10-21T01:24:00',results:[{id:'F11',kind:'functional',status:'passed'}],target:{case_snapshots:[{id:'F11',title:'购物车数量校验'}]}};
assert.equal(names.brief(run),'购物车数量校验');assert.ok(!names.brief(run).includes('测试报告'));
const option=names.label(run,[],{status:'通过',time:true});
assert.ok(option.startsWith('购物车数量校验 · 通过 · '));assert.ok(option.includes('报告 16a5b0'));
assert.equal(names.titleOf({results:[{id:'A08'}]},'A08',[{id:'A08',title:'不可售商品排除'}]),'不可售商品排除');
assert.equal(names.titleOf(run,'F11',[]),'购物车数量校验');
assert.equal(names.brief({results:[]},[]),'无用例记录');
const multi={results:[{id:'F1'},{id:'F2'},{id:'F3'},{id:'F4'}],target:{case_snapshots:[{id:'F1',title:'一'},{id:'F2',title:'二'},{id:'F3',title:'三'},{id:'F4',title:'四'}]}};
assert.equal(names.brief(multi),'一、二、三 等 4 条用例');
assert.equal(names.brief({results:[{id:'X'}]},[]),'X');

// 断言展示：同名同值合并，结果不同的不合并，缺失对照值不再写成通过。
const grouped=api.distinct([
  {name:'仅隔离数据完成下架准备',passed:true,expected:{商品数:4},actual:{下架成功:4}},
  {name:'仅隔离数据完成下架准备',passed:true,expected:{商品数:4},actual:{下架成功:4}},
  {name:'登录成功',passed:true,expected:null,actual:null},
  {name:'登录成功',passed:false,expected:null,actual:null}]);
assert.equal(grouped.length,3);assert.equal(JSON.stringify(grouped.map(row=>row.count)),'[2,1,1]');
const merged=content(api.comparison({name:'仅隔离数据完成下架准备',passed:true,expected:{商品数:4},actual:{下架成功:4}},2));
assert.ok(merged.includes('同类记录 2 条已合并'));assert.ok(!merged.includes('只核对流程结果'));
const process=content(api.comparison({name:'流程前提：商家会话可读',passed:true,expected:null,actual:null},1));
assert.ok(!process.includes('未采集独立值'));assert.ok(process.includes('只核对流程结果'));
const unresolved=content(api.comparison({name:'缺少对照的失败断言',passed:false},1));
assert.ok(unresolved.includes('不能据此判断业务是否正确'));
console.log('OP experience: real counts, evaluator comparison, missing evidence and safe text passed.');
console.log('OP report names and merged assertions passed.');
