const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('web/op-quality.js','utf8');
const definition=source.match(/function requestTimeout\(path\) \{[\s\S]*?\n  \}/)[0];
const context=vm.createContext({});vm.runInContext(definition,context);
for(const path of ['/functional-intake','/business-debug','/agent-quality/evaluations/id/model-score','/runs/id','/agent-quality/evaluations/id/detail']){
  assert.equal(vm.runInContext(`requestTimeout(${JSON.stringify(path)})`,context),120000,path);
}
assert.equal(vm.runInContext('requestTimeout("/agent-quality/evaluations/id/defect-benchmark")',context),1250000);
assert.equal(vm.runInContext('requestTimeout("/cases")',context),30000);
assert.ok(source.includes('requestTimeout(path)'));
const wrapper=source.match(/const api=async\(path,body,method="POST"\)=>\{[\s\S]*?\n    \};/)[0];
const timers=[],requests=[];
Object.assign(context,{valid:()=>true,AbortController,setTimeout:(callback,delay)=>{timers.push(delay);return timers.length;},clearTimeout:()=>{},options:{api:async(path,options)=>{requests.push({path,options});return 'ok';}}});
vm.runInContext(wrapper,context);
(async()=>{
  await vm.runInContext('api("/functional-intake",{requirement:"购物车"})',context);
  await vm.runInContext('api("/agent-quality/evaluations/id/defect-benchmark",{})',context);
  await vm.runInContext('api("/cases")',context);
  assert.deepEqual(timers,[120000,1250000,30000]);
  assert.equal(requests[0].options.method,'POST');
  assert.equal(requests[0].options.body,'{"requirement":"购物车"}');
  assert.ok(requests.every(request=>request.options.signal instanceof AbortSignal));
})().catch(error=>{console.error(error);process.exitCode=1;});
console.log('Agent timeouts: inline model jobs outlive their server deadline, bounded benchmark, normal requests unchanged passed.');
