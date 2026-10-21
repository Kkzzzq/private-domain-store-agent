const fs=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const source=fs.readFileSync('web/op-agent-observatory.js','utf8');
const context=vm.createContext({window:{},crypto:{randomUUID:()=> 'fixed-request-key'}});
vm.runInContext(source,context);
const {buildTimeline,advanceDebug}=context.window.OPAgentObservatory;
const result={id:'A02',status:'passed',evidence:{duration_ms:950,budget:{calls:3,tokens:500,models:[{model:'deepseek-flash'}]},cleanup_ok:true,
  requests:[{method:'POST',path:'/api/v1/c/shops/nanzhi/chat',status:200,elapsed_ms:900,input:{message:'查询库存'},output:{intent:'inventory',session_id:'session',mode:'llm',summary_mode:'extractive',
  tools:[{tool:'check_inventory',args:{sku_id:1},result:'<script>unsafe()</script>'}],sources:[{source:'policy',chunk_id:'p1'}],answer:'库存20'}}],
  assertions:[{name:'库存一致',passed:true,expected:20,actual:20},{name:'失败不得覆盖',passed:false,expected:1,actual:2}]}};
const business=buildTimeline(result,'business');
assert.equal(business.budget.calls,3);
assert.equal(business.nodes.filter(node=>node.type==='tool').length,1);
assert.equal(business.nodes.find(node=>node.type==='tool').elapsed,null);
assert.equal(business.nodes.find(node=>node.type==='request').elapsed,900);
assert.equal(business.nodes.find(node=>node.type==='tool').detail.result,'<script>unsafe()</script>');
assert.equal(business.nodes.some(node=>node.type==='assertion'),false);
assert.equal(buildTimeline(result,'evaluator').nodes.filter(node=>node.status==='failed').length,1);
const functional=buildTimeline({id:'F01',evidence:{suite:{reports:[{node:'tests/test_auth.py::test_logout',stage:'call',outcome:'passed'}]}}},'functional');
assert.equal(functional.nodes[0].type,'test');
assert.equal(functional.nodes[0].status,'passed');
assert.equal(buildTimeline({},'business').nodes.length,0);
assert.equal(buildTimeline({evidence:{requests:'[深层数据省略]'}},'business').nodes.length,0);
assert.equal(buildTimeline({evidence:{requests:Array.from({length:700},()=>({path:'/x',status:200}))}},'business').nodes.length,600);
assert.ok(!source.includes('innerHTML'));
assert.ok(!source.includes('eval('));
assert.ok(source.includes('textContent'));
for(const page of ['b.html','c.html'])assert.ok(!fs.readFileSync('web/'+page,'utf8').includes('op-agent-observatory'));
const caps=['qa.assistant.run','qa.approve'];
(async()=>{
  const state={candidate:{id:'C00000000001',revision_digest:'case-digest'}};
  const calls=[];
  let fail=true;
  const api=async(path,body)=>{
    calls.push({path,body});
    if(path==='/plans')return {id:'plan-id',digest:'plan-digest'};
    if(path==='/runs'){
      if(fail){fail=false;throw Error('response lost');}
      return {id:'run-id'};
    }
    return {};
  };
  await assert.rejects(()=>advanceDebug(state,api,[]),/权限/);
  assert.equal(calls.length,0);
  await assert.rejects(()=>advanceDebug(state,api,caps),/response lost/);
  assert.equal(state.planApproved,true);
  assert.equal((await advanceDebug(state,api,caps)).id,'run-id');
  assert.equal(calls.filter(row=>row.path==='/plans').length,1);
  const runCalls=calls.filter(row=>row.path==='/runs');
  assert.equal(runCalls.length,2);
  assert.equal(runCalls[0].body.request_key,runCalls[1].body.request_key);
  await advanceDebug(state,api,caps);
  assert.equal(calls.filter(row=>row.path==='/runs').length,2);
  assert.equal(calls[1].body.environment_id,'isolated-local');
  assert.equal(calls[1].body.mode,'live');
  assert.equal(calls[1].body.max_tokens,60000);
  console.log('Observatory projection, permissions, safe text and idempotent debug passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
