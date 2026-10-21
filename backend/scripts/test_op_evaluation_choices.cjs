const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
class Node{constructor(tag,text){this.tag=tag;this.textContent=text||'';this.children=[];this.index=0;}append(...nodes){this.children.push(...nodes);}get value(){return this.tag==='select'?this.children[this.index]?.value||'':this.val||'';}set value(v){this.val=v;}set selectedIndex(v){this.index=v;}}
const all=n=>[n,...n.children.flatMap(all)],text=n=>all(n).map(x=>x.textContent).join(' ');
const code=fs.readFileSync('web/op-agent-quality.js','utf8');
const body=code.slice(code.indexOf('    function comparePanel(rows){'),code.indexOf('    function heldoutPanel(){'));
const context=vm.createContext({el:(tag,text)=>new Node(tag,text),select:()=>new Node('select'),btn:(text,fn)=>Object.assign(new Node('button',text),{onclick:fn}),stamp:x=>x,labels:{},job:()=>{}});
vm.runInContext(body+';this.panel=comparePanel;',context);
for(const count of [0,1,2]){const panel=context.panel(Array.from({length:count},(_,i)=>({id:'report'+i,created_at:'now',program:{decision:'passed'}})));
 const selects=all(panel).filter(n=>n.tag==='select');assert.equal(selects.length,count<2?0:2);
 if(count===0)assert.ok(text(panel).includes('暂无独立评测'));
 if(count===1)assert.ok(text(panel).includes('至少两份'));
 if(count===2){const button=all(panel).find(n=>n.tag==='button');assert.equal(button.disabled,false);selects[1].selectedIndex=0;selects[1].onchange();assert.equal(button.disabled,true);}
}
console.log('Evaluation comparison: empty/single-record guidance, distinct selection and duplicate prevention passed.');
