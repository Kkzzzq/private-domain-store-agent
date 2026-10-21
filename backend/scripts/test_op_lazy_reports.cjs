const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
class Node{
  constructor(tag){this.tagName=tag;this.children=[];this.attrs={};this.isConnected=true;this.textContent='';}
  append(...nodes){this.children.push(...nodes);}replaceChildren(...nodes){this.children=[...nodes];}
  setAttribute(k,v){this.attrs[k]=v;}
}
const flatten=node=>[node,...(node.children||[]).flatMap(flatten)];
const text=node=>flatten(node).map(n=>n.textContent||'').join(' ');
const context=vm.createContext({window:{},document:{createElement:t=>new Node(t)},sessionStorage:{getItem:()=> 'operator'},crypto:{randomUUID:()=> 'key'}});
vm.runInContext(fs.readFileSync('web/assistant-presentation.js','utf8'),context);
vm.runInContext(fs.readFileSync('web/op-agent-observatory.js','utf8'),context);
(async()=>{
  const host=new Node('main');let requests=0,finish;
  const options={agent:'functional',descriptor:{model:{},tools:[]},capabilities:[],alive:()=>true,refresh:()=>{},runs:[{id:'r1',name:'购物车检查',brief:true,status:'passed',results:[{id:'F11',kind:'functional',status:'passed'}]}],
    loadRun:()=>{requests++;return new Promise(resolve=>finish=resolve);}};
  context.window.OPAgentObservatory.mount(host,options);
  assert.equal(requests,0,'must not download the default report');
  const chooser=flatten(host).find(n=>n.attrs?.['aria-label']==='历史运行');
  assert.equal(chooser.value,'');chooser.value='r1';const loading=chooser.onchange();
  assert.equal(requests,1);assert.ok(text(host).includes('正在下载报告详情'));
  finish({id:'r1',status:'passed',results:[{id:'F11',kind:'functional',status:'passed',evidence:{assertions:[{name:'真实数量',passed:true,expected:2,actual:2}],cleanup_ok:true}}]});
  await loading;assert.ok(text(host).includes('真实数量'));assert.ok(!text(host).includes('正在下载报告详情'));
  console.log('Reports: zero default detail requests, explicit selection and download status passed.');
})().catch(err=>{console.error(err);process.exitCode=1;});
