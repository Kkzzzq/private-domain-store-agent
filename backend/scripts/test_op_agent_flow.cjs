const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
class Element{
  constructor(tag){this.tagName=tag;this.children=[];this.textContent='';this.classList={add(){}};this.style={setProperty(){}};this.attributes={};}
  append(...nodes){this.children.push(...nodes);}
  setAttribute(name,value){this.attributes[name]=value;}
  querySelector(){return null;}
  querySelectorAll(){return [];}
}
const context=vm.createContext({window:{},document:{createElement:tag=>new Element(tag)}});
const source=fs.readFileSync('web/op-agent-flow.js','utf8');
vm.runInContext(source,context);
const flatten=node=>[node,...node.children.flatMap(flatten)];
for(const [id,count] of [['business',3],['functional',4],['evaluator',3]]){
  const root=new Element('main');
  context.window.OPAgentFlow.mount(root,id);
  const nodes=flatten(root),buttons=nodes.filter(node=>node.tagName==='button'&&node.className==='af-step-button');
  assert.equal(buttons.length,count,id);
  const hint=nodes.find(node=>node.attributes.role==='status');
  const original=hint.textContent;
  buttons.at(-1).onclick();
  assert.notEqual(hint.textContent,original,'missing prerequisites must give guidance, not fake completion');
  assert.ok(hint.textContent.length>10);
  assert.ok(nodes.some(node=>node.textContent==='第一次使用，从这里开始'));
  assert.ok(nodes.some(node=>node.textContent==='全部功能说明、费用与失败处理'));
}
assert.ok(!source.includes('innerHTML'));
assert.ok(!source.includes('fetch('));
assert.ok(!source.includes('aria-current'));
console.log('Agent flow: distinct 3/4/3 steps, missing prerequisite guidance, no fake progress or network writes passed.');
