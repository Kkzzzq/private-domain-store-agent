window.OPBusinessObservatory = (() => {
  let owner, state;
  function mount(host, options){
    const identity=sessionStorage.getItem("token_op");
    if(owner!==identity){owner=identity;state={records:[],messages:[],role:"customer",draft:"",busy:false,apiReady:false};}
    const root=document.createElement("section");root.className="ao-workspace";host.append(root);
    const valid=()=>root.isConnected&&options.alive()&&sessionStorage.getItem("token_op")===identity;
    const el=(tag,cls,text)=>{const node=document.createElement(tag);if(cls)node.className=cls;if(text!=null)node.textContent=String(text);return node;};
    const button=(text,click,disabled=false)=>{const node=el("button","",text);node.type="button";node.onclick=click;node.disabled=disabled;return node;};
    const json=value=>el("pre","ao-json",JSON.stringify(value??null,null,2).slice(0,100000));
    const api=async(path,body)=>{if(!valid())throw Error("页面或账号已变化");return options.api(path,body);};
    const failure=error=>[404,405].includes(error.status)?"后端尚未加载业务对话接口，需要正常重启8000后端后再刷新。当前未调用模型。":error.message;
    function answer(text){const content=window.AssistantPresentation.clean(text),node=el("div","ao-answer");let offset=0;for(const match of content.matchAll(/\*\*([^*\n]+)\*\*|`([^`\n]+)`/g)){node.append(document.createTextNode(content.slice(offset,match.index)),el(match[1]?"strong":"code","",match[1]||match[2]));offset=match.index+match[0].length;}node.append(document.createTextNode(content.slice(offset)));return node;}
    function draw(){
      if(!valid())return;root.replaceChildren();
      const top=el("div","ao-summary");top.append(el("h3","","业务对话工作台"),button("刷新对话记录",load,state.busy));root.append(top);
      root.append(el("p","ao-muted","独立合成店铺 · 真实模型对话（最多5轮）。每次发送都在新副本里重放上下文，不操作实际店铺，本页不做答案评分。"));
      const help=el("details","ao-details");help.append(el("summary","","怎么用、轨迹和用量怎么看？"),el("p","ao-muted","怎么用：与购物或经营助手对话，展开轨迹可查看它实际调用了哪些接口和工具；点击某一步，右侧显示该步的输入与结果。合成买家只能购物与查本人订单，合成商家可查本店经营；这里的商品是测试副本，不等于 C 端当前真实商品。"),el("p","ao-muted","轨迹与用量：POST /api/v1/auth/login 是测试身份登录，chat 是发送业务问题；HTTP 不是商品操作次数。JSON 是脱敏后的请求/响应原始记录，不是客服回复。模型调用次数表示真实模型请求，tokens 表示模型用量；副本清理完成只表示临时环境已释放。将问题转评测候选只是创建待审核用例，不会自动运行或判为通过。"));root.append(help);
      if(state.error)root.append(el("p","qa-error",state.error));
      const grid=el("div","ao-grid"),left=el("section","ao-column"),middle=el("section","ao-column"),right=el("section","ao-column");
      const role=el("select");role.setAttribute("aria-label","对话身份");for(const [value,name]of [["customer","合成买家"],["merchant","合成商家"]]){const node=el("option","",name);node.value=value;role.append(node);}role.value=state.role;role.disabled=state.busy||state.messages.length>0;role.onchange=()=>state.role=role.value;
      left.append(el("h4","","对话"),role);
      const record=state.records.find(row=>row.id===state.selected)||state.records[0];
      const chats=(record?.evidence?.requests||[]).filter(row=>String(row.path||"").endsWith("/chat"));
      // 数据来源在页面上写明：本页跑的是独立合成副本，不是线上真实店铺库。
      const environment=record?.evidence?.environment||{};
      if(record)left.append(el("p","ao-datasource",`数据来源：独立合成副本（环境 ${environment.id||"isolated-local"} · fixture ${environment.fixture_version||"seed-isolated-v1"}）· 不是线上南枝真实库`));
      const assistantName=state.role==="merchant"?"运营小助手":"购物小助手";
      for(const chat of chats){
        const turn=el("div","ao-chat-turn");
        const ask=el("div","ao-bubble ao-bubble-user");
        ask.append(el("span","ao-speaker",state.role==="merchant"?"我（合成商家）":"我（合成买家）"),el("p","ao-bubble-text",chat.input?.message||"问题未采集"));
        const reply=el("div","ao-bubble ao-bubble-agent");
        reply.append(el("span","ao-speaker",assistantName),answer(chat.output?.answer||"回答未采集"));
        turn.append(ask,reply);left.append(turn);
      }
      if(state.busy){const pending=el("div","ao-bubble ao-bubble-agent ao-bubble-pending");pending.append(el("span","ao-speaker",assistantName),el("p","ao-bubble-text","正在真实调用模型并复现对话，请稍候…"));left.append(pending);}
      const input=el("textarea");input.rows=3;input.maxLength=1000;input.value=state.draft;input.placeholder="例如：预算100元，推荐吃饭用的东西";input.setAttribute("aria-label","业务问题");input.disabled=state.busy;input.oninput=()=>state.draft=input.value;
      const send=button("发送到合成助手",async()=>{
        if(state.busy)return;const message=state.draft.trim();if(message.length<2){state.error="请输入至少两个字的问题";draw();return;}
        if(state.messages.length>=5){state.error="本段对话已达5轮，请开始新对话";draw();return;}
        state.busy=true;state.error="";draw();
        try{
          const messages=[...state.messages,message];
          const result=await api("/business-debug",{role:state.role,messages,confirmed:true});
          if(!valid())return;
          state.records=[result,...state.records.filter(row=>row.id!==result.id)].slice(0,10);state.selected=result.id;state.nodeId=null;
          if(result.status==="completed"){state.messages=messages;state.draft="";}else state.error=result.evidence?.error||"本次对话未完成，没有用规则答案补齐";
        }catch(error){if(valid()){state.error=failure(error);if([404,405].includes(error.status))state.apiReady=false;}}
        finally{state.busy=false;if(valid())draw();}
      },state.busy||!state.apiReady||!options.capabilities.includes("qa.assistant.run"));
      input.placeholder="输入业务问题，Enter发送，Shift+Enter换行";
      input.onkeydown=event=>{if(event.key==="Enter"&&!event.shiftKey&&!event.isComposing&&event.keyCode!==229){event.preventDefault();if(!send.disabled)send.click();}};
      left.append(input,send,el("p","ao-muted","Enter发送 · Shift+Enter换行"));
      left.append(button("开始新对话",()=>{state.messages=[];state.draft="";state.selected=null;state.records=[];state.nodeId=null;state.error="";draw();},state.busy));
      if(state.records.length){
        const history=el("select");history.setAttribute("aria-label","对话记录");for(const row of state.records){const node=el("option","",`${row.created_at.slice(0,16).replace("T"," ")} · ${row.role==="merchant"?"商家":"买家"} · ${row.status==="completed"?"已完成":"未完成"}`);node.value=row.id;history.append(node);}history.value=record.id;history.disabled=state.busy;history.onchange=()=>{state.selected=history.value;const saved=state.records.find(row=>row.id===history.value);state.messages=saved.status==="completed"?saved.messages.slice():[];state.role=saved.role;state.nodeId=null;draw();};left.append(el("h4","","对话记录（7天内）"),history);
      }
      middle.append(el("h4","","执行轨迹"));right.append(el("h4","","业务证据"));
      const projected=window.OPAgentObservatory.buildTimeline({evidence:record?.evidence},"business");
      const selected=projected.nodes.find(node=>node.id===state.nodeId)||projected.nodes.find(node=>node.type==="input")||projected.nodes[0];state.nodeId=selected?.id;
      for(const node of projected.nodes){const step=button(node.title,()=>{state.nodeId=node.id;draw();});step.className="ao-node";step.setAttribute("aria-pressed",String(node.id===state.nodeId));if(node.elapsed!=null)step.append(el("small","",node.elapsed+"ms"));middle.append(step);}
      if(selected){if(selected.type==="answer")right.append(answer(selected.detail.answer));const raw=el("details");raw.append(el("summary","","查看这一步的技术原始记录"),json(selected.detail));right.append(raw);}
      if(record){
        right.append(el("p","ao-muted",`模型HTTP调用 ${projected.budget.calls??"未采集"} · tokens ${projected.budget.tokens??"未采集"}${projected.budget.estimated?"（估算）":""} · 副本清理 ${projected.cleanup===true?"完成":"未确认"}`));
        if(projected.models.length){const details=el("details");details.append(el("summary","","实际模型调用"),json(projected.models));right.append(details);}
        const transfer=el("details");transfer.append(el("summary","","将问题交给评测Agent"),el("p","ao-muted","仅转最后一轮问题；多轮上下文请在用例管理补充。主动填写预期并保存才会创建候选，不会自动审批或运行。"));
        const expected=el("input");expected.maxLength=100;expected.placeholder="最后一轮回答应包含的文字";expected.setAttribute("aria-label","转评测预期");
        transfer.append(expected,button("转为评测候选",async()=>{
          const word=expected.value.trim();if(!word){state.error="请先填写最后一轮预期文字";draw();return;}
          try{
            const messages=record.messages||[];
            const candidate=await api("/cases",{title:"业务对话转评测（最后一轮）",role:record.role,turns:[{message:messages[messages.length-1],expected_contains:[word]}]});
            if(valid()){state.error="已创建候选 "+candidate.id+"，请前往测试用例管理审核。";draw();}
          }catch(error){if(valid()){state.error=error.message;draw();}}
        },state.busy||!options.capabilities.includes("qa.assistant.run")));right.append(transfer);
      }else{middle.append(el("p","ao-muted","发送业务问题后显示实际轨迹。"));right.append(el("p","ao-muted","未采集的数据不会补造为执行证据。"));}
      grid.append(left,middle,right);root.append(grid);
    }
    async function load(){try{const rows=await api("/business-debug");if(valid()){if(!Array.isArray(rows))throw Error("后端对话接口返回格式异常");state.apiReady=true;state.records=rows;if(!state.selected&&rows.length){state.selected=rows[0].id;state.messages=rows[0].status==="completed"?rows[0].messages.slice():[];state.role=rows[0].role;}state.error="";draw();}}catch(error){if(valid()){state.apiReady=false;state.error=failure(error);draw();}}}
    draw();load();
  }
  return {mount};
})();
