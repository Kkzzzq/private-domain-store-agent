window.OPAgentObservatory = (() => {
  const array = value => Array.isArray(value) ? value : [];
  const object = value => value && typeof value === "object" && !Array.isArray(value) ? value : {};
  const states = new Map();
  let owner;
  const names = {passed:"通过",failed:"失败",blocked:"阻塞",cancelled:"已取消",queued:"排队",running:"运行中",completed:"完成",recorded:"已记录",skipped:"跳过",llm:"真实模型",fallback:"规则回退",direct:"直接查询"};
  const label = value => names[value] || value || "未采集";
  function buildTimeline(result, agent) {
    const evidence=object(result?.evidence), nodes=[];
    const add=(type,title,detail,status="recorded",elapsed=null)=>{
      if(nodes.length<600)nodes.push({id:String(nodes.length),type,title,detail,status,elapsed});
    };
    if(agent==="functional")for(const report of array(evidence.suite?.reports)){
      add("test",`${report.stage||"执行"} · ${report.node||result.id}`,report,report.outcome);
    }
    for(const request of array(evidence.requests)){
      const response=object(request.output), input=object(request.input);
      add("request",`${request.method||"请求"} ${request.path||"未采集路径"}`,request,
        Number(request.status)>=400?"failed":"recorded",typeof request.elapsed_ms==="number"?request.elapsed_ms:null);
      if(String(request.path||"").endsWith("/chat")){
        if(input.message)add("input","用户输入",{message:input.message,session_id:input.session_id});
        if(response.intent)add("intent","识别结果 · "+response.intent,{intent:response.intent,mode:response.mode,
          note:"响应中记录的意图，不代表模型内部思维链。"});
        if(response.session_id)add("memory","会话与摘要模式",{session_id:response.session_id,
          summary_mode:response.summary_mode||"未采集",note:"未采集完整记忆快照；不据此声称存在长期记忆。"});
        for(const tool of array(response.tools))add("tool","工具 · "+tool.tool,tool);
        if(array(response.sources).length)add("knowledge","本轮知识引用",{sources:response.sources,
          retrieval_mode:response.retrieval_mode,embedding_model:response.embedding_model,
          note:"来源于本轮响应，未采集知识检索与工具之间的独立时间关系。"});
        if(response.answer)add("answer","最终回答",{answer:response.answer,products:response.products,
          chat_models:response.chat_models,mode:response.mode});
      }
    }
    if(agent!=="business")for(const check of array(evidence.assertions)){
      add("assertion",check.name||"硬断言",check,check.passed===true?"passed":"failed");
    }
    if(evidence.error)add("error","执行异常",{error:evidence.error},result.status);
    return {nodes,truncated:nodes.length===600,budget:object(evidence.budget),
      assertions:array(evidence.assertions),facts:evidence.facts,cleanup:evidence.cleanup_ok,
      models:array(evidence.budget?.models),duration:typeof evidence.duration_ms==="number"?evidence.duration_ms:null};
  }
  async function advanceDebug(state, api, capabilities) {
    if(!capabilities.includes("qa.assistant.run")||!capabilities.includes("qa.approve"))throw Error("需要运行助手与审批权限");
    if(!state.candidate)throw Error("请先保存并核对候选定义");
    if(!state.caseApproved){
      await api(`/cases/${state.candidate.id}/approve`,{digest:state.candidate.revision_digest});
      state.caseApproved=true;
    }
    if(!state.plan)state.plan=await api("/plans",{goal:"可视化合成对话调试",kind:"assistant",mode:"live",planner:"fixed",
      environment_id:"isolated-local",case_ids:[state.candidate.id],max_calls:20,max_tokens:60000,timeout_seconds:600});
    if(!state.planApproved){await api(`/plans/${state.plan.id}/approve`,{digest:state.plan.digest});state.planApproved=true;}
    if(!state.requestKey)state.requestKey=crypto.randomUUID();
    if(!state.run)state.run=await api("/runs",{plan_id:state.plan.id,request_key:state.requestKey});
    return state.run;
  }
  function mount(host, options) {
    if(options.agent==="business"){
      if(window.OPBusinessObservatory)return window.OPBusinessObservatory.mount(host,options);
      const notice=document.createElement("p");notice.textContent="业务对话模块未加载，请刷新页面重试。";host.append(notice);return;
    }
    const identity=sessionStorage.getItem("token_op");
    if(identity!==owner){states.clear();owner=identity;}
    const agent=options.agent;
    if(!states.has(agent))states.set(agent,{view:"replay",turns:[{message:"",expected:"",tool:""}],role:"customer",debug:{}});
    const state=states.get(agent),root=document.createElement("section");root.className="ao-workspace";host.append(root);
    state.runId=null;state.caseId=null;state.nodeId=null;state.loadingRun=null;
    const valid=()=>root.isConnected&&sessionStorage.getItem("token_op")===identity&&options.alive();
    const el=(tag,cls,text)=>{const node=document.createElement(tag);if(cls)node.className=cls;if(text!=null)node.textContent=String(text);return node;};
    const button=(text,callback,disabled=false)=>{const node=el("button","",text);node.type="button";node.disabled=disabled;node.onclick=callback;return node;};
    const text=value=>typeof value==="string"?value:JSON.stringify(value??null,null,2);
    const json=value=>el("pre","ao-json",text(value).slice(0,100000));
    function answer(value){
      const content=window.AssistantPresentation.clean(value),node=el("div","ao-answer");let offset=0;
      for(const match of content.matchAll(/\*\*([^*\n]+)\*\*|`([^`\n]+)`/g)){
        node.append(document.createTextNode(content.slice(offset,match.index)),el(match[1]?"strong":"code","",match[1]||match[2]));offset=match.index+match[0].length;
      }
      node.append(document.createTextNode(content.slice(offset)));return node;
    }
    const api=async(path,body)=>{if(!valid())throw Error("页面或身份已变化");return options.api(path,body);};
    async function act(callback){
      if(state.busy)return;state.busy=true;state.error="";draw();
      try{await callback();}catch(error){if(valid())state.error=error.message;}
      finally{
        state.busy=false;
        if(state.refreshRequested&&options.alive()&&sessionStorage.getItem("token_op")===identity){state.refreshRequested=false;await options.refresh();}
        else if(valid())draw();
      }
    }
    function field(caption,control){const wrapper=el("label","ao-field");control.setAttribute("aria-label",caption);wrapper.append(el("span","",caption),control);return wrapper;}
    function select(items,value,change){const node=el("select");for(const item of items){const option=el("option","",item.title);option.value=item.id;node.append(option);}node.value=value;node.onchange=()=>change(node.value);return node;}
    function debugPanel() {
      const panel=el("section","ao-debug");panel.append(el("h4","","合成对话调试"),el("p","ao-muted","先保存候选核对，再批准执行。真实模型会消耗额度；仅独立合成店铺，不操作实际店铺。"));
      const locked=Boolean(state.debug.candidate),allowed=options.capabilities.includes("qa.assistant.run");
      const role=select([{id:"customer",title:"合成买家 alice"},{id:"merchant",title:"合成商家 merchant"}],state.role,value=>state.role=value);role.disabled=locked||state.busy;panel.append(field("测试身份",role));
      state.turns.forEach((turn,index)=>{
        const block=el("div","ao-turn"),message=el("textarea"),expected=el("input");
        message.value=turn.message;message.maxLength=1000;message.rows=2;message.disabled=locked||state.busy;message.oninput=()=>turn.message=message.value;
        expected.value=turn.expected;expected.maxLength=100;expected.disabled=locked||state.busy;expected.oninput=()=>turn.expected=expected.value;
        const tool=select([{id:"",title:"不指定工具"},...(options.descriptor.tools||[]).map(name=>({id:name,title:name}))],turn.tool,value=>turn.tool=value);tool.disabled=locked||state.busy;
        block.append(field(`第 ${index+1} 轮问题`,message),field("回答应包含（或选择必需工具）",expected),field("必需成功工具",tool));panel.append(block);
      });
      panel.append(button("增加一轮",()=>{state.turns.push({message:"",expected:"",tool:""});draw();},locked||state.busy||state.turns.length>=5));
      panel.append(button("保存调试候选",()=>act(async()=>{
        const turns=state.turns.map(turn=>({message:turn.message.trim(),expected_contains:turn.expected.trim()?[turn.expected.trim()]:[],required_tools:turn.tool?[turn.tool]:[]}));
        if(turns.some(turn=>turn.message.length<2||(!turn.expected_contains.length&&!turn.required_tools.length)))throw Error("每轮至少两字问题，并填写预期文字或必需工具");
        state.debug.candidate=await api("/cases",{title:"OP可视化对话调试",role:state.role,turns});
      }),locked||state.busy||!allowed));
      if(state.debug.candidate){
        const definition=el("details");definition.open=!state.debug.run;
        definition.append(el("summary","","冻结的调试定义（点击核对）"),json(state.debug.candidate.definition));
        panel.append(el("p","ao-muted","候选已冻结 · "+state.debug.candidate.id),definition);
        panel.append(button(state.debug.run?"运行已创建":"批准并运行（消耗额度）",()=>act(async()=>{
          if(!await window.OPDialogs.confirm("批准当前冻结定义与隔离计划，并使用服务端配置的模型执行？最多20次调用、60000 tokens；不操作实际店铺。"))return;
          const run=await advanceDebug(state.debug,api,options.capabilities);state.runId=run.id;state.caseId=null;
          state.refreshRequested=true;
        }),state.busy||Boolean(state.debug.run)||!options.capabilities.includes("qa.approve")||!allowed));
        if(state.debug.plan)panel.append(el("p","ao-muted","计划回执 · "+state.debug.plan.id));
        if(state.debug.run)panel.append(el("p","ao-muted","运行回执 · "+state.debug.run.id));
        panel.append(button("新建另一份调试",()=>{state.debug={};draw();},state.busy));
      }
      return panel;
    }
    function draw(){
      if(!valid())return;root.replaceChildren();
      const tabs=el("div","ao-tabs");
      for(const [id,title] of [["replay","执行回放"],["configuration","能力配置"],["boundaries","使用边界"]]){
        const node=button(title,()=>{state.view=id;draw();});node.setAttribute("aria-pressed",String(state.view===id));tabs.append(node);
      }
      root.append(tabs);
      const help=el("details");
      help.append(el("summary","","这些功能是什么意思？"));
      for(const text of [agent==="evaluator"?"评测对象是业务Agent：模拟用户提问，检查助手的回答、工具调用和权限是否满足预期。":"功能测试对象是业务功能：实际验证接口、数据库和页面，不把助手说成功当成测试通过。",
        "执行回放：查看已经发生的记录，不会重新测试。能力配置：当前服务的模型和工具，只读，不代表历史运行配置。使用边界：查看权限及隔离范围。",
        "历史运行是一份报告，里面可以有多条用例；下方用例只切换本报告的场景，不会重新执行。setup＝准备，call＝执行，teardown＝收尾，属于同一个用例。",
        "通过＝执行并满足预期；失败＝实际结果不符；阻塞＝模型、依赖或预算等导致未完成。平台诊断/旧记录不是正式真实模型测试的通过证明。",
        "规划调用是测试Agent制订计划的模型请求；执行调用是所选用例实际请求模型的次数。接口/页面测试执行调用为0可以正常。tokens是模型用量，未采集不等于0。",
        "步骤证据是选中步骤的输入、输出和耗时。HTTP是接口请求，JSON是技术原始记录，不是客服回答。清理成功只表示释放测试资源，不表示用例通过。"] )help.append(el("p","ao-muted",text));
      root.append(help);
      if(state.error)root.append(el("p","qa-error",state.error));
      if(state.view==="configuration"){
        root.append(el("h3","","当前服务配置（只读，不代表历史运行）"),json({model:options.descriptor.model,
          tools:options.descriptor.tools,guardrails:options.descriptor.guardrails}),el("p","ao-muted","提示词编辑、完整记忆维护、长期画像和拖拽编排未在本批开放。运行实际模型请看运行预算记录。"));return;
      }
      if(state.view==="boundaries"){
        root.append(el("h3","","先区分配置、记录与判定"),el("p","","业务助手负责回答，评测执行器负责硬断言，功能执行器负责接口/数据库/浏览器验证；同一问题可关联三类证据，但不共享一个虚构的通过率。"),el("p","","本页只读所选报告的执行证据，真实店铺或隔离副本以报告环境为准，不展示模型内部思维链。工具、记忆和知识没有独立时间戳时仅展示记录，不伪造耗时或先后关系。"),el("p","","保存候选不调用模型，明确批准才会创建真实执行。审批或启动失败后重试继续既有回执；已启动任务不会因刷新重复执行。"));return;
      }
      const runs=options.runs.filter(run=>array(run.results).some(result=>result.kind===(agent==="functional"?"functional":"assistant")));
      const run=runs.find(item=>item.id===state.runId);
      const resultRows=array(run?.brief?[]:run?.results).filter(row=>row.kind===(agent==="functional"?"functional":"assistant"));
      const result=resultRows.find(row=>row.id===state.caseId)||resultRows[0];if(result)state.caseId=result.id;
      const projected=buildTimeline(result,agent);
      const selected=projected.nodes.find(node=>node.id===state.nodeId)
        ||projected.nodes.find(node=>agent==="business"?node.type==="input":node.type==="assertion"&&node.status==="failed")||projected.nodes[0];
      state.nodeId=selected?.id;
      const top=el("div","ao-summary");top.append(el("strong","",agent==="business"?"业务对话与工具轨迹":agent==="evaluator"?"评测步骤与判定依据":"功能执行与业务核验"));
      top.append(button("刷新回放",options.refresh,state.busy));root.append(top);
      if(run){
        const metrics=el("p","ao-muted");metrics.textContent=`运行 ${run.id.slice(0,8)} · ${label(run.status)} · ${run.diagnostic===false?"正式真实模型测试":"平台诊断/旧记录"} · 用例 ${result?.id||"—"} · ${projected.duration==null?"总耗时未采集":projected.duration+"ms"} · 规划模型HTTP调用 ${run.planning?.budget?.calls??"未采集"} · 本用例执行模型HTTP调用 ${projected.budget.calls??"未采集"} · 执行tokens ${projected.budget.tokens??"未采集"}${projected.budget.estimated?"（估算）":""}${projected.budget.uncertain?"（调用结果未知）":""}`;root.append(metrics);
      }
      const grid=el("div","ao-grid"),left=el("section","ao-column"),middle=el("section","ao-column"),right=el("section","ao-column");
      left.append(el("h4","","选择报告与测试场景"));
      if(agent==="business")left.append(debugPanel());
      left.append(field("历史运行",select([{id:"",title:"请选择报告，点击后下载详情"},...runs.map(item=>({id:item.id,title:(item.name||item.id.slice(0,8))+" · "+label(item.status)}))],state.runId||"",async value=>{
        state.runId=value;state.caseId=null;state.nodeId=null;state.error="";state.loadingRun=value||null;draw();
        if(!value)return;
        try{const full=await (options.loadRun?options.loadRun(value):api(`/runs/${encodeURIComponent(value)}`));const index=options.runs.findIndex(item=>item.id===value);if(index>=0)options.runs[index]={...full,name:options.runs[index].name};}
        catch(error){if(valid())state.error=error.message;}
        finally{if(state.loadingRun===value)state.loadingRun=null;if(valid())draw();}
      })));
      if(state.loadingRun){const notice=el("p","ao-muted","正在下载报告详情…");notice.setAttribute("role","status");notice.setAttribute("aria-live","polite");left.append(notice);}
      if(run&&!run.brief&&result){
        left.append(field("用例",select(resultRows.map(row=>({id:row.id,title:row.id+" · "+label(row.status)})),result.id,value=>{state.caseId=value;state.nodeId=null;draw();})));
        const target=run.target||{};left.append(el("p","ao-muted",`环境 ${target.environment_id||"未采集"} · fixture ${target.fixture_version||"未采集"}`));
        const snapshot=array(target.case_snapshots).find(row=>row.id===result.id);
        if(snapshot)left.append(el("p","",snapshot.title));
        if(array(result.doc?.steps).length){left.append(el("h4","","本用例具体做什么"));for(const step of result.doc.steps)left.append(el("p","ao-muted",step));}
        if(array(result.doc?.expected).length){left.append(el("h4","","满足哪些条件才算通过"));for(const expected of result.doc.expected)left.append(el("p","ao-muted",expected));}
      }else if(!state.loadingRun)left.append(el("p","ao-muted",runs.length?"报告详情尚未下载，请先选择要查看的报告。":"暂无对应运行。评测/功能页可使用计划入口创建运行。"));
      middle.append(el("h4","","执行步骤（点击查看详情）"),el("p","ao-muted","这里是实际请求和检查记录，不是模型思维过程。按请求记录展开；同一请求内的工具仅有顺序，未采集独立耗时。"));
      for(const node of projected.nodes){
        const item=button(`${Number(node.id)+1}. ${node.title}`,()=>{state.nodeId=node.id;draw();});
        item.className="ao-node ao-"+node.status;item.setAttribute("aria-pressed",String(state.nodeId===node.id));
        item.append(el("small","",label(node.status)+(node.elapsed==null?" · 独立耗时未采集":" · "+node.elapsed+"ms")));middle.append(item);
      }
      if(!projected.nodes.length)middle.append(el("p","ao-muted",run?"尚无执行步骤证据，不能据此判断通过。":"选择运行后显示实际执行步骤。"));
      if(projected.truncated)middle.append(el("p","ao-muted","步骤较多，仅展示前600项；完整证据请查看原运行报告。"));
      right.append(el("h4","","所选步骤的实际输入与结果"));
      if(selected){
        right.append(el("h4","",selected.title));
        if(selected.type==="answer")right.append(answer(selected.detail.answer));
        if(selected.type==="input")right.append(el("p","ao-answer",selected.detail.message));
        if(selected.type==="request")right.append(el("p","ao-muted",`接口返回状态 ${selected.detail.status??"未采集"}；2xx表示接口请求成功，不代表整个测试用例通过。`));
        if(selected.type==="test")right.append(el("p","ao-muted","这是测试程序的一个阶段：setup准备数据，call执行业务验证，teardown负责收尾；具体业务检查见左侧步骤和通过条件。"));
        if(selected.type==="assertion")right.append(el("p","ao-muted",selected.detail.passed===true?"此项实际结果符合预期。":"此项实际结果未满足预期，请对照expected（预期）与actual（实际）。"));
        const raw=el("details");raw.append(el("summary","","技术原始记录（输入 / 输出 / 预期 / 实际）"),json(selected.detail));right.append(raw);
      }
      if(result){
        if(run.planning){const planning=el("details");planning.append(el("summary","","真实模型规划轨迹与用量"),json(run.planning));right.append(planning);}
        const details=el("details","ao-checks");details.append(el("summary","",`硬断言 ${projected.assertions.filter(row=>row.passed===true).length}/${projected.assertions.length} · 清理 ${projected.cleanup===true?"成功":projected.cleanup===false?"未确认成功":"未确认"}`),json(projected.assertions));right.append(details);
        if(projected.facts!=null){const facts=el("details");facts.append(el("summary","","业务核查事实"),json(projected.facts));right.append(facts);}
        if(projected.models.length){const models=el("details");models.append(el("summary","","实际模型HTTP记录（不等于工具次数）"),json(projected.models));right.append(models);}
        const target=el("details");target.append(el("summary","","批准的执行范围 / 版本"),json(run.target));right.append(target);
      }
      grid.append(left,middle,right);root.append(grid);
    }
    draw();
  }
  return {mount,buildTimeline,advanceDebug};
})();
