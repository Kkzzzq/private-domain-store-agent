window.OPQuality = (() => {
  const names = {assistant:"业务 Agent 评测",functional:"业务功能测试",joint:"联合回归",rules:"规则 / 固定回归",live:"真实云端模型",candidate:"候选未接入",active:"已接入",queued:"排队",planning:"AI规划排队",planning_running:"AI规划中",draft:"待批准",approved:"已批准",running:"运行中",completed:"执行完成",passed:"通过",failed:"失败",blocked:"阻塞",cancelled:"已取消",eligible:"满足本次范围门禁",not_eligible:"不满足门禁",not_selected:"未在这侧运行"};
  const label = value => names[value] || value;
  const el = (tag, cls, text) => { const node=document.createElement(tag); if(cls)node.className=cls; if(text!=null)node.textContent=String(text); return node; };
  const button = (text, action, primary=false) => { const node=el("button",primary?"qa-primary":"",text); node.type="button"; node.onclick=action; return node; };
  const pre = value => el("pre","qa-json",typeof value==="string"?value:JSON.stringify(value,null,2));
  function answer(text){
    const node=el("div","qa-answer");const content=String(text||"");let offset=0;
    for(const match of content.matchAll(/\*\*([^*\n]+)\*\*|`([^`\n]+)`/g)){
      node.append(document.createTextNode(content.slice(offset,match.index)),el(match[1]?"strong":"code","",match[1]||match[2]));offset=match.index+match[0].length;
    }
    node.append(document.createTextNode(content.slice(offset)));return node;
  }
  function mount(host, options) {
    const root=el("section","qa-workspace"); host.replaceChildren(root);
    const identity=sessionStorage.getItem("token_op");
    const valid=()=>root.isConnected&&sessionStorage.getItem("token_op")===identity;
    let data, selectedRun, selectedCase, selectedPlan, pending=false, filter="active", timer, comparison, flash;
    const api=async(path,body,method="POST")=>{if(!valid())throw Error("账号或页面已变化");return options.api(path,body?{method,body:JSON.stringify(body)}:{});};
    const error=message=>{if(valid()){const notice=el("p","qa-error",message);root.prepend(notice);}};
    const can=cap=>data?.capabilities.capabilities.includes(cap);
    const canRun=kind=>kind==="joint"?can("qa.assistant.run")&&can("qa.functional.run"):can(`qa.${kind}.run`);
    async function refresh(){
      try{const [capabilities,cases,plans,runs]=await Promise.all([api("/capabilities"),api("/cases"),api("/plans"),api("/runs")]);if(!valid())return;data={capabilities,cases,plans,runs};paint();poll();}
      catch(err){error(err.message);}
    }
    function poll(){
      clearTimeout(timer);
      if(!valid())return;
      const active=data.runs.some(run=>["queued","running"].includes(run.status))||data.plans.some(plan=>["planning","planning_running"].includes(plan.status));
      if(active)timer=setTimeout(()=>{if(valid()&&!pending&&!root.querySelector("dialog[open]"))refresh();else if(valid())poll();},1500);
    }
    async function action(callback){if(pending)return;pending=true;try{await callback();await refresh();}catch(err){error(err.message);}finally{pending=false;}}
    function badge(value){return el("span",`qa-badge qa-${value}`,label(value));}
    function heading(title,description){const node=el("div","qa-heading");const copy=el("div");copy.append(el("h2","",title),el("p","",description));node.append(copy);return node;}
    function paint(){
      if(!valid())return;root.replaceChildren();
      if(flash){root.append(el("p","qa-notice",flash));flash=null;}
      root.append(el("p","qa-environment","业务数据：独立合成SQLite / 内存Redis，每条用例单独子进程。真实模式使用云端聊天模型；RAG用例使用独立Embedding与Chroma。原生MySQL/Redis业务联调和浏览器E2E仍另行验收。"));
      const top=heading("智能测试中心","工具轨迹、业务事实和固定断言决定结果，模型不能自行宣布通过。");
      const controls=el("div","qa-actions");const joint=button("新建联合回归",()=>compose("joint"),true);joint.disabled=!can("qa.assistant.run")||!can("qa.functional.run");controls.append(joint,button("刷新",refresh));if(data.runs.length>=2)controls.append(button("版本报告对比",compareDialog));if(can('qa.approve'))controls.append(button("历史保留与清理",retentionDialog));top.append(controls);root.append(top);
      if(comparison){const dimension={environment_id:"测试环境",fixture_version:"fixture版本",mode:"执行模式",unfinished_run:"运行未结束"};const panel=el('section','qa-card');panel.append(el('h3','','报告差异'),el('p','qa-muted',comparison.note));if(comparison.incompatible_dimensions.length)panel.append(el('p','qa-error','不可比维度：'+comparison.incompatible_dimensions.map(key=>dimension[key]||key).join('、')));for(const row of comparison.cases){const reason=row.before==='not_selected'?'仅候选运行包含，单列不计入回归判定':row.after==='not_selected'?'仅基线运行包含，单列不计入回归判定':'用例版本或条件不同，不可比较';panel.append(el('p','',`${row.id}：${label(row.before)} → ${label(row.after)} · ${row.comparable?row.transition==='regressed'?'发生回归':row.transition==='improved'?'已改善':'未变化':reason}`));}root.append(panel);}
      if(options.tab==="testing-overview"){renderOverview();return;}
      if(options.tab==="testing-cases"){renderCases();return;}
      if(options.tab!=="testing-runs")renderCapabilities();
      renderPlans();renderRuns();
      if(selectedPlan)renderPlan(data.plans.find(plan=>plan.id===selectedPlan));
      if(selectedRun)renderRun(data.runs.find(run=>run.id===selectedRun));
    }
    function renderOverview(){
      const business=el("article","qa-card");
      business.append(el("h3","","业务 Agent"),el("p","","服务买家与商家的商品咨询、推荐、订单查询及受控业务提案。测试入口仅供 OP 使用，业务助手仍在 B/C。"),el("p","qa-muted","实现存在不等于全量验收通过；原生业务依赖、浏览器E2E及全部助手场景仍需逐项验收。"));
      root.append(business);renderCapabilities();
      const summary=el("section","qa-card");summary.append(el("h3","","执行与验收分开统计"));
      for(const kind of ["assistant","functional"]){
        const relevant=data.runs.filter(run=>run.kind===kind||run.kind==="joint");
        summary.append(el("p","",`${label(kind)}：最近加载 ${relevant.length} 次相关运行；已接入数量不是通过数量，结论请以对应环境的报告和逐条断言为准。`));
      }
      summary.append(el("p","qa-muted",`目录版本：${data.capabilities.catalog_version}`));root.append(summary);renderRuns();
    }
    function renderCapabilities(){
      const cards=el("div","qa-capability-grid");
      for(const kind of ["assistant","functional"]){
        const all=data.cases.filter(row=>row.kind===kind),ready=all.filter(row=>row.state==="active");
        const card=el("article","qa-card");card.append(el("h3","",kind==="assistant"?"助手评测 Agent":"功能测试 Agent"),
          el("p","",kind==="assistant"?"被测：买家 / 商家业务助手的回答、工具调用与权限。":"被测：业务API、状态机、库存与金额等确定性约束。"),
          el("p","qa-count",`${ready.length} 已接入 / ${all.length} 规划目标`),
          el("p","qa-muted",kind==="assistant"?"对话 → 工具轨迹 → 可信快照 → 断言":"审核场景 → 隔离接口步骤 → 状态变化 → 断言"));
        const create=button(`新建${label(kind)}`,()=>compose(kind),true);create.disabled=!can(`qa.${kind}.run`);card.append(create);cards.append(card);
      }
      root.append(cards);
    }
    function renderCases(){
      const toolbar=el("div","qa-actions");for(const value of ["active","candidate","all"])toolbar.append(button(value==="all"?"全部规划":label(value),()=>{filter=value;paint();}));root.append(toolbar);
      if(can('qa.assistant.run'))toolbar.append(button('新增助手用例',()=>caseDialog(),true));
      const list=el("div","qa-case-library");
      for(const row of data.cases.filter(row=>filter==="all"||row.state===filter)){
        const item=el("div","qa-case-row");item.append(el("strong","",`${row.id} ${row.title}`),el("span","qa-muted",`${label(row.kind)} · v${row.version} · ${row.adapter}`),badge(row.state));
        if(row.adapter==='declarative_assistant'){if(can('qa.assistant.run'))item.append(button(row.state==='candidate'?'编辑候选':'新建版本',()=>caseDialog(row)));if(can('qa.approve')&&row.state==='candidate')item.append(button('审核启用',()=>action(()=>api(`/cases/${row.id}/approve`,{digest:row.revision_digest}))));if(can('qa.approve')&&row.state==='active')item.append(button('撤销启用',()=>action(()=>api(`/cases/${row.id}/revoke`,{}))));}list.append(item);
      }root.append(list);
    }
    function renderPlans(){
      const section=el("section","qa-card");section.append(el("h3","","计划与审批"));
      if(!data.plans.length)section.append(el("p","qa-muted","尚无计划。选择已接入用例，先生成并审核，再启动运行。"));
      for(const plan of data.plans.slice(0,6)){
        const row=el("div","qa-case-row");row.append(button(plan.payload.goal,()=>{selectedPlan=plan.id;paint();}),badge(plan.status),el("span","qa-muted",`${label(plan.payload.kind)} · ${plan.payload.case_ids.length}条 · ${label(plan.payload.mode)}`));section.append(row);
      }root.append(section);
    }
    function renderPlan(plan){
      if(!plan)return;const section=el("section","qa-card qa-plan-detail");section.append(el("h3","",plan.payload.goal),badge(plan.status));
      section.append(el("p","",`用例：${plan.payload.case_ids.join("、")}；预算≤${plan.payload.max_calls}次LLM / ${plan.payload.max_tokens} tokens；最长${plan.payload.timeout_seconds}秒`),
        el("p","qa-muted",`环境 ${plan.payload.environment_id} · 代码指纹 ${plan.payload.target_revision.slice(0,12)} · 计划 ${plan.digest.slice(0,12)} · ${plan.payload.planner==="model"?"真实模型工具规划":"人工选择固定计划（无规划模型调用）"}`));
      if(plan.evidence&&Object.keys(plan.evidence).length)section.append(pre(plan.evidence));
      const controls=el("div","qa-actions");
      if(plan.status==="draft"){
        const approve=button("批准此版本",()=>action(()=>api(`/plans/${plan.id}/approve`,{digest:plan.digest})),true);approve.disabled=!can("qa.approve");controls.append(approve);
      }
      if(plan.status==="approved"){const start=button("启动已批准计划",()=>action(async()=>{const run=await api("/runs",{plan_id:plan.id,request_key:crypto.randomUUID()});selectedRun=run.id;}),true);start.disabled=!canRun(plan.payload.kind);controls.append(start);}
      controls.append(button("收起",()=>{selectedPlan=null;paint();}));section.append(controls);root.append(section);
    }
    function renderRuns(){
      const section=el("section","qa-card");section.append(el("h3","","最近运行 · 两类结论分别计算"));
      if(!data.runs.length)section.append(el("p","qa-muted","尚未运行测试，不展示虚构通过率。需启动独立quality worker处理队列。"));
      for(const run of data.runs.slice(0,15)){
        const row=el("div","qa-case-row");row.append(button(`${run.id.slice(0,8)} · ${label(run.kind)}`,()=>{selectedRun=run.id;selectedCase=null;paint();}),badge(run.status),el("span","qa-muted",`${label(run.mode)} · ${run.results.length}条`));
        for(const [kind,group]of Object.entries(run.summary.groups||{}))row.append(el("span",group.eligible?"qa-pass":"qa-error",`${label(kind)}：${group.counts.passed||0}/${group.planned}通过`));
        section.append(row);
      }root.append(section);
    }
    function renderRun(run){
      if(!run)return;
      const section=el("section","qa-run-detail");const head=heading(`运行 ${run.id.slice(0,8)}`,`${label(run.kind)} · ${label(run.status)} · ${run.summary.decision?label(run.summary.decision):"尚未形成结论"}`);
      const controls=el("div","qa-actions");
      if(["queued","running"].includes(run.status)){const cancel=button(run.cancel_requested?"等待取消确认":"取消运行",()=>action(()=>api(`/runs/${run.id}/cancel`,{})));cancel.disabled=!canRun(run.kind);controls.append(cancel);}
      const rerun=button("新建重跑",()=>action(async()=>{const next=await api(`/runs/${run.id}/rerun`,{});selectedRun=next.id;}));rerun.disabled=!canRun(run.kind);controls.append(rerun);
      controls.append(button("导出脱敏JSON",()=>{const url=URL.createObjectURL(new Blob([JSON.stringify(run,null,2)],{type:"application/json"}));const link=el("a");link.href=url;link.download=`quality-${run.id}.json`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}));head.append(controls);section.append(head);
      if(run.summary.error)section.append(el("p","qa-error",run.summary.error));
      const layout=el("div","qa-evidence-grid");const cases=el("div","qa-evidence-column");cases.append(el("h3","","用例 / 真实状态"));
      for(const row of run.results){const snapshot=run.target?.case_snapshots?.find(entry=>entry.id===row.id);const item=button(`${row.id} ${snapshot?.title||data.cases.find(entry=>entry.id===row.id)?.title||""}`,()=>{selectedCase=row.id;paint();});item.classList.toggle("selected",(selectedCase||run.results[0]?.id)===row.id);item.append(badge(row.status));cases.append(item);}
      const row=run.results.find(entry=>entry.id===(selectedCase||run.results[0]?.id));const evidence=row?.evidence||{};
      const middle=el("div","qa-evidence-column"),right=el("div","qa-evidence-column");middle.append(el("h3","",row?.kind==="assistant"?"测试对话与工具轨迹":"API步骤与状态证据"));right.append(el("h3","","可信事实与固定断言"));
      if(evidence.error)middle.append(el("p","qa-error",evidence.error));
      for(const artifact of evidence.artifacts||[])middle.append(button('查看真实浏览器截图',()=>showArtifact(run.id,artifact.id)));
      const requests=evidence.requests||[];
      for(const request of requests){
        const detail=el("details","qa-step");detail.open=request.path.endsWith("/chat");detail.append(el("summary","",`${request.method} ${request.path} · ${request.status}${request.elapsed_ms==null?"":` · ${request.elapsed_ms}ms`}`));
        if(request.input?.message)detail.append(el("p","qa-question",request.input.message));
        if(request.output?.answer)detail.append(answer(request.output.answer));
        if(request.output?.tools?.length)detail.append(pre(request.output.tools));
        const raw=el("details");raw.append(el("summary","","脱敏请求 / 响应"),pre(request));detail.append(raw);middle.append(detail);
      }
      if(!requests.length)middle.append(el("p","qa-muted",["queued","running"].includes(row?.status)?"等待隔离子进程返回证据；不会预填通过。":"此步骤没有API请求证据，查看阻塞原因或固定测试断言。"));
      if(evidence.facts)right.append(pre(evidence.facts));
      for(const check of evidence.assertions||[]){const item=el("div",check.passed?"qa-assert qa-pass":"qa-assert qa-error");item.append(el("strong","",`${check.passed?"通过":"失败"} · ${check.name}`));if(check.expected!=null||check.actual!=null)item.append(pre({expected:check.expected,actual:check.actual}));right.append(item);}
      if(!evidence.assertions?.length)right.append(el("p","qa-muted","尚无有效断言结果，不算通过。"));
      if(evidence.budget)right.append(el("h4","","模型预算 / 实际来源"),pre(evidence.budget));
      right.append(el("p","qa-muted",`隔离清理：${evidence.cleanup_ok===true?"已确认":evidence.cleanup_ok===false?"未确认":"尚未执行"}`));
      layout.append(cases,middle,right);section.append(layout);root.append(section);
    }
    async function showArtifact(runId,artifactId){
      try{const response=await fetch(`/api/v1/op/qa/runs/${encodeURIComponent(runId)}/artifacts/${encodeURIComponent(artifactId)}`,{headers:{Authorization:'Bearer '+identity}});if(!response.ok)throw Error('截图读取失败或无权限');const blob=await response.blob();if(!valid())return;const url=URL.createObjectURL(blob),dialog=el('dialog','qa-dialog'),picture=el('img');picture.src=url;picture.alt='隔离浏览器测试截图';picture.style.maxWidth='100%';dialog.append(button('关闭',()=>dialog.close()),picture);dialog.addEventListener('close',()=>{URL.revokeObjectURL(url);dialog.remove();},{once:true});root.append(dialog);dialog.showModal();}catch(err){error(err.message);}
    }
    function compareDialog(){
      const dialog=el('dialog','qa-dialog'),form=el('form','qa-form'),baseline=el('select'),candidate=el('select'),message=el('p','qa-error');
      form.append(el('h2','','版本报告对比'));
      for(const run of data.runs){for(const select of [baseline,candidate]){const option=el('option','',`${run.id.slice(0,8)} · ${label(run.kind)} · ${label(run.status)}`);option.value=run.id;select.append(option);}}
      candidate.selectedIndex=Math.min(1,data.runs.length-1);baseline.setAttribute('aria-label','基线运行');candidate.setAttribute('aria-label','候选运行');form.append(el('label','','基线运行'),baseline,el('label','','候选运行'),candidate,message,button('生成对比',async()=>{try{comparison=await api(`/compare?baseline=${encodeURIComponent(baseline.value)}&candidate=${encodeURIComponent(candidate.value)}`);dialog.close();paint();}catch(err){message.textContent=err.message;}}),button('取消',()=>dialog.close()));dialog.append(form);dialog.addEventListener('close',()=>dialog.remove(),{once:true});root.append(dialog);dialog.showModal();
    }
    function retentionDialog(){
      const dialog=el('dialog','qa-dialog'),form=el('div','qa-form'),days=el('input'),result=el('p'),consent=el('input'),notice=el('label'),remove=button('确认清理预览范围',async()=>{if(!consent.checked||!preview)return;try{const done=await api('/retention/apply',{days:preview.days,digest:preview.digest});flash=`已清理${done.deleted_runs}次历史运行；${done.artifact_cleanup_errors.length}项截图清理异常。计划保留。`;remove.disabled=true;dialog.close();await refresh();}catch(err){result.textContent=err.message;}});let preview;
      days.type='number';days.min='7';days.max='3650';days.value='30';days.setAttribute('aria-label','保留天数');consent.type='checkbox';notice.append(consent,document.createTextNode('确认删除已预览的历史运行，不可撤销'));remove.disabled=true;consent.onchange=()=>{remove.disabled=!consent.checked||!preview?.count;};days.oninput=()=>{preview=null;remove.disabled=true;};form.append(el('h2','','历史保留与清理'),el('p','qa-muted','先预览再确认；活动任务与计划不会删除。'),days,button('预览清理范围',async()=>{try{preview=await api('/retention/preview',{days:Number(days.value)});result.textContent=`将清理${preview.count}次已结束的历史运行。${preview.truncated?`本次只处理最早${preview.count}次，另有${preview.remaining}次仍超期，可再次预览清理。`:''}${preview.notice}`;consent.checked=false;remove.disabled=true;}catch(err){result.textContent=err.message;}}),result,notice,remove,button('关闭',()=>dialog.close()));dialog.append(form);dialog.addEventListener('close',()=>dialog.remove(),{once:true});root.append(dialog);dialog.showModal();
    }
    function caseDialog(previous){
      const dialog=el('dialog','qa-dialog'),form=el('form','qa-form'),title=el('input'),role=el('select'),turns=el('div'),message=el('p','qa-error'),fields=[];
      title.required=true;title.maxLength=80;title.value=previous?.definition?.title||'';title.setAttribute('aria-label','用例名称');for(const [value,text] of [['customer','买家'],['merchant','商家']]){const option=el('option','',text);option.value=value;role.append(option);}role.value=previous?.definition?.role||'customer';role.setAttribute('aria-label','被测角色');
const addTurn=(saved={})=>{if(fields.length>=5)return;const section=el('section','qa-card'),question=el('textarea'),tools=el('input'),contains=el('input'),forbidden=el('input'),price=el('input');question.required=true;question.maxLength=1000;question.value=saved.message||'';tools.value=(saved.required_tools||[]).join(',');contains.value=(saved.expected_contains||[]).join(',');forbidden.value=(saved.forbidden_contains||[]).join(',');price.type='number';price.min='0';price.step='0.01';price.value=saved.max_product_price==null?'':String(saved.max_product_price);for(const [node,name]of [[question,'用户输入'],[tools,'必须调用的工具名'],[contains,'回答必须包含'],[forbidden,'回答不得包含'],[price,'商品卡最高单价（可选）']]){node.setAttribute('aria-label',`第${fields.length+1}轮${name}`);section.append(el('label','',name),node);}section.prepend(el('h3','',`第${fields.length+1}轮`));turns.append(section);fields.push({question,tools,contains,forbidden,price});};
      for(const saved of previous?.definition?.turns||[{}])addTurn(saved);form.append(el('h2','',previous?'编辑或创建新版本':'新增助手用例'),el('p','qa-muted','仅声明输入与硬断言，不执行自定义代码、SQL或URL。保存为候选，审核后才能运行；已审核版本保持不变。每轮至少配置一项断言，多个词或工具名用逗号分隔。'),el('label','','用例名称'),title,el('label','','被测角色'),role,turns,button('添加一轮',()=>addTurn()),message);
      const submit=el('button','qa-primary','保存候选');submit.type='submit';form.append(submit,button('取消',()=>dialog.close()));const split=value=>value.split(/[,，\n]/).map(word=>word.trim()).filter(Boolean);form.onsubmit=async event=>{event.preventDefault();submit.disabled=true;try{const definition={title:title.value,role:role.value,turns:fields.map(field=>({message:field.question.value,required_tools:split(field.tools.value),expected_contains:split(field.contains.value),forbidden_contains:split(field.forbidden.value),max_product_price:field.price.value===''?null:Number(field.price.value)}))};const path=previous?`/cases/${previous.id}${previous.state==='candidate'?'':'/revisions'}`:'/cases';await api(path,definition,previous?.state==='candidate'?'PATCH':'POST');filter='candidate';dialog.close();await refresh();}catch(err){message.textContent=err.message;}finally{submit.disabled=false;}};dialog.append(form);dialog.addEventListener('close',()=>dialog.remove(),{once:true});root.append(dialog);dialog.showModal();
    }
    function compose(kind){
      const dialog=el("dialog","qa-dialog");const form=el("form","qa-form");form.append(el("h2","",`新建${label(kind)}`));
      const goal=el("textarea");goal.name="goal";goal.required=true;goal.maxLength=2000;goal.value=kind==="functional"?"验证商品与订单的关键业务约束":kind==="assistant"?"验证业务助手商品查询、预算推荐与越权保护":"分别验证业务助手与业务功能；保持用例数据隔离";form.append(el("label","","测试目标"),goal);
      const mode=el("select"),planner=el("select");
      for(const value of kind==="functional"?["rules"]:["rules","live"]){const option=el("option","",label(value));option.value=value;mode.append(option);}
      for(const [value,text]of [["fixed","固定计划（不调用规划模型）"],["model","AI工具规划（消耗云端模型额度）"]]){const option=el("option","",text);option.value=value;planner.append(option);}
      form.append(el("label","","执行模式"),mode,el("label","","规划方式"),planner,el("p","qa-muted","只运行勾选且已接入的用例；AI仅能在此集合内选择。每条用例独立数据。"));
      const environment=el("select");
      for(const row of data.capabilities.environments){const option=el("option","",row.name);option.value=row.id;environment.append(option);}
      form.append(el("label","","执行环境"),environment);
      const choices=el("div","qa-choices");const counters={assistant:0,functional:0};
      for(const row of data.cases.filter(entry=>entry.state==="active"&&(kind==="joint"||entry.kind===kind))){const wrap=el("label");const check=el("input");check.type="checkbox";check.value=row.id;check.checked=counters[row.kind]++<2;wrap.append(check,document.createTextNode(`${row.id} ${row.title}`));choices.append(wrap);}form.append(choices);
      const updateModes=()=>{for(const check of choices.querySelectorAll('input')){const row=data.cases.find(item=>item.id===check.value);check.disabled=row.kind==='assistant'&&!row.modes.includes(mode.value);if(check.disabled)check.checked=false;check.parentElement.title=check.disabled?'此用例需要真实模型模式':'';}};
      mode.onchange=updateModes;updateModes();
      const budget=el("input");budget.type="number";budget.min="2000";budget.max="60000";budget.value="30000";form.append(el("label","","共享模型Token预算（含规划、重试与被测助手）"),budget);
      const consent=el("label","qa-consent"),check=el("input");check.type="checkbox";check.required=true;consent.append(check,document.createTextNode("确认只在已登记合成环境运行；真实模式/AI规划会消耗配置的模型额度"));form.append(consent);
      const message=el("p","qa-error");const submit=el("button","qa-primary","生成待审批计划");submit.type="submit";
      const labels=Array.from(form.querySelectorAll('label')).filter(node=>!node.querySelector('input'));
      Array.from(form.querySelectorAll('textarea,select,input[type=number]')).forEach((field,index)=>{field.id='qa-field-'+crypto.randomUUID();labels[index].htmlFor=field.id;});
      const actions=el("div","qa-actions");actions.append(button("取消",()=>dialog.close()),submit);form.append(message,actions);
      form.onsubmit=async event=>{event.preventDefault();submit.disabled=true;try{const ids=Array.from(choices.querySelectorAll("input:checked")).map(node=>node.value);const plan=await api("/plans",{goal:goal.value,kind,mode:mode.value,planner:planner.value,environment_id:environment.value,case_ids:ids,max_tokens:Number(budget.value)});selectedPlan=plan.id;dialog.close();await refresh();}catch(err){message.textContent=err.message;}finally{submit.disabled=false;}};
      dialog.append(form);dialog.addEventListener("close",()=>dialog.remove(),{once:true});root.append(dialog);dialog.showModal();
    }
    root.append(el("p","qa-muted","正在读取OP测试能力…"));refresh();
  }
  return {mount};
})();
