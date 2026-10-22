/* Server-derived capabilities and independent evaluations. No generated HTML. */
window.OPAgentQuality=(()=>{
  const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!=null)n.textContent=String(text);if(cls)n.className=cls;return n;};
  const btn=(text,fn)=>{const n=el('button',text);n.type='button';n.onclick=fn;return n;};
  const detail=(title,value)=>{const d=el('details');d.append(el('summary',title),el('pre',typeof value==='string'?value:JSON.stringify(value,null,2)));return d;};
  const select=(label,values)=>{const n=el('select');n.setAttribute('aria-label',label);for(const [value,text] of values){const o=el('option',text);o.value=value;n.append(o);}return n;};
  const states=new WeakMap();
  let cacheOwner,details=new Map(),downloads=new Map();
  function clearCache(){cacheOwner=undefined;details=new Map();downloads=new Map();}
  window.addEventListener('op-session-ended',clearCache);
  const labels={passed:'通过',failed:'未通过',incomplete:'证据待补充',completed:'已评分',blocked:'阻塞',scoring:'执行中',not_scored:'尚未评分',needs_review:'待人工核验'};
  const dimensionNames={task_success:'任务完成',factual_grounding:'事实依据',tool_use:'工具使用',conversation:'完整会话',permissions:'权限边界',recovery:'异常恢复',efficiency:'效率与成本',feature_grounding:'真实功能依据',plan_coverage:'计划覆盖',tool_execution:'工具执行',assertion_quality:'断言质量',defect_detection:'缺陷检出',failure_attribution:'失败归因',cleanup:'数据清理'};
  const stamp=value=>new Date(/[Z+]|\d-\d\d:\d\d$/.test(value)?value:value+'Z').toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false});
  function mount(root,{id,data,api,refresh,reviewPlan}){
    if(!['functional','evaluator'].includes(id))return;
    const identity=sessionStorage.getItem('token_op');
    if(cacheOwner!==identity){clearCache();cacheOwner=identity;}
    const sessionDetails=details,sessionDownloads=downloads;
    const host=el('section',null,'aq-panel qa-card');root.append(host);
    const state=states.get(root)||{target:'business'};states.set(root,state);
    const live=()=>host.isConnected&&sessionStorage.getItem('token_op')===identity;
    let errorNode=null;
    const error=err=>{
      if(!live()||err?.handled)return;
      const text=err?.message||String(err);
      if(errorNode?.isConnected&&errorNode.textContent===text)return;
      errorNode?.remove();
      errorNode=el('p',text,'qa-error');
      host.append(errorNode);
    };
    const clearError=()=>{errorNode?.remove();errorNode=null;};
    const job=async(button,fn)=>{button.disabled=true;try{await fn();}catch(err){error(err);}finally{button.disabled=false;}};
    if(id==='functional'){
      host.append(el('h3','B / C / OP 功能依据与执行工具'),el('p','目录来自实际代码，平台治理单独标记为 OP。已关联场景不代表全部分支覆盖；模型必须先读功能目录，再调用批准的复合测试工具。'));
      api('/agent-quality/features').then(catalog=>{
        if(!live())return;
        const side=select('功能所属端',[['all','全部：B / C / OP'],['B','商家 B 端'],['C','买家 C 端'],['OP','平台 OP 端']]),list=el('div');
        host.append(el('p',`发现 ${catalog.endpoint_count} 个接口入口 · 目录 ${catalog.version.slice(0,12)} · 可复用点击工具 ${catalog.ui_actions?.counts?.ready??0} 个可用 / ${catalog.ui_actions?.counts?.unverified??0} 个待验证`),detail('B/C 前端实际入口与版本',catalog.frontend),detail('可复用点击工具库（Agent 只需组合调用）',catalog.ui_actions),side,list);
        const paint=()=>{list.replaceChildren();for(const feature of catalog.features.filter(f=>side.value==='all'||f.sides.includes(side.value))){
          const split=feature.coverage_split||{},counts=channel=>(split[channel]?.case_ids||[]).length;
          const scenes=feature.scenarios||{},labels=scenes.labels||{},coverage=scenes.coverage||{};
          const sceneText=Object.keys(labels).map(kind=>`${labels[kind]} ${(coverage[kind]||[]).length}`).join(' · ');
          const statusText=(scenes.status||'unconfirmed')==='untestable'?'暂不可测试':(scenes.status||'unconfirmed')==='unconfirmed'?'待确认':'';
          const summary=split.api||split.page?`接口覆盖 ${counts('api')} 条 · 页面覆盖 ${counts('page')} 条${statusText?' · '+statusText:''}`:(feature.tools.length?'部分场景已接入':'未覆盖');
          const card=el('details',null,'aq-feature');card.append(el('summary',`${feature.sides.join('/')} · ${feature.name} · ${summary}`),el('p',feature.rule),el('p',feature.coverage_note));
          card.append(detail(`正常/异常/权限/边界场景（${sceneText||'未采集'}）`,{status:scenes.status,status_note:scenes.status_note,coverage:scenes.coverage,reviewed:scenes.reviewed,unconfirmed_case_ids:scenes.unconfirmed_case_ids}),detail(`可复用点击工具（${(feature.ui_actions?.ready||[]).length} 个可用）`,feature.ui_actions),detail('测试数据要求与清理方式',feature.cleanup),detail('接口覆盖与页面覆盖（分别记录）',split),detail('真实入口、参数、权限依赖与源码',feature.endpoints),detail('前置条件与验证目标',{preconditions:feature.preconditions,verification:feature.verification}),detail('当前环境可用复合工具',feature.tools));
          if(feature.tools.length){const create=btn('生成计划并前往审批 →',()=>job(create,async()=>{
            const env=data.capabilities.environments[0]?.id;
            const caseIds=feature.tools.filter(t=>!t.environments?.length||t.environments.includes(env)).map(t=>t.case_id).slice(0,20);
            if(!caseIds.length)throw Error('所选环境没有可执行工具');
            const plan=await api('/plans',{kind:'functional',goal:`检查${feature.sides.join('/')}端的${feature.name}。依据功能目录${catalog.version}：${feature.rule}。执行所有批准场景并保留实际工具证据。`,case_ids:caseIds,environment_id:env,mode:'rules',diagnostic:env==='real-nanzhi',planner:env==='real-nanzhi'?'fixed':'model',functional_driver:true,max_calls:30,max_tokens:60000,timeout_seconds:1200});
            if(reviewPlan)await reviewPlan(plan.id);else await refresh();
          }));create.className='qa-primary aq-approval-button';card.append(el('p','生成后进入审批，核对范围与预算并批准后才能执行。'),create);}list.append(card);
        }};side.onchange=paint;paint();
      }).catch(error);return;
    }
    host.classList.add('aq-evaluator');
    const intro=el('div',null,'aq-intro');intro.append(el('h3','选择评测来源'),el('p','先选择运行记录生成程序核验；模型评分和人工复核可在结果中继续补充。','qa-muted'));host.append(intro);
    const target=select('评测对象',[['business','业务 Agent'],['functional','功能测试 Agent']]);target.value=state.target;
    const source=select('来源运行',[]),list=el('div',null,'aq-history-list'),content=el('div',null,'aq-detail');
    const form=el('div',null,'aq-source-form');
    const field=(name,control)=>{const wrap=el('label',null,'aq-field');wrap.append(el('span',name),control);return wrap;};
    form.append(field('评测对象',target),field('选择已结束的运行',source));
    const sourceNote=el('p','','qa-muted aq-source-note');
    const layout=el('div',null,'aq-review-layout'),historyPanel=el('div',null,'aq-history');
    const historyHead=el('div',null,'aq-history-head'),historyCount=el('span','0 份','aq-history-count');
    historyHead.append(el('h4','历史评测'),historyCount);historyPanel.append(historyHead,el('p','点击一份评测查看结果；详情按需加载。','qa-muted'),list);
    layout.append(historyPanel,content);host.append(form,sourceNote,layout);
    const emptyDetail=()=>{const empty=el('div',null,'aq-empty');empty.append(el('span','评测结果','aq-section-kicker'),el('h4','选择一份评测，开始查看'),el('p','可以从左侧打开历史评测，也可以选择上方运行记录生成新的程序核验。'));content.replaceChildren(empty);};
    const fill=()=>{source.replaceChildren();const kind=target.value==='business'?'assistant':'functional';const runs=data.runs.filter(r=>['completed','failed','blocked','cancelled'].includes(r.status)&&(r.kind===kind||r.kind==='joint'));for(const run of runs){const o=el('option',window.OPReportName?window.OPReportName.label(run,data.cases,{time:true}):run.name||run.id);o.value=run.id;source.append(o);}source.disabled=!runs.length;sourceNote.textContent=runs.length?`可选 ${runs.length} 份已结束运行。生成程序核验不会重新执行业务任务；补充模型评分会调用评测模型。`:'当前对象暂无已结束运行。请先到对应 Agent 工作区完成一次运行，再回到这里评测。';create.disabled=!runs.length;};
    let selectedEvaluation=null;
    async function show(row){
      selectedEvaluation=row.id;
      for(const item of list.querySelectorAll('button')){const chosen=item.dataset.evaluationId===row.id;item.classList.toggle('is-selected',chosen);item.setAttribute('aria-pressed',String(chosen));}
      if(row.brief&&sessionDetails.get(row.id)?.version===row.version)row=sessionDetails.get(row.id);
      if(row.brief){
        const notice=el('p','正在下载报告详情…');notice.setAttribute('role','status');notice.setAttribute('aria-live','polite');content.replaceChildren(notice);
        try{
          const reportId=row.id;
          if(!sessionDownloads.has(reportId)){
            const request=api(`/agent-quality/evaluations/${reportId}/detail`).then(full=>{
              if(details===sessionDetails&&sessionStorage.getItem('token_op')===identity){sessionDetails.set(reportId,full);while(sessionDetails.size>40)sessionDetails.delete(sessionDetails.keys().next().value);}return full;
            }).finally(()=>sessionDownloads.delete(reportId));
            sessionDownloads.set(reportId,request);
          }
          row=await sessionDownloads.get(reportId);
        }catch(err){if(live())content.replaceChildren(el('p',err.message,'qa-error'),btn('重试下载',()=>show(row)));return;}
        if(!live()||selectedEvaluation!==row.id)return;
      }
      if(details===sessionDetails&&sessionStorage.getItem('token_op')===identity)sessionDetails.set(row.id,row);
      content.replaceChildren();
      const resultHead=el('header',null,'aq-result-head');resultHead.append(el('span','当前评测','aq-section-kicker'),el('h4',`${row.target==='business'?'业务 Agent':'功能测试 Agent'} · ${stamp(row.created_at)}`),el('p',`来源运行 ${String(row.source_run||'').slice(0,8)} · 评测编号 ${row.id.slice(0,8)}`,'qa-muted'));content.append(resultHead);
      const verdicts=el('div',null,'aq-verdicts');
      for(const [title,value,note] of [['程序核验',labels[row.program.decision]||row.program.decision,'按已采集证据逐项检查'],['模型评分',labels[row.model_score.status]||'尚未评分','按需调用独立评测模型'],['人工复核',row.reviews.length?'已有复核':'待复核','保留人工意见与依据']]){const card=el('section',null,'aq-verdict');card.append(el('span',title),el('strong',value),el('small',note));verdicts.append(card);}content.append(verdicts,el('h4','程序核验明细'));
      if(row.review_conflict)content.append(el('p','人工意见与程序或模型存在分歧，请查看复核依据。','qa-error'));
      if(row.reviews.length&&!row.review_current)content.append(el('p','已有人工意见针对旧评测版本，请对当前证据重新复核。'));
      for(const check of row.program.checks)content.append(el('p',`${check.status==='passed'?'✓':check.status==='failed'?'✗':'待证据'} ${check.name}${check.detail?' · '+check.detail:''}`));
      content.append(detail('任务结果与原始报告',row.snapshot.source.results),detail('工具调用轨迹与完整已采集会话',row.snapshot.evidence));
      content.append(el('h4','模型评分'),el('p','可补充任务完成度、事实依据和工具使用等维度的评分。此操作会调用模型，结果不会覆盖程序核验。','qa-muted'));
      const score=btn('补充模型评分',()=>job(score,async()=>show(await api(`/agent-quality/evaluations/${row.id}/model-score`,{}))));content.append(score);
      if(Object.keys(row.model_score).length)content.append(detail('模型各维度分数、证据引用与用量',row.model_score));
      for(const dimension of row.model_score.dimensions||[])content.append(el('p',`${dimensionNames[dimension.dimension]||dimension.dimension}：${dimension.score==null?'未观察':dimension.score+'/4'} · ${dimension.reason} · 证据 ${dimension.evidence_ids.join('、')||'无'}`));
      if(row.target==='functional'){
        if(row.snapshot.heldout){
          const hidden=row.snapshot.heldout,states={not_enabled:'未启用：管理员尚未配置答案',incomplete:'证据不足：答案或来源场景不完整',failed:'存在不匹配项',passed:'当前隐藏集核验通过'};
          content.append(el('h4','隐藏集对照（独立结论）'),el('p',`${states[hidden.decision]||'待确认'} · 已提供答案 ${hidden.scored_count??0}/${hidden.expected_count??0}。此结论不替代程序核验、模型评分或人工复核。`),detail('隐藏集逐条状态与摘要',hidden));
        }
        const calibrate=btn('用正常版与缺陷版评测测试 Agent',()=>job(calibrate,async()=>{
          if(!await window.OPDialogs.confirm('将在独立合成环境执行4个场景的正常版与缺陷版，共8次执行；最多32次模型调用、480000 tokens，可能等待数分钟。不修改实际店铺，撤销权限后会停止。确认运行？'))return;
          show(await api(`/agent-quality/evaluations/${row.id}/defect-benchmark`,{}));
        }));
        content.append(el('p','基准在独立合成环境为每个已知缺陷场景各跑正常版与注入版两次真实模型与真实复合工具，不修改实店；只看这些场景的检出与误报，不代表全站检出率。'),calibrate);
        for(const item of (row.snapshot.calibration||{}).scenarios||[])content.append(el('p',`${item.detected?'检出':item.false_positive?'正常版误报':'未检出'} · ${item.title}（${item.defect}）· 用例 ${item.case_id} · 注入执行 ${item.mutation_exercised?'已确认':'未确认'}`));
        if(row.snapshot.calibration)content.append(detail('功能测试 Agent 缺陷基准证据（逐场景正常/注入两次执行）',row.snapshot.calibration));
      }
      const decision=select('人工复核结论',[['needs_evidence','需要补充证据'],['accepted','认可本次评测'],['rejected','不认可本次评测']]);
      const reason=el('textarea');reason.placeholder='填写复核依据，保留与程序或模型结论的分歧';reason.setAttribute('aria-label','人工复核理由');
      const review=btn('提交人工复核',()=>job(review,async()=>show(await api(`/agent-quality/evaluations/${row.id}/reviews`,{version:row.version,decision:decision.value,reason:reason.value}))));
      const manual=el('section',null,'aq-manual');manual.append(el('h4','人工复核'),el('p','结合程序核验和模型评分填写依据，人工意见会单独留存。','qa-muted'),field('复核结论',decision),field('复核依据',reason),review,detail('历史复核记录',row.reviews));content.append(manual);
      // 重复执行稳定性：同一计划在本报告中真实执行过几次，不足就判证据不足。
      const planId=(row.snapshot.source||{}).plan_id;
      const steady=el('div');content.append(el('h4','重复执行稳定性'),steady);
      if(planId)api(`/agent-quality/stability?plan_id=${encodeURIComponent(planId)}`).then(rows=>{if(!live())return;steady.replaceChildren(el('p',`${rows.note}（同一计划已完成 ${rows.attempts} 次）`));for(const item of rows.cases)steady.append(el('p',`${item.case_id}：${item.note} · ${item.statuses.join(' → ')}`));}).catch(err=>steady.append(el('p',err.message)));
      else steady.append(el('p','来源报告没有计划编号，无法统计稳定性。'));
      if(row.program.decision!=='passed')content.append(el('p','存在失败或未观察项；人工意见不会改写原始断言。'));
    }
    function comparePanel(rows){
      const box=el('div',null,'aq-compare');
      box.append(el('h4','评测版本对比'));
      if(rows.length<2){box.append(el('p',rows.length===0?'暂无独立评测记录。先在上方选择已结束运行，点击「生成程序核验」。':'当前只有 1 份独立评测。请再选择一次已结束运行创建评测，至少两份才能对比。','qa-notice'));return box;}
      const a=select('基线评测',[]),b=select('候选评测',[]),out=el('div');
      for(const row of rows){for(const node of [a,b]){const option=el('option',`${stamp(row.created_at)} · ${row.id.slice(0,8)} · ${labels[row.program.decision]||row.program.decision}`);option.value=row.id;node.append(option);}}
      if(rows.length>1)b.selectedIndex=1;
      const compare=btn('生成对比',()=>job(compare,async()=>{const result=await api(`/agent-quality/evaluations/compare?baseline=${encodeURIComponent(a.value)}&candidate=${encodeURIComponent(b.value)}`);
        const nodes=[el('p',result.comparable?'两份评测可比。':`不可比：${result.incompatible_reasons.join('、')}`)];
        for(const item of result.program.filter(row=>row.changed))nodes.push(el('p',`${item.name}：${labels[item.before]||item.before} → ${labels[item.after]||item.after} · ${item.transition}`));
        for(const item of result.dimensions)nodes.push(el('p',`${dimensionNames[item.dimension]||item.dimension}：${item.before==null?'未观察':item.before} → ${item.after==null?'未观察':item.after}${item.delta==null?'':'（'+(item.delta>0?'+':'')+item.delta+'）'}`));
        nodes.push(el('p','人工复核：基线 '+result.reviews.baseline+' 条 / 候选 '+result.reviews.candidate+' 条；'+result.note));
        out.replaceChildren(...nodes);}));
      const update=()=>{compare.disabled=!a.value||!b.value||a.value===b.value;};a.onchange=update;b.onchange=update;update();
      const fields=el('div',null,'aq-compare-fields');
      for(const [title,node] of [['基线评测',a],['候选评测',b]]){const field=el('label',title);field.append(node);fields.append(field);}
      box.append(fields,compare,out);
      return box;
    }
    function heldoutPanel(){
      const box=el('div'),out=el('div'),logs=el('div');
      box.append(el('h4','不公开评测集'),el('p','期望答案不随代码发布，只给摘要；没有本地答案文件时标记 expectation_unavailable，不计通过。揭示答案需要审批权限并留痕。'),out,logs);
      const paint=async()=>{const view=await api('/agent-quality/heldout');if(!live())return;
        out.replaceChildren(el('p',`答案文件：${view.available?'已提供（摘要 '+String(view.sealed_digest).slice(0,12)+'）':'未提供'} · ${view.note}`));
        for(const item of view.entries){
          const line=el('section',null,'aq-heldout-entry');
          line.append(el('p',`${item.status==='sealed'?'已封存':'无答案'} · ${item.id} · 用例 ${item.case_id} · ${item.goal} · 摘要 ${item.expect_hash?item.expect_hash.slice(0,12):'无'}`));
          if(item.status==='sealed'){
            // 内嵌浏览器/沙箱 iframe 会禁用 prompt()，所以用页面内输入框留痕，不依赖弹窗。
            const reason=el('input');reason.placeholder='填写揭示理由（至少 3 字，会留痕）';reason.setAttribute('aria-label','揭示理由');
            const form=el('div',null,'aq-heldout-form');form.hidden=true;
            const submit=btn('提交揭示',()=>job(submit,async()=>{
              const text=reason.value.trim();if(text.length<3)throw Error('请填写至少 3 个字的揭示理由');
              const result=await api('/agent-quality/heldout/reveal',{entry_id:item.id,reason:text});
              form.hidden=true;reason.value='';
              line.append(el('p',`已揭示 ${item.id}：${JSON.stringify(result.answer.expect)}`,'aq-heldout-result'));
              const rows=await api('/agent-quality/heldout/reveals');logs.replaceChildren(el('p',`揭示记录 ${rows.length} 条，最近：${rows[0]?rows[0].entry_id+'（'+rows[0].reason+'）':'无'}`));
            }));
            form.append(reason,submit,btn('取消',()=>{form.hidden=true;reason.value='';}));
            line.append(btn('揭示答案',()=>{form.hidden=false;reason.focus();}),form);
          }else line.append(el('p','没有本地答案文件，无法揭示。','qa-muted'));
          out.append(line);
        }
        const rows=await api('/agent-quality/heldout/reveals');logs.replaceChildren(el('p',`揭示记录 ${rows.length} 条`));};
      paint().catch(error);return box;
    }
    let revision=0,compareHost=null,heldoutHost=null;
    const advanced=el('details',null,'aq-advanced');advanced.append(el('summary','更多评测工具：版本对比与独立评测集'));host.append(advanced);
    async function load(){const current=++revision;selectedEvaluation=null;state.target=target.value;clearError();fill();list.replaceChildren(el('p','正在读取评测记录…','qa-muted'));emptyDetail();historyCount.textContent='—';
      let rows;
      try{rows=await api(`/agent-quality/evaluations?target=${target.value}&brief=true`);}
      catch(err){
        if(!live()||current!==revision)return;
        const failure=Error(`读取评测记录失败：${err.message}`);failure.handled=true;
        if(current===revision){list.replaceChildren(el('p',failure.message,'qa-error'),btn('重新读取',()=>load().catch(error)));}
        throw failure;
      }
      if(!live()||current!==revision)return;
      list.replaceChildren();historyCount.textContent=`${rows.length} 份`;
      if(!rows.length)list.append(el('p','暂无历史评测。选择上方运行记录生成第一份。','aq-empty-list'));
      for(const row of rows){const item=btn('',()=>show(row));item.dataset.evaluationId=row.id;item.setAttribute('aria-pressed','false');const sourceRun=data.runs.find(run=>run.id===row.source_run);const title=sourceRun&&window.OPReportName?window.OPReportName.brief(sourceRun,data.cases):`${row.target==='business'?'业务 Agent':'功能测试 Agent'}评测`;item.append(el('strong',title),el('span',labels[row.program.decision]||row.program.decision,'aq-list-status'),el('small',`${stamp(row.created_at)} · 来源 ${row.source_run.slice(0,8)}`));list.append(item);}
      if(!compareHost){compareHost=el('div');advanced.append(compareHost);}
      compareHost.replaceChildren(comparePanel(rows));
      if(!heldoutHost){heldoutHost=el('div');advanced.append(heldoutHost);heldoutHost.append(heldoutPanel());}}
    const create=btn('生成程序核验',()=>job(create,async()=>{if(!source.value)throw Error('请先选择一份已结束运行');const row=await api('/agent-quality/evaluations',{target:target.value,run_id:source.value});await load();await show(row);}));create.classList.add('qa-primary');form.append(create);
    target.onchange=()=>load().catch(error);load().catch(error);
  }
  return {mount};
})();
