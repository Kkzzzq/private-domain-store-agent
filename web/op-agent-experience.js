/* Presentation layer only. Existing plans, approvals and evidence remain authoritative. */
window.OPAgentExperience = (() => {
  const contexts = new WeakMap();
  const rows = value => Array.isArray(value) ? value : [];
  const titles = {business:'业务 Agent',functional:'功能测试 Agent',evaluator:'助手评测 Agent'};
  const labels = {queued:'排队中',running:'执行中',completed:'执行结束',passed:'通过',failed:'失败',blocked:'阻塞',cancelled:'已取消',draft:'待审批',approved:'已批准',planning:'等待规划',planning_running:'正在规划'};
  const label = value => labels[value] || value || '未记录';
  const el = (tag,cls,text) => {const node=document.createElement(tag);node.className=cls||'';if(text!=null)node.textContent=String(text);return node;};
  const button = (text,fn) => {const node=el('button','ae-button',text);node.type='button';node.onclick=fn;return node;};
  const display = value => value===undefined?'未采集':typeof value==='string'?value:JSON.stringify(value,null,2);
  const chip = (text,state='') => el('span','ae-chip ae-'+state,text);
  function counts(run) {const result={passed:0,failed:0,blocked:0};for(const row of rows(run?.results))if(Object.hasOwn(result,row.status))result[row.status]++;return result;}
  function overview(root,{agents,data,go}) {
    root.classList.add('ae-root');
    const head=el('header','ae-hero');head.append(el('span','ae-eyebrow','OP / AGENT WORKSPACE'),el('h2','','三个 Agent，一个工作入口'),el('p','','体验业务能力，验证业务功能，再检查助手是否真正完成任务。'));
    root.append(head);
    const summary=el('section','ae-attention');
    const active=rows(data.runs).filter(run=>['queued','running'].includes(run.status));
    const approvals=rows(data.plans).filter(plan=>plan.status==='draft');
    const problem=rows(data.runs).filter(run=>rows(run.results).some(row=>['failed','blocked'].includes(row.status)));
    summary.append(el('strong','','当前待办'),button(`进行中 ${active.length}`,()=>go('testing-runs')),button(`待审批计划 ${approvals.length}`,()=>go(approvals[0]?.payload?.kind==='assistant'?'testing-evaluator':'testing-functional')),button(`含失败或阻塞的报告 ${problem.length}`,()=>go('testing-runs')),el('small','','按当前已加载记录统计；报告可分别筛选两类测试。'));
    root.append(summary);
    const relation=el('div','ae-relation');relation.setAttribute('aria-label','三个Agent的职责关系');
    for(const text of ['业务 Agent → 完成用户的业务任务','功能测试 Agent → 验证接口、页面与业务状态','助手评测 Agent → 验证业务 Agent 的回答与执行'])relation.append(el('p','',text));
    root.append(relation);
    const workspaces=el('div','ae-overview-agents');
    const routes={business:'testing-business',functional:'testing-functional',evaluator:'testing-evaluator'};
    const copy={business:['先看它如何完成任务','切换买家与商家视角，查看回答、商品结果与待确认操作。','进入业务对话'],functional:['业务功能是否正常','从测试计划到状态核验，定位失败步骤及业务差异。','进入功能测试'],evaluator:['助手是否回答并执行正确','对照问题、实际回答、事实依据和逐项判定。','进入助手评测']};
    for(const id of ['business','functional','evaluator']) {
      const descriptor=rows(agents).find(row=>row.id===id),stats=descriptor?.stats||{};
      const section=el('section','ae-workspace-card ae-card-'+id);
      section.append(el('span','ae-eyebrow',titles[id]),el('h3','',copy[id][0]),el('p','',copy[id][1]));
      if(id==='business')section.append(el('p','ae-meta',`已接入工具 ${stats.tool_count??descriptor?.tools?.length??'未采集'} · 本人缓存对话 ${stats.dialogues??'未采集'}`));
      else {
        const latest=stats.last_run&&rows(data.runs).find(run=>run.id===stats.last_run.id);
        section.append(chip(stats.last_run?label(stats.last_run.status):'尚无运行记录',stats.last_run?.status));
        section.append(el('p','ae-meta',`已接入用例 ${stats.active_cases??'未采集'} · 运行记录 ${stats.runs??'未采集'}`));
        if(latest){const c=counts(latest);section.append(el('p','ae-meta',`最近报告：通过 ${c.passed} / 失败 ${c.failed} / 阻塞 ${c.blocked}（仅该报告）`));}
      }
      section.append(button(copy[id][2],()=>go(routes[id])));
      if(id==='business'){const guide=el('div','ae-business-guide');for(const [title,detail] of [['购物与推荐','观察预算、规格和数量如何影响真实商品结果。'],['订单与售后','检查当前身份能查什么，以及需要用户确认的操作。'],['商家经营','查看本店经营查询和商品配置提案。']]){const block=el('div');block.append(el('strong','',title),el('p','ae-meta',detail));guide.append(block);}section.append(guide);}
      workspaces.append(section);
    }
    root.append(workspaces);
    const recent=el('section','ae-recent');recent.append(el('h3','','最近任务'));
    const latest=rows(data.runs).slice(0,5);
    if(!latest.length)recent.append(el('p','ae-meta','尚无任务记录。进入对应工作区创建计划，批准后运行。'));
    for(const run of latest){const line=el('div','ae-task-line');line.append(el('strong','',run.name||run.id),chip(label(run.status),run.status),el('span','ae-meta',run.target?.environment_id||'环境未采集'),button('进入报告列表',()=>go('testing-runs')));recent.append(line);}
    root.append(recent);
    const details=el('details','ae-details');details.append(el('summary','','统计口径与使用边界'),el('p','ae-meta',`用例登记不等于验收通过。业务助手、功能测试与助手评测分别查看结果；接口通过不代表浏览器通过。报告和截图保留 ${data.capabilities?.retention?.days??'未采集'} 天。`));
    for(const line of rows(data.capabilities?.limitations))details.append(el('p','ae-meta',line));root.append(details);
  }
  function context(root,options) {
    root.classList.add('ae-root');root.dataset.agentExperience=options.id;
    const previous=contexts.get(root);
    contexts.set(root,{...options,traceOpen:previous?.traceOpen||false});
    if(!previous){const observer=new MutationObserver(()=>enhance(root));observer.observe(root,{childList:true,subtree:true});}
    const intro=el('section','ae-role-intro');
    const descriptions={business:'这里体验业务助手；不填写预期答案，也不在这里给回答打分。',functional:'这里验证业务功能。先看测试目标与计划，再看实际状态是否符合预期。',evaluator:'这里评测业务助手。将用户问题、助手回答、事实依据与判定放在一起。'};
    intro.append(el('strong','',titles[options.id]),el('p','',descriptions[options.id]));root.append(intro);
    queueMicrotask(()=>enhance(root));
  }
  function brief(value) {
    if(value==null)return '未采集独立值';
    if(Array.isArray(value)){
      if(value.every(row=>row&&typeof row==='object'&&row.tool))return `${value.length} 条工具记录：${value.map(row=>row.tool).join(' → ')}`;
      if(value.every(row=>row&&typeof row==='object'&&row.name))return `${value.length} 项结果：${value.map(row=>row.name).join('、')}`;
    }
    const text=display(value);return text.length>240?text.slice(0,240)+'…（完整内容见证据）':text;
  }
  function comparison(check) {
    const item=el('section','ae-check');item.append(chip(check.passed===true?'通过':check.passed===false?'失败':'未记录',check.passed===true?'passed':check.passed===false?'failed':''),el('strong','',check.name||'业务检查'));
    const grid=el('div','ae-compare');
    for(const [caption,value] of [['预期',check.expected],['实际',check.actual]]){const cell=el('div');cell.append(el('small','',caption),el('pre','',brief(value)));grid.append(cell);}item.append(grid);const evidence=el('details','ae-details');evidence.append(el('summary','','查看完整断言证据'),el('pre','ae-facts',display(check)));item.append(evidence);return item;
  }
  function focus(result,run,kind) {
    const panel=el('section','ae-result-focus');const evidence=result?.evidence||{};
    panel.append(el('h3','',kind==='evaluator'?'问题、回答与判定':'检查目标与业务结果'));
    if(!result){panel.append(el('p','ae-meta','选择一份运行报告，查看实际结果。'));return panel;}
    const title=result.doc?.title||rows(run?.target?.case_snapshots).find(row=>row.id===result.id)?.title||result.id;
    panel.append(el('h4','',title),chip('本场景：'+label(result.status),result.status));
    const meta=el('p','ae-meta',`环境 ${run?.target?.environment_id||'未采集'} · 版本 ${run?.target?.code_revision||run?.target?.commit||'见批准范围'} · ${run?.diagnostic===false?'正式测试记录':'诊断或历史记录'}`);panel.append(meta);
    if(kind==='evaluator') {
      const chats=rows(evidence.requests).filter(request=>String(request.path||'').endsWith('/chat'));
      if(!chats.length)panel.append(el('p','ae-meta','本记录没有采集到被测助手对话，不能仅凭接口记录判定回答质量。'));
      chats.forEach((request,index)=>{const turn=el('section','ae-turn');turn.append(el('span','ae-eyebrow',`第 ${index+1} 轮`),el('small','','用户问题'),el('p','ae-question',request.input?.message??'未采集'),el('small','','业务助手的实际回答'),el('p','ae-response',request.output?.answer??'未采集'));panel.append(turn);});
    } else {
      const steps=rows(result.doc?.steps);if(steps.length){const list=el('ol','ae-task-steps');for(const text of steps)list.append(el('li','',text));panel.append(list);}
      const stages=rows(evidence.suite?.reports).filter(report=>report.stage==='call');
      if(stages.length){const list=el('div','ae-stage-results');for(const stage of stages)list.append(el('p','',`${label(stage.outcome)} · ${stage.node||'执行阶段'}`));panel.append(list);}
    }
    if(evidence.error)panel.append(el('p','ae-failure',evidence.error));
    const checks=rows(evidence.assertions);panel.append(el('h4','','逐项核验'));
    if(checks.length)checks.forEach(check=>panel.append(comparison(check)));
    else panel.append(el('p','ae-meta','本记录未采集逐项断言；不能将缺失证据当成通过。'));
    if(evidence.facts!=null){const facts=el('details','ae-details');facts.append(el('summary','','可信业务事实'),el('pre','ae-facts',display(evidence.facts)));panel.append(facts);}
    panel.append(el('p','ae-meta',evidence.cleanup_ok===true?'资源清理：已完成（不等于用例通过）':evidence.cleanup_ok===false?'资源清理：未成功，需处理':'资源清理：本记录未采集'));
    return panel;
  }
  function enhance(root) {
    const ctx=contexts.get(root);if(!ctx||!root.isConnected)return;
    for(const grid of root.querySelectorAll('.ao-grid:not([data-ae-ready])')) {
      const columns=Array.from(grid.children);if(columns.length!==3)continue;
      grid.dataset.aeReady='true';const [left,middle,right]=columns;
      grid.classList.add('ae-'+ctx.id);
      if(ctx.id==='business') {
        left.classList.add('ae-dialogue');left.querySelector('h4').textContent='对话与业务结果';
        const side=el('aside','ae-inspector'),trace=el('details','ae-details');trace.open=ctx.traceOpen;
        trace.append(el('summary','','展开实际执行轨迹'),middle);trace.addEventListener('toggle',()=>{ctx.traceOpen=trace.open;});
        const raw=right.querySelector('.ao-json');
        if(raw){try{const detail=JSON.parse(raw.textContent);const readable=detail.message||detail.answer||detail.result||detail.error;
          if(readable){const copy=el('section','ae-detail-reading');copy.append(el('small','','本步记录'),el('p','',display(readable)));right.insertBefore(copy,right.children[1]||null);}
        }catch{/* Raw technical records remain available in their original form. */}}
        if(raw&&!raw.closest('details')){const technical=el('details','ae-details');technical.append(el('summary','','技术原始记录'));raw.replaceWith(technical);technical.append(raw);}
        side.append(trace,right);grid.append(side);
      } else {
        const selections=Array.from(left.querySelectorAll('select'));
        const runs=rows(ctx.data.runs).filter(run=>rows(run.results).some(row=>row.kind===(ctx.id==='functional'?'functional':'assistant')));
        const run=runs.find(run=>run.id===selections[0]?.value)||runs[0];
        const results=rows(run?.results).filter(row=>row.kind===(ctx.id==='functional'?'functional':'assistant'));
        const result=results.find(row=>row.id===selections[1]?.value)||results[0];
        const center=el('section','ae-result-column'),trace=el('details','ae-details');trace.open=ctx.traceOpen;
        trace.append(el('summary','','执行步骤与技术轨迹'),middle);trace.addEventListener('toggle',()=>{ctx.traceOpen=trace.open;});
        center.append(focus(result,run,ctx.id),trace);grid.insertBefore(center,right);
        left.querySelector('h4').textContent='任务与场景';
      }
    }
    if(ctx.id!=='business') {
      const host=root.querySelector('.ao-workspace')?.parentElement;
      if(host&&host.parentElement===root){
        const create=Array.from(root.querySelectorAll('button')).find(node=>node.textContent===(ctx.id==='functional'?'新建功能测试计划':'新建评测计划'));
        const commands=create?.closest('.qa-actions');
        if(commands&&!commands.classList.contains('ae-command-bar')){commands.classList.add('ae-command-bar');root.insertBefore(commands,host);}
        const planTitle=Array.from(root.querySelectorAll('h3')).find(node=>node.textContent==='计划与审批');
        const plan=planTitle?.closest('.qa-card');
        if(plan&&!root.querySelector('.ae-plans')){const details=el('details','ae-plans');
          const plans=rows(ctx.data.plans).filter(row=>row.payload?.kind===(ctx.id==='functional'?'functional':'assistant'));
          const awaiting=plans.filter(row=>row.status==='draft').length;details.open=awaiting>0;
          details.append(el('summary','',`测试计划与审批（${plans.length} 份，${awaiting} 份待审批）`),plan);root.insertBefore(details,host);
        }
      }
    }
    const historyTitle=Array.from(root.querySelectorAll('h3')).find(node=>node.textContent.includes('最近测试用例报告'));
    const history=historyTitle?.closest('.qa-card');
    if(history&&!history.dataset.aeHistory){history.dataset.aeHistory='true';const folded=el('details','ae-details');folded.append(el('summary','','展开历史运行与报告'));history.replaceWith(folded);folded.append(history);}
    for(const reference of root.querySelectorAll('.qa-agent-reference:not([data-ae-ready])')){reference.dataset.aeReady='true';reference.open=false;}
  }
  return {overview,context,focus,counts};
})();
