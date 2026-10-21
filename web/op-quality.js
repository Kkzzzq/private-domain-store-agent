window.OPQuality = (() => {
  const names = {mixed:"接口/UI与Agent组合执行",assistant:"业务 Agent 评测",functional:"业务功能测试",joint:"联合回归",rules:"规则 / 固定回归",live:"真实云端模型",browser:"浏览器用例",candidate:"候选未接入",active:"已接入",revoked:"已撤销",queued:"排队",planning:"AI规划排队",planning_running:"AI规划中",draft:"待批准",approved:"已批准",running:"运行中",completed:"执行完成",passed:"通过",failed:"失败",blocked:"阻塞",cancelled:"已取消",eligible:"满足本次范围门禁",not_eligible:"不满足门禁",not_selected:"未在这侧运行"};
  const label = value => names[value] || value;
  const shots = new Map();
  let shotsOwner = null;
  const releaseShots = () => { for(const url of shots.values())URL.revokeObjectURL(url); shots.clear(); };
  window.addEventListener("beforeunload",releaseShots);
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
  const toolDescriptions={
    query_store_data:"按身份查询本店配置、券、评价、本人购物车及授权订单物流售后；先过滤权限，再检索，实时核验。",
    merchant_help:"仅B端运营助手：讲解现有后台商品、优惠券、装修等功能的操作步骤，不代替用户保存。",
    search_product_images:"用多模态模型检索商品图片，保留SPU/SKU对应关系；图像不可用会明确标注。",
    check_inventory:"按 SKU 编号查询当前库存。",
    clarify_recommendation:"缺少预算、数量或偏好时，确定需要向用户追问的信息。",
    get_store_catalog:"了解本店分类、商品、价格范围及 SKU 库存，为推荐做准备。",
    low_inventory:"查询本店库存低于或等于预警阈值的 SKU。",
    merchant_overview:"查询本店经营概览。",
    prepare_product_draft:"生成待确认的商品配置提案，不直接创建或上架商品。",
    query_orders:"买家查本人在本店的订单；商家查本店订单。",
    recommend_products:"按预算、数量、品类和偏好筛选本店有货商品。",
    search_knowledge:"检索店铺知识库，查询售后、运费、养护及平台规则。",
    search_products:"检索名称、分类、描述、标签、SKU规格和参数，支持语义召回；买家仅可售，商家可查本店全部状态。",
    read_test_capabilities:"读取允许的测试环境、用例与执行能力。",
    propose_test_plan:"从授权用例中提出测试计划，批准后才能执行。"
  };
  function toolList(tools){
    const node=el("dl","qa-tool-list");
    for(const name of tools){const row=el("div","qa-tool-row");row.append(el("dt","",name),el("dd","",Object.prototype.hasOwnProperty.call(toolDescriptions,name)?toolDescriptions[name]:"暂无简要说明，请查看工具契约。"));node.append(row);}
    return node;
  }
  function mount(host, options) {
    const root=el("section","qa-workspace"); host.replaceChildren(root);
    const identity=sessionStorage.getItem("token_op");
    const valid=()=>root.isConnected&&sessionStorage.getItem("token_op")===identity;
    if(shotsOwner!==identity){releaseShots();shotsOwner=identity;}
    const AGENT_TABS=["testing-overview","testing-business","testing-evaluator","testing-functional"];
    const BATCH_LIMIT=10;
    const batchLimit=group=>RUN_ENVIRONMENT==="real-nanzhi"&&group.kind==="assistant"?1:BATCH_LIMIT;
    const RUN_BUDGET={max_calls:50,max_tokens:60000,timeout_seconds:1200};
    let RUN_ENVIRONMENT="isolated-local";
    const AGENT_ROUTE={business:"testing-business",evaluator:"testing-evaluator",functional:"testing-functional"};
    const AGENT_TITLE={business:"业务Agent",evaluator:"评测Agent",functional:"功能测试Agent"};
    const TYPE_LABEL={assistant:"Agent 测试用例",functional:"接口测试用例",browser:"UI 测试用例"};
    const TYPE_OF=row=>["registered_browser","real_shop_browser"].includes(row.adapter)?"browser":row.kind;
    const ADAPTER_LABEL={isolated_assistant_api:"隔离子进程 · 助手接口",registered_pytest:"固定 pytest 节点",registered_browser:"隔离浏览器（Edge/Chromium + 截图）",real_shop_browser:"实店 UI 自动化",real_shop_agent:"实店 Agent 真实模型",real_shop_api:"实店接口与数据库断言",declarative_assistant:"自定义助手用例",declarative_functional:"自定义功能步骤与硬断言"};
    const MODEL_FIELD={provider:"供应商标识",cloud_style:"云端协议",cloud_model:"云端模型",target_model:"被测业务Agent模型",debug_model:"OP合成调试模型",ollama_model:"本地模型",role:"被测角色",model:"模型",note:"说明",kind:"类型"};
    const CAPABILITY_LABEL={"qa.view":"查看测试中心","qa.assistant.run":"运行助手评测","qa.functional.run":"运行功能测试","qa.approve":"审批计划与历史清理"};
    const artifactLocks=new Map();
    let data, agents, selectedRun, selectedCase, selectedPlan, pending=false, caseState="active", caseType="all", caseQuery="", checked=new Set(), expanded=new Set(), comparison, flash, receipts=[], failures=[], reportDate="", refreshVersion=0, timer;
    const api=async(path,body,method="POST")=>{if(!valid())throw Error("账号或页面已变化");return options.api(path,body?{method,body:JSON.stringify(body)}:{});};
    const error=message=>{if(valid()){const notice=el("p","qa-error",message);root.prepend(notice);}};
    const failScreen=(message,detail)=>{
      if(!valid())return;
      const card=el("section","qa-card");
      card.append(el("h3","","无法读取 OP 测试能力"),el("p","qa-error",message));
      if(detail)card.append(el("p","qa-muted",detail));
      card.append(el("p","qa-muted","平台运营账号（平台管理员）默认拥有全部质量能力：qa.view / qa.assistant.run / qa.functional.run / qa.approve。若当前账号确实缺失授权，管理员可在 backend 目录执行 .venv/Scripts/python.exe -m app.quality.cli <账号名>，或执行 --all-operators 给所有平台运营补齐；服务重启时也会自动补齐。"));
      card.append(actions(button("重试",()=>{root.replaceChildren(el("p","qa-muted","正在读取OP测试能力…"));refresh();},true)));
      root.replaceChildren(card);
    };
    const can=cap=>data?.capabilities.capabilities.includes(cap);
    const canRun=kind=>kind==="joint"?can("qa.assistant.run")&&can("qa.functional.run"):can(`qa.${kind}.run`);
    /* 报告列表用登记用例名称区分报告；时间与编号只作为次要参考，避免一列时间戳无法辨认。 */
    const reportName=run=>window.OPReportName?window.OPReportName.brief(run,data?.cases):(run.name||clock(run.created_at).slice(0,16)+" 测试报告");
    const clock=value=>{if(!value)return "—";const text=String(value);const iso=/[zZ]|[+-]\d{2}:?\d{2}$/.test(text)?text:text+"Z";const time=new Date(iso);return isNaN(time.getTime())?String(value):time.toLocaleString("zh-CN",{hour12:false,timeZone:"Asia/Shanghai"});};
    const go=tab=>{location.hash="#/testing/"+tab.slice("testing-".length);};
    const agentOf=id=>(agents||[]).find(row=>row.id===id);
    const actions=(...nodes)=>{const box=el("div","qa-actions");for(const node of nodes)box.append(node);return box;};
    const itemNode=item=>typeof item==="string"?document.createTextNode(item):item;
    const list=items=>{const node=el("ul","qa-list");for(const item of items){const row=el("li");row.append(itemNode(item));node.append(row);}return node;};
    const steps=items=>{const node=el("ol","qa-list");for(const item of items){const row=el("li");row.append(itemNode(item));node.append(row);}return node;};
    const mono=text=>el("code","qa-code",text);
    function table(headers,rows){
      const node=el("table","qa-table"),head=el("thead"),headRow=el("tr");
      for(const text of headers)headRow.append(el("th","",text));head.append(headRow);
      const body=el("tbody");
      for(const row of rows){const tr=el("tr");for(const cell of row){const td=el("td");td.append(itemNode(cell));tr.append(td);}body.append(tr);}
      node.append(head,body);return node;
    }
    const statBox=(value,caption)=>{const box=el("div");box.append(el("strong","",value==null?"—":String(value)),el("span","",caption));return box;};
    const modelSummary=model=>!model?"未返回":Object.entries(model).filter(([key])=>key!=="note").map(([key,value])=>`${MODEL_FIELD[key]||key}=${value}`).join(" · ")||"未配置";
    const modeFor=row=>row.kind==="assistant"?"live":"rules";
    function runCounts(run){const counts={passed:0,failed:0,blocked:0,cancelled:0,running:0,other:0};for(const row of run.results||[]){if(Object.prototype.hasOwnProperty.call(counts,row.status))counts[row.status]++;else counts.other++;}return counts;}
    function runReason(run){
      if(run.summary?.error)return run.summary.error;
      const bad=(run.results||[]).filter(row=>["failed","blocked","cancelled"].includes(row.status));
      if(bad.length)return bad.map(row=>`${row.id}${row.evidence?.error?"（"+row.evidence.error+"）":""}`).join("；");
      return run.status==="cancelled"?"运行已被取消，未跑完全部用例。":"报告未给出具体原因，请查看运行详情里的断言与证据。";
    }
    const runGroups=rows=>{
      const groups=new Map();
      for(const row of rows){if(row.kind==="joint")continue;const kind=row.kind==="assistant"?"assistant":"functional";const mode=kind==="assistant"?modeFor(row):"rules";const key=kind+"|"+mode;if(!groups.has(key))groups.set(key,{kind,mode,ids:[]});groups.get(key).ids.push(row.id);}
      return Array.from(groups.values());
    };
    function runBlock(row){
      if(RUN_ENVIRONMENT==="real-nanzhi"&&!String(row.adapter).startsWith("real_shop_"))return "此用例是历史隔离诊断，尚未接入实店执行器。";
      if(row.state!=="active")return "候选用例未接入，不能运行；先在「测试用例管理」里审核启用。";
      if(row.kind==="assistant"&&!(row.modes||[]).includes("live"))return "未支持真实模型，不能进行正式Agent评测。";
      if(row.kind==="assistant"&&!can("qa.assistant.run"))return "缺少 qa.assistant.run 能力，不能运行助手评测。";
      if(row.kind!=="assistant"&&!can("qa.functional.run"))return "缺少 qa.functional.run 能力，不能运行功能测试。";
      if(!can("qa.approve"))return "缺少 qa.approve 能力；运行按钮在同一次点击内完成批准与启动。";
      return "";
    }
    const canRunRow=row=>!runBlock(row);
    async function refresh(){
      const revision=++refreshVersion;
      try{
        const wanted=["/capabilities","/cases","/plans",reportDate?"/runs?report_date="+encodeURIComponent(reportDate):"/runs"];
        if(AGENT_TABS.includes(options.tab))wanted.push("/agents");
        const [capabilities,cases,plans,runs,agentsPayload]=await Promise.all(wanted.map(path=>api(path)));
        if(!valid()||revision!==refreshVersion)return;
        data={capabilities,cases,plans,runs};
        RUN_ENVIRONMENT=capabilities.real_shop?"real-nanzhi":"isolated-local";
        agents=agentsPayload?.agents;
        paint();poll();
      }catch(err){
        if(!data){
          if(err.status===403)failScreen("当前账号没有 OP 质量能力授权："+err.message,"该账号不是平台运营，或质量能力未授予。");
          else if(err.status===401)failScreen("登录状态已失效，请重新进入运营台。");
          else failScreen("请求失败："+err.message,"请检查后端服务与网络后重试。");
        }else{
          error(err.message);
        }
      }
    }
    const typing=()=>{const node=document.activeElement;return !!node&&root.contains(node)&&["INPUT","TEXTAREA"].includes(node.tagName);};
    function poll(){
      clearTimeout(timer);
      if(!valid())return;
      const active=data.runs.some(run=>["queued","running"].includes(run.status))||data.plans.some(plan=>["planning","planning_running"].includes(plan.status));
      if(active)timer=setTimeout(()=>{if(valid()&&!pending&&!root.querySelector("dialog[open]")&&!typing())refresh();else if(valid())poll();},1500);
    }
    async function action(callback){if(pending)return;pending=true;try{await callback();await refresh();}catch(err){error(err.message);}finally{pending=false;}}
    function badge(value){return el("span",`qa-badge qa-${value}`,label(value));}
    function heading(title,description){const node=el("div","qa-heading");const copy=el("div");copy.append(el("h2","",title),el("p","",description));node.append(copy);return node;}
    const envNote=()=>el("p","qa-environment",RUN_ENVIRONMENT==="real-nanzhi"?"测试目标：线上南枝小店真实数据库。接口、Agent、UI均访问真实站点；仅修改本轮新增测试记录，订单与审计保留。演示支付和物流不调用外部服务。":"业务数据：独立合成SQLite / 内存Redis，每条用例单独子进程。真实模式使用云端聊天模型；RAG用例使用独立Embedding与Chroma。");
    function paint(){
      if(!valid())return;root.replaceChildren();
      if(flash){root.append(el("p","qa-notice",flash));flash=null;}
      if(options.tab==="testing-overview")return renderOverview();
      if(options.tab==="testing-business")return renderAgentWorkspace("business");
      if(options.tab==="testing-evaluator")return renderAgentWorkspace("evaluator","assistant");
      if(options.tab==="testing-functional")return renderAgentWorkspace("functional","functional");
      if(options.tab==="testing-cases")return renderCases();
      if(options.tab==="testing-runs")return renderRunsPage();
      return renderOverview();
    }
    function renderOverview(){
      if(window.OPAgentExperience)return window.OPAgentExperience.overview(root,{agents,data,go});
      root.append(heading("Agent总览","三类 Agent 的职责、实时统计与入口；接入用例数与通过数量分开统计，本页只展示单次运行结果，不计算全量完成率。"));
      root.append(el("p","qa-notice",`业务Agent负责对话与业务工具；评测Agent验证助手；功能测试Agent验证业务状态。两类测试均可新建候选用例，审核后真实模型规划执行。测试模型：${agentOf("evaluator")?.model?.cloud_model||"待后端加载独立测试配置"}，不影响商城模型。`));
      root.append(el("p","qa-notice",`报告与截图保留 ${data.capabilities.retention?.days||"—"} 天后自动删除；计划与活动任务保留。手动清理入口在「测试用例报告」页。`));
      if(!agents)root.append(el("p","qa-muted","正在读取三类 Agent 说明…"));
      const grid=el("div","qa-agent-grid");
      for(const row of agents||[]){
        const card=el("article","qa-card"),stats=row.stats||{};
        card.append(el("h3","",row.name),el("p","",row.role));
        if(row.id==="business"){
          const strip=el("div","qa-stat");strip.append(statBox(stats.tool_count??row.tools?.length,"业务工具"),statBox(stats.dialogues,"本人7天内缓存对话（最多10条）"));
          card.append(strip,el("p","qa-muted","直接输入问题，查看回答、工具、知识来源和上下文；不要求预期答案，不在这里评判用例通过率。"),el("p","qa-muted",`商城 ${row.model?.cloud_model||"未读取"} · 合成调试 ${row.model?.debug_model||"未读取"}`),actions(button("进入业务对话",()=>go("testing-business"),true)));grid.append(card);continue;
        }
        const strip=el("div","qa-stat");
        strip.append(statBox(stats.active_cases,"接入用例数（≠通过数）"),statBox(stats.documented_cases,"已登记步骤文档数"),statBox(stats.runs,"运行次数"),statBox(stats.last_run?label(stats.last_run.status):"无","最近一次运行状态"));
        card.append(strip);
        card.append(el("p","qa-muted",`已审核自建用例 ${stats.custom_cases??"—"} · 近200条记录中正式真实模型测试 ${stats.formal_runs??"—"} / 平台诊断或旧记录 ${stats.diagnostic_runs??"—"}`));
        const addCase=button(row.id==="functional"?"新增功能用例":"新增助手用例",()=>row.id==="functional"?functionalCaseDialog():caseDialog());addCase.disabled=!can(`qa.${row.kind}.run`);card.append(actions(addCase));
        card.append(el("p","qa-muted",stats.last_run?`最近一次运行：${clock(stats.last_run.created_at)} · 模式 ${label(stats.last_run.mode)} · 结论 ${stats.last_run.decision?label(stats.last_run.decision):"尚未形成"}`:"该 Agent 还没有运行记录，接入数量不代表已通过。"));
        const latest=stats.last_run&&data.runs.find(run=>run.id===stats.last_run.id);
        if(latest){const counts=runCounts(latest);card.append(el("p","qa-muted",`该次运行用例通过 ${counts.passed} / ${latest.results.length}（仅该次运行结果，不代表全量完成率）`));}
        card.append(el("p","qa-muted",`模型：${modelSummary(row.model)}；工具：${(row.tools||[]).length?row.tools.join("、"):"不调用模型工具"}`));
        if(AGENT_ROUTE[row.id])card.append(actions(button("进入该页",()=>go(AGENT_ROUTE[row.id]),true)));
        grid.append(card);
      }
      root.append(grid);
      const limits=el("section","qa-card");limits.append(el("h3","","统计口径与限制"));
      limits.append(list((data.capabilities.limitations||[]).concat([`用例目录版本：${data.capabilities.catalog_version}`,`运行上限：每条计划最多 ${data.capabilities.limits?.max_cases||BATCH_LIMIT} 条用例、${data.capabilities.limits?.max_calls||20} 次模型调用、${data.capabilities.limits?.max_tokens||30000} tokens`])));
      root.append(limits);
      if(receipts.length)renderReceipts();
    }
    function renderAgentWorkspace(id,kind){
      const reference=renderAgentPage(id);
      if(kind)renderEvaluation(kind);
      if(reference)root.append(reference);
    }
    function renderAgentPage(id){
      const row=agentOf(id);
      if(!row){root.append(heading("Agent 说明",agents?"后端未返回该 Agent 的说明，请刷新重试。":"正在读取该 Agent 的说明…"));return;}
      root.append(heading(AGENT_TITLE[id]||row.name,row.role));
      // 功能测试页：先让运营用自己的话输入需求，Agent 判断可否实现，再走批准的既有执行链。
      if(id==="functional")window.OPFunctionalIntake?.mount(root,{api,refresh,data});
      window.OPAgentExperience?.context(root,{id,row,data});
      window.OPAgentQuality?.mount(root,{id,data,api,refresh});
      if(window.OPAgentObservatory){
        const visualHost=el("div");root.append(visualHost);
        window.OPAgentObservatory.mount(visualHost,{agent:id,descriptor:row,cases:data.cases,
          runs:data.runs.map(run=>({...run,name:window.OPReportName?window.OPReportName.label(run,data.cases,{status:label(run.status),time:true}):run.name})),
          capabilities:data.capabilities.capabilities,api,refresh,alive:valid});
      }
      const reference=el("details","qa-agent-reference");reference.open=true;reference.append(el("summary","","查看能力说明、使用方法与源码"));
      const card=el("section","qa-card");
      const stats=id==="business"?{}:row.stats||{};
      const strip=el("div","qa-stat");
      if(id!=="business")strip.append(statBox(stats.active_cases,"接入用例数（≠通过数）"),statBox(stats.documented_cases,"已登记步骤文档数"),statBox(stats.runs,"运行次数"),statBox(stats.last_run?label(stats.last_run.status):"无","最近一次运行"));
      card.append(el("p","qa-muted",`接口登记名：${row.name} · 类型 ${id==="business"?"业务对话":label(row.kind)}`),strip,el("p","qa-muted",id==="business"?"对话记录与实际模型调用见上方工作台。":stats.last_run?`最近一次运行 ${String(stats.last_run.id).slice(0,8)} · ${clock(stats.last_run.created_at)} · 模式 ${label(stats.last_run.mode)} · 结论 ${stats.last_run.decision?label(stats.last_run.decision):"尚未形成"}`:"尚无运行记录。"),el("h4","","角色与用途"),el("p","",row.purpose),el("h4","","入口接口"),table(["入口","实际接口"],(row.entry_points||[]).map(item=>[item.name,mono(item.value)])));
      card.append(el("h4","","当前模型"),table(["字段","值"],Object.entries(row.model||{}).map(([key,value])=>[MODEL_FIELD[key]||key,String(value)])),el("p","qa-muted",`模型摘要：${modelSummary(row.model)}`));
      card.append(el("h4","","工具清单"));
      const tools=Array.from(new Set([...(row.tools||[]),...(row.planner_tools||[])]));
      card.append(tools.length?toolList(tools):el("p","qa-muted","执行阶段使用固定业务断言，不以模型回答代替验证。"));
      card.append(el("h4","","护栏"),list(row.guardrails||[]),el("h4","","怎么用"),steps(row.how_to_use||[]),el("h4","","怎么改"),table(["要改什么","改哪里"],(row.how_to_modify||[]).map(item=>[item.what,mono(item.where)])));
      card.append(el("h4","","源码文件"),list((row.sources||[]).map(path=>mono(path))));
      card.append(el("h4","","能力门控"),list((row.capabilities||[]).map(cap=>`${cap}：${CAPABILITY_LABEL[cap]||cap}`)));
      reference.append(card);return reference;
    }
    function renderEvaluation(kind){
      const controls=el("div","qa-actions");
      const create=button(kind==="assistant"?"新建评测计划":"新建功能测试计划",()=>compose(kind),true);
      create.disabled=!can(`qa.${kind}.run`);
      controls.append(create,button("刷新",refresh));
      const addCase=button(kind==="functional"?"新增功能用例":"新增助手用例",()=>kind==="functional"?functionalCaseDialog():caseDialog());addCase.disabled=!can(`qa.${kind}.run`);controls.append(addCase);
      if(data.runs.length>=2)controls.append(button("版本报告对比",compareDialog));
      if(can('qa.approve'))controls.append(button("历史保留与清理",retentionDialog));
      root.append(controls);
      root.append(el("p","qa-muted",kind==="assistant"?"本页只列 kind=assistant 的计划与运行；批准绑定 digest，改动后必须重新批准。":"本页只列 kind=functional 的计划与运行；功能回归走固定执行器，不消耗被测模型。"));
      root.append(envNote());
      if(comparison)renderComparison();
      renderPlans(kind);renderRunsSection(kind);
      if(selectedPlan)renderPlan(data.plans.find(plan=>plan.id===selectedPlan));
    }
    function renderComparison(){
      const dimension={environment_id:"测试环境",fixture_version:"fixture版本",mode:"执行模式",unfinished_run:"运行未结束"};
      const panel=el('section','qa-card');panel.append(el('h3','','报告差异'),el('p','qa-muted',comparison.note));
      if(comparison.incompatible_dimensions.length)panel.append(el('p','qa-error','不可比维度：'+comparison.incompatible_dimensions.map(key=>dimension[key]||key).join('、')));
      for(const row of comparison.cases){const reason=row.before==='not_selected'?'仅候选运行包含，单列不计入回归判定':row.after==='not_selected'?'仅基线运行包含，单列不计入回归判定':'用例版本或条件不同，不可比较';panel.append(el('p','',`${row.id}：${label(row.before)} → ${label(row.after)} · ${row.comparable?row.transition==='regressed'?'发生回归':row.transition==='improved'?'已改善':'未变化':reason}`));}
      root.append(panel);
    }
    function renderReceipts(){
      const card=el("section","qa-card qa-receipt");
      card.append(el("h3","","本次运行回执"),el("p","qa-muted","批准与启动已在同一次点击内完成；报告与截图保留后会自动清理。"));
      for(const item of receipts){const line=el("p");line.append(document.createTextNode(`${TYPE_LABEL[item.kind]||label(item.kind)} · ${label(item.mode)} · ${item.count} 条用例 · 计划 `),mono(item.plan),document.createTextNode(" · 运行 "),mono(item.run));card.append(line);}
      for(const item of failures)card.append(el("p","qa-error",`${TYPE_LABEL[item.kind]||label(item.kind)}（${item.ids.join("、")}）未启动：${item.error}`));
      card.append(actions(button("查看测试用例报告",()=>go("testing-runs"),true),button("清除回执",()=>{receipts=[];failures=[];paint();})));
      root.append(card);
    }
    function renderPlans(kind){
      const plans=data.plans.filter(plan=>plan.payload.kind===kind);
      const section=el("section","qa-card");section.append(el("h3","","计划与审批"));
      if(!plans.length)section.append(el("p","qa-muted","尚无该类型的计划。选择已接入用例，先生成并审核，再启动运行。"));
      for(const plan of plans.slice(0,6)){
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
    function renderRunsPage(){
      root.append(heading("测试用例报告","每条运行的用例数、通过/失败/阻塞计数与代码版本；失败必标注原因，UI 用例可直接查看截图。"));
      root.append(el("p","qa-notice",data.capabilities.retention?.notice||`运行报告与截图保留 ${data.capabilities.retention?.days||"—"} 天后自动删除；计划与活动任务保留。`));
      const controls=el("div","qa-actions");controls.append(button("刷新",refresh));
      const date=el("input");date.type="date";date.value=reportDate;date.setAttribute("aria-label","报告日期（北京时间）");date.onchange=()=>{reportDate=date.value;selectedRun=null;selectedCase=null;refresh();};controls.append(el("label","","报告日期（北京时间）"),date,button("最近报告",()=>{reportDate="";selectedRun=null;refresh();}));
      if(data.runs.length>=2)controls.append(button("版本报告对比",compareDialog));
      if(can('qa.approve'))controls.append(button("历史保留与清理",retentionDialog));
      root.append(controls);
      root.append(el("p","qa-muted","保留策略为自动清理（默认 7 天），也可用「历史保留与清理」手动预览并清理超期报告；只删已结束的运行与不再被引用的截图。"));
      root.append(envNote());
      if(comparison)renderComparison();
      if(receipts.length)renderReceipts();
      renderRunsSection("all");
    }
    function renderRunsSection(kind){
      const section=el("section","qa-card");section.append(el("h3","","最近测试用例报告（最多 100 份）"));
      let rows=kind==="all"?data.runs:data.runs.filter(run=>run.kind===kind||run.report_batch&&run.results.some(row=>row.kind===kind));
      if(kind==="all"&&options.tab==="testing-runs")rows=rows.filter(run=>["completed","failed","blocked","cancelled"].includes(run.status));
      if(!rows.length)section.append(el("p","qa-muted",kind==="all"?"尚未运行测试，不展示虚构通过率。需启动独立quality worker处理队列。":"该类型还没有运行记录；全部报告在「测试用例报告」页。"));
      for(const run of rows.slice(0,100)){
        const counts=runCounts(run);
        const broken=run.status==="failed"||counts.failed>0, halted=run.status==="blocked"||counts.blocked>0, stopped=run.status==="cancelled";
        const row=el("div",broken||halted||stopped?"qa-case-row qa-run-failed":"qa-case-row");
        const toggle=button(`${reportName(run)} · ${label(run.kind)}`,()=>{selectedRun=selectedRun===run.id?null:run.id;selectedCase=null;const y=window.scrollY;paint();window.scrollTo({top:y,behavior:"instant"});});toggle.setAttribute("aria-expanded",String(selectedRun===run.id));
        row.append(toggle,badge(run.status),
          el("span","qa-muted",`${run.target?.environment_id==="real-nanzhi"?"线上南枝实店验收":run.diagnostic===false?"正式真实模型测试":"平台诊断/旧记录（非正式验收）"} · ${label(run.mode)} · 用例 ${run.results.length} 条 · 报告 ${String(run.id).slice(0,6)}`),
          el("span",broken||halted?"qa-error":"qa-pass",`通过 ${counts.passed} / 失败 ${counts.failed} / 阻塞 ${counts.blocked}`),
          el("span","qa-muted",`开始 ${clock(run.started_at||run.created_at)} · 结束 ${clock(run.finished_at)}`),
          el("span","qa-muted",`代码 ${String(run.target?.target_revision||"").slice(0,12)||"—"}`));
        if(broken||halted||stopped)row.append(el("span","qa-error",`失败原因：${runReason(run)}`));
        row.dataset.runId=run.id;section.append(row);
        if(selectedRun===run.id)renderRun(run,section);
      }root.append(section);
    }
    function renderRun(run,container=root){
      if(!run)return;
      const section=el("section","qa-run-detail");const head=heading(reportName(run),`${label(run.kind)} · ${label(run.status)} · ${run.summary.decision?label(run.summary.decision):"尚未形成结论"}`);
      const controls=el("div","qa-actions");
      if(["queued","running"].includes(run.status)){const cancel=button(run.cancel_requested?"等待取消确认":"取消运行",()=>action(()=>api(`/runs/${run.id}/cancel`,{})));cancel.disabled=!canRun(run.kind);controls.append(cancel);}
      const rerun=button("新建重跑",()=>action(async()=>{const next=await api(`/runs/${run.id}/rerun`,{});selectedRun=next.id;}));rerun.disabled=!canRun(run.kind);controls.append(rerun);
      controls.append(button("导出脱敏JSON",()=>{const url=URL.createObjectURL(new Blob([JSON.stringify(run,null,2)],{type:"application/json"}));const link=el("a");link.href=url;link.download=`quality-${run.id}.json`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}));head.append(controls);section.append(head);
      section.append(el("p","qa-muted",`测试环境：${run.target?.environment_id||"未记录"} · 报告编号 ${run.id}`));
      const counts=runCounts(run);
      if(["failed","blocked","cancelled"].includes(run.status)||counts.failed||counts.blocked)section.append(el("p","qa-error",`失败原因：${runReason(run)}`));
      else if(run.summary.error)section.append(el("p","qa-error",`失败原因：${run.summary.error}`));
      const layout=el("div","qa-evidence-grid");const cases=el("div","qa-evidence-column");cases.append(el("h3","","用例 / 真实状态"));
      for(const row of run.results){const snapshot=run.target?.case_snapshots?.find(entry=>entry.id===row.id);const item=button(`${row.id} ${snapshot?.title||data.cases.find(entry=>entry.id===row.id)?.title||""}`,()=>{selectedCase=row.id;paint();});item.classList.toggle("selected",(selectedCase||run.results[0]?.id)===row.id);item.classList.add("qa-result-"+row.status);item.append(badge(row.status));cases.append(item);if(["failed","blocked","cancelled"].includes(row.status)&&row.evidence?.error)cases.append(el("p","qa-error",`${row.id}：${row.evidence.error}`));}
      const row=run.results.find(entry=>entry.id===(selectedCase||run.results[0]?.id));const evidence=row?.evidence||{};
      const middle=el("div","qa-evidence-column"),right=el("div","qa-evidence-column");middle.append(el("h3","",row?.kind==="assistant"?"测试对话与工具轨迹":"API步骤与状态证据"));right.append(el("h3","","可信事实与固定断言"));
      const snapshot=run.target?.case_snapshots?.find(entry=>entry.id===row?.id);
      const doc=row?.doc||data.cases.find(entry=>entry.id===row?.id)?.doc||{};
      middle.prepend(el("h3","",snapshot?.title||data.cases.find(entry=>entry.id===row?.id)?.title||row?.id||"等待用例"));
      middle.append(el("h4","","测试步骤（中文）"),steps(doc.steps||[]),el("h4","","预期结果"),list(doc.expected||[]),el("h4","","实际结果"));
      middle.append(el("p",row?.status==="passed"?"qa-pass":["failed","blocked","cancelled"].includes(row?.status)?"qa-error":"qa-muted",row?.status==="passed"?"实际执行通过；下方展示真实请求、响应和断言结果。":row?.status==="failed"?"实际执行失败："+(evidence.error||"请查看失败断言"):row?.status==="blocked"?"执行阻塞："+(evidence.error||"缺少执行证据"):"当前状态："+label(row?.status||"queued")));
      if(evidence.suite?.reports)for(const result of evidence.suite.reports)middle.append(el("p","qa-muted",`${result.node||row.id} · ${result.stage||"执行"}：${result.outcome==="passed"?"通过":result.outcome==="failed"?"失败":result.outcome}`));
      if(evidence.error)middle.append(el("p","qa-error",evidence.error));
      const artifacts=evidence.artifacts||[];
      if(artifacts.length){middle.append(el("h4","","UI 用例截图（点击放大）"));const box=el("div","qa-shots");for(const artifact of artifacts)box.append(shotThumb(run.id,artifact));middle.append(box);}
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
      for(const check of evidence.assertions||[]){const item=el("div",check.passed?"qa-assert qa-pass":"qa-assert qa-error");item.append(el("strong","",`${check.passed?"通过":"失败"} · ${check.name}`));if(check.expected!=null||check.actual!=null)item.append(el("h5","","预期结果"),pre(check.expected??"断言条件成立"),el("h5","","实际结果"),pre(check.actual??(check.passed?"条件成立":"条件不成立")));right.append(item);}
      if(!evidence.assertions?.length)right.append(el("p","qa-muted","尚无有效断言结果，不算通过。"));
      if(evidence.budget)right.append(el("h4","","模型预算 / 实际来源"),pre(evidence.budget));
      right.append(el("p","qa-muted",`${run.target?.environment_id==="real-nanzhi"?"本轮记录归档":"隔离清理"}：${evidence.cleanup_ok===true?"已确认":evidence.cleanup_ok===false?"未确认":"尚未执行"}`));
      if(evidence.cleanup)right.append(pre(evidence.cleanup));
      layout.append(cases,middle,right);section.append(layout);container.append(section);
    }
    async function shotUrl(runId,artifactId){
      const key=runId+":"+artifactId;
      if(shots.has(key))return shots.get(key);
      if(!artifactLocks.has(key)){
        const task=(async()=>{
          const response=await fetch(`/api/v1/op/qa/runs/${encodeURIComponent(runId)}/artifacts/${encodeURIComponent(artifactId)}`,{headers:{Authorization:'Bearer '+identity}});
          if(!response.ok)throw Error('截图读取失败或无权限');
          const url=URL.createObjectURL(await response.blob());shots.set(key,url);artifactLocks.delete(key);return url;
        })();
        artifactLocks.set(key,task);task.catch(()=>artifactLocks.delete(key));
      }
      return artifactLocks.get(key);
    }
    function shotThumb(runId,artifact){
      const holder=el("figure","qa-shot"),picture=el("img","qa-thumb"),caption=el("span","qa-muted","加载截图中…");
      picture.alt="UI用例截图";holder.append(picture,caption);holder.title="点击放大截图";holder.onclick=()=>showArtifact(runId,artifact.id);
      shotUrl(runId,artifact.id).then(url=>{if(!valid()||!holder.isConnected)return;picture.src=url;caption.remove();}).catch(err=>{caption.textContent=err.message;});
      return holder;
    }
    async function showArtifact(runId,artifactId){
      try{const url=await shotUrl(runId,artifactId);if(!valid())return;const dialog=el('dialog','qa-dialog qa-wide'),picture=el('img','qa-full');picture.src=url;picture.alt='UI自动化测试截图';dialog.append(button('关闭',()=>dialog.close()),picture);dialog.addEventListener('close',()=>dialog.remove(),{once:true});root.append(dialog);dialog.showModal();}catch(err){error(err.message);}
    }
    function compareDialog(){
      const dialog=el('dialog','qa-dialog'),form=el('form','qa-form'),baseline=el('select'),candidate=el('select'),message=el('p','qa-error');
      form.append(el('h2','','版本报告对比'));
      for(const run of data.runs){for(const select of [baseline,candidate]){const option=el('option','',`${run.id.slice(0,8)} · ${label(run.kind)} · ${label(run.status)}`);option.value=run.id;select.append(option);}}
      candidate.selectedIndex=Math.min(1,data.runs.length-1);baseline.setAttribute('aria-label','基线运行');candidate.setAttribute('aria-label','候选运行');form.append(el('label','','基线运行'),baseline,el('label','','候选运行'),candidate,message,button('生成对比',async()=>{try{comparison=await api(`/compare?baseline=${encodeURIComponent(baseline.value)}&candidate=${encodeURIComponent(candidate.value)}`);dialog.close();paint();}catch(err){message.textContent=err.message;}}),button('取消',()=>dialog.close()));dialog.append(form);dialog.addEventListener('close',()=>dialog.remove(),{once:true});root.append(dialog);dialog.showModal();
    }
    function retentionDialog(){
      const dialog=el('dialog','qa-dialog'),form=el('div','qa-form'),days=el('input'),result=el('p'),consent=el('input'),notice=el('label'),remove=button('确认清理预览范围',async()=>{if(!consent.checked||!preview)return;try{const done=await api('/retention/apply',{days:preview.days,digest:preview.digest});flash=`已清理${done.deleted_runs}次历史运行；${done.artifact_cleanup_errors.length}项截图清理异常。计划保留。`;remove.disabled=true;dialog.close();await refresh();}catch(err){result.textContent=err.message;}});let preview;
      days.type='number';days.min='7';days.max='3650';days.value=String(data.capabilities.retention?.days||7);days.setAttribute('aria-label','保留天数');consent.type='checkbox';notice.append(consent,document.createTextNode('确认删除已预览的历史运行，不可撤销'));remove.disabled=true;consent.onchange=()=>{remove.disabled=!consent.checked||!preview?.count;};days.oninput=()=>{preview=null;remove.disabled=true;};form.append(el('h2','','历史保留与清理'),el('p','qa-muted','先预览再确认；活动任务与计划不会删除。报告与截图按保留策略自动清理，此处为手动清理入口。'),days,button('预览清理范围',async()=>{try{preview=await api('/retention/preview',{days:Number(days.value)});result.textContent=`将清理${preview.count}次已结束的历史运行。${preview.truncated?`本次只处理最早${preview.count}次，另有${preview.remaining}次仍超期，可再次预览清理。`:''}${preview.notice}`;consent.checked=false;remove.disabled=true;}catch(err){result.textContent=err.message;}}),result,notice,remove,button('关闭',()=>dialog.close()));dialog.append(form);dialog.addEventListener('close',()=>dialog.remove(),{once:true});root.append(dialog);dialog.showModal();
    }
    function functionalCaseDialog(previous){
      const dialog=el("dialog","qa-dialog"),form=el("form","qa-form"),title=el("input"),steps=el("div"),fields=[],message=el("p","qa-error");
      title.required=true;title.maxLength=80;title.value=previous?.definition?.title||"";title.setAttribute("aria-label","功能用例名称");
      const labeled=(section,text,input)=>{input.setAttribute("aria-label",text);const label=el("label","",text);label.append(input);section.append(label);};
      const select=(values,value)=>{const node=el("select");for(const [id,text]of values){const option=el("option","",text);option.value=id;node.append(option);}node.value=value;return node;};
      function addStep(saved={}){
        if(fields.length>=12)return;
        const section=el("section","qa-card"),action=select([["catalog","浏览商品列表"],["product","查看商品详情"],["cart","读取购物车"],["add_cart","加入购物车"],["orders","查询本人订单"]],saved.action||"catalog"),role=select([["customer","合成买家"],["merchant","合成商家"],["anonymous","匿名"]],saved.role||"customer");
        const product=el("input"),sku=el("input"),quantity=el("input"),status=el("input"),checks=el("textarea");
        for(const input of [product,sku,quantity,status])input.type="number";
        product.value=saved.product_id??"";sku.value=saved.sku_id??"";quantity.value=saved.quantity??1;status.value=saved.expected_status??200;
        checks.value=JSON.stringify(saved.checks||[],null,2);checks.rows=3;checks.maxLength=5000;
        section.append(el("h4","","业务步骤（按添加顺序执行）"));
        for(const [text,input]of [["业务动作",action],["步骤身份",role],["商品ID（详情动作必填）",product],["SKU ID（加购必填）",sku],["数量",quantity],["预期HTTP状态",status],["JSON字段断言（可选数组）",checks]])labeled(section,text,input);
        const record={section,action,role,product,sku,quantity,status,checks};fields.push(record);
        section.append(button("删除此步骤",()=>{if(fields.length<=1)return;fields.splice(fields.indexOf(record),1);section.remove();}));steps.append(section);
      }
      for(const step of previous?.definition?.steps||[{}])addStep(step);
      form.append(el("h2","",previous?"编辑功能用例或新建版本":"新增功能用例"),el("p","qa-muted","只执行固定业务动作与合成身份；不能输入URL、SQL或脚本。每步必验HTTP状态。字段断言示例：[{\"path\":\"items\",\"operator\":\"length\",\"value\":1}]。保存为候选，审核后才能运行。"));
      labeled(form,"功能用例名称",title);form.append(steps,button("增加业务步骤",()=>addStep()),message);
      const submit=el("button","qa-primary","保存功能候选");submit.type="submit";form.append(actions(button("取消",()=>dialog.close()),submit));
      form.onsubmit=async event=>{event.preventDefault();submit.disabled=true;try{
        const definition={kind:"functional",title:title.value,steps:fields.map(row=>({action:row.action.value,role:row.role.value,product_id:row.product.value?Number(row.product.value):null,sku_id:row.sku.value?Number(row.sku.value):null,quantity:Number(row.quantity.value),expected_status:Number(row.status.value),checks:JSON.parse(row.checks.value||"[]")}))};
        const path=previous?(previous.state==="candidate"?`/cases/${previous.id}`:`/cases/${previous.id}/revisions`):"/cases";
        await api(path,definition,previous?.state==="candidate"?"PATCH":"POST");caseState="candidate";dialog.close();await refresh();
      }catch(error){message.textContent=error.message;}finally{submit.disabled=false;}};
      dialog.append(form);dialog.addEventListener("close",()=>dialog.remove(),{once:true});root.append(dialog);dialog.showModal();
    }
    function caseDialog(previous){
      const dialog=el('dialog','qa-dialog'),form=el('form','qa-form'),title=el('input'),role=el('select'),turns=el('div'),message=el('p','qa-error'),fields=[];
      title.required=true;title.maxLength=80;title.value=previous?.definition?.title||'';title.setAttribute('aria-label','用例名称');for(const [value,text] of [['customer','买家'],['merchant','商家']]){const option=el('option','',text);option.value=value;role.append(option);}role.value=previous?.definition?.role||'customer';role.setAttribute('aria-label','被测角色');
const addTurn=(saved={})=>{if(fields.length>=5)return;const section=el('section','qa-card'),question=el('textarea'),tools=el('input'),contains=el('input'),forbidden=el('input'),price=el('input');question.required=true;question.maxLength=1000;question.value=saved.message||'';tools.value=(saved.required_tools||[]).join(',');contains.value=(saved.expected_contains||[]).join(',');forbidden.value=(saved.forbidden_contains||[]).join(',');price.type='number';price.min='0';price.step='0.01';price.value=saved.max_product_price==null?'':String(saved.max_product_price);for(const [node,name]of [[question,'用户输入'],[tools,'必须调用的工具名'],[contains,'回答必须包含'],[forbidden,'回答不得包含'],[price,'商品卡最高单价（可选）']]){node.setAttribute('aria-label',`第${fields.length+1}轮${name}`);section.append(el('label','',name),node);}section.prepend(el('h3','',`第${fields.length+1}轮`));turns.append(section);fields.push({question,tools,contains,forbidden,price});};
      for(const saved of previous?.definition?.turns||[{}])addTurn(saved);form.append(el('h2','',previous?'编辑或创建新版本':'新增助手用例'),el('p','qa-muted','仅声明输入与硬断言，不执行自定义代码、SQL或URL。保存为候选，审核后才能运行；已审核版本保持不变。每轮至少配置一项断言，多个词或工具名用逗号分隔。'),el('label','','用例名称'),title,el('label','','被测角色'),role,turns,button('添加一轮',()=>addTurn()),message);
      const submit=el('button','qa-primary','保存候选');submit.type='submit';form.append(submit,button('取消',()=>dialog.close()));const split=value=>value.split(/[,，\n]/).map(word=>word.trim()).filter(Boolean);form.onsubmit=async event=>{event.preventDefault();submit.disabled=true;try{const definition={title:title.value,role:role.value,turns:fields.map(field=>({message:field.question.value,required_tools:split(field.tools.value),expected_contains:split(field.contains.value),forbidden_contains:split(field.forbidden.value),max_product_price:field.price.value===''?null:Number(field.price.value)}))};const path=previous?`/cases/${previous.id}${previous.state==='candidate'?'':'/revisions'}`:'/cases';await api(path,definition,previous?.state==='candidate'?'PATCH':'POST');caseState='candidate';dialog.close();await refresh();}catch(err){message.textContent=err.message;}finally{submit.disabled=false;}};dialog.append(form);dialog.addEventListener('close',()=>dialog.remove(),{once:true});root.append(dialog);dialog.showModal();
    }
    function renderCases(){
      root.append(heading("测试用例管理","按 Agent、接口、UI 自动化分类管理；展开查看中文执行步骤与预期结果。"));
      const total=data.cases.length,active=data.cases.filter(row=>row.state==="active").length;
      const tally=["assistant","functional","browser"].map(type=>`${TYPE_LABEL[type]} ${data.cases.filter(row=>TYPE_OF(row)===type&&row.state==="active").length} 已接入`).join(" · ");
      root.append(el("p","qa-muted",`已接入 ${active} / 共 ${total} 条：${tally}。候选（未接入）用例不能运行。`));
      const toolbar=el("div","qa-case-filters");
      const stateSelect=el("select");stateSelect.setAttribute("aria-label","用例状态");
      for(const [value,text] of [["active","已接入"],["candidate","候选未接入"],["all","全部状态"]]){const node=el("option","",text);node.value=value;stateSelect.append(node);}stateSelect.value=caseState;stateSelect.onchange=()=>{caseState=stateSelect.value;paint();};
      for(const [value,text] of [["all","全部类型"],["assistant","Agent 测试用例"],["functional","接口测试用例"],["browser","UI 测试用例"]]){const node=button(text,()=>{caseType=value;paint();});node.classList.toggle("is-active",caseType===value);node.setAttribute("aria-pressed",String(caseType===value));toolbar.append(node);}
      root.append(toolbar);
      const search=el("div","qa-search");
      const input=el("input");input.type="search";input.placeholder="按 id 或标题搜索，例如 A02 / 库存";input.value=caseQuery;input.setAttribute("aria-label","搜索用例");
      const box=el("div","qa-case-library");
      const rows=()=>data.cases.filter(row=>(caseState==="all"||row.state===caseState)&&(caseType==="all"||TYPE_OF(row)===caseType)&&(!caseQuery.trim()||row.id.toLowerCase().includes(caseQuery.trim().toLowerCase())||String(row.title).toLowerCase().includes(caseQuery.trim().toLowerCase())));
      const paintList=()=>{box.replaceChildren();const shown=rows();for(const row of shown)box.append(caseItem(row));if(!shown.length)box.append(el("p","qa-muted","没有匹配当前筛选与搜索的用例。"));};
      input.oninput=()=>{caseQuery=input.value;paintList();};
      const selectedRows=()=>data.cases.filter(row=>checked.has(row.id));
      const runnable=rows=>rows.filter(canRunRow);
      const chosen=()=>runnable(selectedRows());
      const runSelected=button("运行选中用例",()=>runCases(selectedRows()),true);
      const runAll=button("一键运行全部已接入",()=>confirmRunAll());
      const allRunnable=runnable(data.cases);
      runAll.disabled=!allRunnable.length;runAll.title=allRunnable.length?"本次点击即批准并启动":runBlock(data.cases.find(row=>row.state==="active"))||"没有可运行的已接入用例";
      runSelected.disabled=!chosen().length;runSelected.title=chosen().length?"本次点击即批准并启动；批准与启动在同一次点击内完成":(selectedRows().length?`选中的用例都不能运行：${runBlock(selectedRows()[0])}`:"先勾选已接入用例");
      search.append(input,stateSelect);
      const execution=el("div","qa-case-execution");execution.append(actions(runSelected,runAll,button("清空选择",()=>{checked.clear();paint();})));
      const creation=el("div","qa-actions");
      if(RUN_ENVIRONMENT!=="real-nanzhi"&&can('qa.assistant.run'))creation.append(button('新增 Agent 用例',()=>caseDialog()));
      if(RUN_ENVIRONMENT!=="real-nanzhi"&&can('qa.functional.run'))creation.append(button('新增接口用例',()=>functionalCaseDialog()));
      execution.append(creation);root.append(search,execution);
      const advanced=el("details","qa-execution-note");advanced.append(el("summary","","执行环境与预算说明"),el("p","qa-muted",`同类型每批最多 ${BATCH_LIMIT} 条，共享预算；超出时分批。Agent 使用 live，接口与 UI 使用固定断言；环境 ${RUN_ENVIRONMENT}。预算 ${RUN_BUDGET.max_calls} 次调用 / ${RUN_BUDGET.max_tokens} tokens / ${RUN_BUDGET.timeout_seconds}s，耗尽明确阻塞。`));root.append(advanced);
      if(receipts.length||failures.length)renderReceipts();
      paintList();
      root.append(box);
    }
    function caseItem(row){
      const item=el("section","qa-case-item"),head=el("div","qa-case-row");
      const pick=el("input");pick.type="checkbox";pick.value=row.id;pick.checked=checked.has(row.id);pick.disabled=!canRunRow(row);pick.setAttribute("aria-label",`选择用例 ${row.id}`);
      if(pick.disabled)pick.title=runBlock(row);
      pick.onchange=()=>{if(pick.checked)checked.add(row.id);else checked.delete(row.id);paint();};
      head.append(pick,el("strong","",`${row.id} ${row.title}`),el("span","qa-muted",`${TYPE_LABEL[TYPE_OF(row)]} · v${row.version} · ${ADAPTER_LABEL[row.adapter]||row.adapter}`),badge(row.state),el("span",row.doc?.risk==="writes"?"qa-error":"qa-muted",row.doc?.risk==="writes"?"会写入":"只读"));
      const run=button("运行此用例",()=>runCases([row]));const block=runBlock(row);run.disabled=!!block;if(block)run.title=block;head.append(run);
      if(['declarative_assistant','declarative_functional'].includes(row.adapter)){if(can(`qa.${row.kind}.run`))head.append(button(row.state==='candidate'?'编辑候选':'新建版本',()=>row.kind==='functional'?functionalCaseDialog(row):caseDialog(row)));if(can('qa.approve')&&row.state==='candidate')head.append(button('审核启用',()=>action(()=>api(`/cases/${row.id}/approve`,{digest:row.revision_digest}))));if(can('qa.approve')&&row.state==='active')head.append(button('撤销启用',()=>action(()=>api(`/cases/${row.id}/revoke`,{}))));}
      item.append(head);
      const docs=el("details","qa-case-docs");docs.open=expanded.has(row.id);docs.addEventListener("toggle",()=>{if(docs.open)expanded.add(row.id);else expanded.delete(row.id);});
      docs.append(el("summary","","执行步骤 / 预期结果 / 代码入口 / 风险"));
      const doc=row.doc||{},body=el("div","qa-case-docs-body"),codeLine=el("p");codeLine.append(mono(`${doc.code_file||"—"} :: ${doc.code_node||"—"}`));
      body.append(el("h4","","执行步骤"),steps(doc.steps||[]),el("h4","","预期结果"),list(doc.expected||[]),el("h4","","对应代码文件与入口"),codeLine,el("h4","","风险标记"),el("p",doc.risk==="writes"?"qa-error":"qa-pass",doc.risk==="writes"?"会写入（writes）：该用例会创建或修改测试记录，执行后必须确认归档或清理成功。":"只读（read-only）：只读取业务数据并断言结果。"),el("h4","","适配器与支持模式"),el("p","",`${ADAPTER_LABEL[row.adapter]||row.adapter}；适配器 ${row.adapter}；支持模式 ${(row.modes||[]).map(label).join("、")||"—"}；v${row.version}；状态 ${label(row.state)}${row.state==="active"?"":"（不能运行）"}`));
      if(row.environments)body.append(el("p","qa-muted",`支持环境：${row.environments.join("、")}`));
      if(row.definition){const raw=el("details","qa-step");raw.append(el("summary","","自定义用例定义（只读）"),pre(row.definition));body.append(raw);}
      docs.append(body);item.append(docs);
      return item;
    }
    function confirmRunAll(){
      const rows=data.cases.filter(canRunRow),groups=runGroups(rows);
      const planned=groups.reduce((total,group)=>total+Math.ceil(group.ids.length/batchLimit(group)),0);
      const dialog=el("dialog","qa-dialog"),form=el("div","qa-form");
      form.append(el("h2","","一键运行全部已接入用例"),el("p","qa-muted",`共 ${rows.length} 条用例，本次运行汇总为一份报告。报告左侧选择用例，查看各自的中文步骤、预期、实际结果及截图。`));
      form.append(table(["用例类型","模式","用例数","计划数"],groups.map(group=>[TYPE_LABEL[group.kind]||label(group.kind),label(group.mode),String(group.ids.length),String(Math.ceil(group.ids.length/batchLimit(group)))])));
      form.append(el("p","","点击下方按钮即批准当前范围并启动；每份报告预算 max_calls=50 / max_tokens=60000 / timeout=1200s，环境 "+RUN_ENVIRONMENT+"。"));
      const message=el("p","qa-error");
      form.append(message,actions(button("取消",()=>dialog.close()),button("确认并运行全部",()=>{dialog.close();runCases(rows);},true)));
      dialog.append(form);dialog.addEventListener("close",()=>dialog.remove(),{once:true});root.append(dialog);dialog.showModal();
    }
    async function startRows(rows){
      const started=[],failed=[];
      for(const group of runGroups(rows)){
        for(let index=0;index<group.ids.length;index+=batchLimit(group)){
          const batch=group.ids.slice(index,index+batchLimit(group));
          try{
            const goal=`${TYPE_LABEL[group.kind]||group.kind}用例 ${batch[0]}${batch.length>1?` 等 ${batch.length} 条`:""} · ${label(group.mode)}`;
            let plan=await api("/plans",{goal:goal+"；请包含全部请求用例",kind:group.kind,mode:group.mode,planner:"model",environment_id:RUN_ENVIRONMENT,case_ids:batch,...RUN_BUDGET});
            for(let attempt=0;["planning","planning_running"].includes(plan.status)&&attempt<120;attempt++){
              await new Promise(resolve=>setTimeout(resolve,1000));plan=await api(`/plans/${plan.id}`);
            }
            if(plan.status!=="draft")throw Error("真实模型规划未完成："+(plan.evidence?.error||plan.status));
            const omitted=batch.filter(id=>!plan.payload.case_ids.includes(id));
            if(omitted.length)failed.push({kind:group.kind,mode:group.mode,ids:omitted,error:"模型规划未选入这些用例，未执行、未计通过"});
            await api(`/plans/${plan.id}/approve`,{digest:plan.digest});
            const run=await api("/runs",{plan_id:plan.id,request_key:crypto.randomUUID()});
            started.push({plan:plan.id,run:run.id,kind:group.kind,mode:group.mode,count:plan.payload.case_ids.length,ids:plan.payload.case_ids.slice()});
          }catch(err){failed.push({kind:group.kind,mode:group.mode,ids:batch.slice(),error:err.message});}
        }
      }
      let report=null;
      if(started.length){
        try{report=await api("/report-batches",{run_ids:started.map(item=>item.run),requested_cases:rows.map(item=>item.id),request_key:crypto.randomUUID()});}
        catch(err){failed.push({kind:"joint",ids:rows.map(item=>item.id),error:"执行已启动，但报告汇总失败："+err.message});}
      }
      return {started,failed,report};
    }
    async function runCases(rows){
      if(pending)return;
      const runnable=rows.filter(canRunRow),blocked=rows.filter(row=>!canRunRow(row));
      if(!runnable.length){error(blocked.length?`不能运行：${runBlock(blocked[0])}`:"没有选择可运行的用例。");return;}
      pending=true;
      try{
        const outcome=await startRows(runnable);
        receipts=outcome.report?[{run:outcome.report.id,plan:"批次汇总",kind:outcome.report.kind,mode:outcome.report.mode,count:outcome.report.results.length,ids:outcome.report.results.map(row=>row.id)}]:outcome.started;failures=outcome.failed;
        if(outcome.report)selectedRun=outcome.report.id;else if(receipts.length)selectedRun=receipts[receipts.length-1].run;
        const total=outcome.started.reduce((sum,item)=>sum+item.count,0);
        flash=`已启动 ${total} 条用例，汇总为 ${outcome.report?1:0} 份报告（批准与启动在同一次点击内完成）。${blocked.length?`另有 ${blocked.length} 条不属于已接入用例，已跳过。`:""}${failures.length?`${failures.length} 批未启动：${failures[0].error}`:""}`;
        await refresh();
      }catch(err){error(err.message);}finally{pending=false;}
    }
    function compose(kind){
      const dialog=el("dialog","qa-dialog");const form=el("form","qa-form");form.append(el("h2","",`新建${label(kind)}`));
      const goal=el("textarea");goal.name="goal";goal.required=true;goal.maxLength=2000;goal.value=kind==="functional"?"验证商品与订单的关键业务约束":kind==="assistant"?"验证业务助手商品查询、预算推荐与越权保护":"分别验证业务助手与业务功能；保持用例数据隔离";form.append(el("label","","测试目标"),goal);
      const mode=el("select"),planner=el("select");
      for(const value of kind==="functional"?["rules"]:data.capabilities.platform_diagnostics?["rules","live"]:["live"]){const option=el("option","",value==="rules"&&kind!=="functional"?"平台确定性诊断（不算Agent真实评测）":label(value));option.value=value;mode.append(option);}
      for(const [value,text]of RUN_ENVIRONMENT==="real-nanzhi"?[["fixed","南枝实店固定步骤与数据库断言"]]:data.capabilities.platform_diagnostics?[["fixed","平台诊断：固定计划（不调用规划模型）"],["model","真实模型工具规划"]]:[["model","真实模型工具规划"]]){const option=el("option","",text);option.value=value;planner.append(option);}
      mode.value=kind==="functional"?"rules":"live";planner.value=RUN_ENVIRONMENT==="real-nanzhi"?"fixed":"model";
      form.append(el("label","","执行模式"),mode,el("label","","规划方式"),planner,el("p","qa-muted","只运行勾选且已接入的用例；AI仅能在此集合内选择。每条用例独立数据。"));
      const environment=el("select");
      for(const row of data.capabilities.environments){const option=el("option","",row.name);option.value=row.id;environment.append(option);}
      form.append(el("label","","执行环境"),environment);
      const choices=el("div","qa-choices");const counters={assistant:0,functional:0};
      for(const row of data.cases.filter(entry=>entry.state==="active"&&(kind==="joint"||entry.kind===kind))){const wrap=el("label");const check=el("input");check.type="checkbox";check.value=row.id;check.checked=counters[row.kind]++<(RUN_ENVIRONMENT==="real-nanzhi"&&row.kind==="assistant"?1:2);wrap.append(check,document.createTextNode(`${row.id} ${row.title}`));choices.append(wrap);}form.append(choices);
      const updateModes=()=>{for(const check of choices.querySelectorAll('input')){const row=data.cases.find(item=>item.id===check.value);check.disabled=row.kind==='assistant'&&!row.modes.includes(mode.value);if(check.disabled)check.checked=false;check.parentElement.title=check.disabled?'此用例需要真实模型模式':'';}};
      mode.onchange=updateModes;updateModes();
      const budget=el("input");budget.type="number";budget.min="2000";budget.max="60000";budget.value="60000";form.append(el("label","","共享模型Token预算（含规划、重试与被测助手）"),budget);
      const consent=el("label","qa-consent"),check=el("input");check.type="checkbox";check.required=true;consent.append(check,document.createTextNode("确认在已登记环境运行；线上实店只修改本轮测试记录，Agent调用会消耗模型额度"));form.append(consent);
      const message=el("p","qa-error");const submit=el("button","qa-primary","生成待审批计划");submit.type="submit";
      const labels=Array.from(form.querySelectorAll('label')).filter(node=>!node.querySelector('input'));
      Array.from(form.querySelectorAll('textarea,select,input[type=number]')).forEach((field,index)=>{field.id='qa-field-'+crypto.randomUUID();labels[index].htmlFor=field.id;});
      const actionsRow=el("div","qa-actions");actionsRow.append(button("取消",()=>dialog.close()),submit);form.append(message,actionsRow);
      form.onsubmit=async event=>{event.preventDefault();submit.disabled=true;try{const ids=Array.from(choices.querySelectorAll("input:checked")).map(node=>node.value);const plan=await api("/plans",{goal:goal.value,kind,mode:mode.value,planner:planner.value,diagnostic:planner.value==="fixed"||kind!=="functional"&&mode.value==="rules",environment_id:environment.value,case_ids:ids,max_tokens:Number(budget.value)});selectedPlan=plan.id;dialog.close();await refresh();}catch(err){message.textContent=err.message;}finally{submit.disabled=false;}};
      dialog.append(form);dialog.addEventListener("close",()=>dialog.remove(),{once:true});root.append(dialog);dialog.showModal();
    }
    root.append(el("p","qa-muted","正在读取OP测试能力…"));refresh();
  }
  return {mount};
})();
