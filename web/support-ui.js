/* Human support is separate from the AI assistant. No catalog-page redraws. */
(() => {
  const merchant = document.body.classList.contains('merchant-store');
  const key = merchant ? 'token_b' : 'token_c';
  const el = (tag, cls, text) => { const n = document.createElement(tag); n.className = cls || ''; if (text != null) n.textContent = text; return n; };
  const labels = {requested:'待商家处理',accepted:'已受理',rejected:'已拒绝',resolved:'处理完成',withdrawn:'已撤销',return_shipped:'买家已寄回',shipped:'已发货',transit:'运输中',delivered:'已签收',exception:'物流异常'};
  const kinds = {return:'退货',exchange:'换货',repair:'维修',other:'其他问题'};
  const time = value => new Date(value).toLocaleString('zh-CN', {hour12:false});
  const trigger = el('button', merchant ? 'support-top' : 'support-header-launch', merchant ? '客户消息 / 售后' : '联系商家'); trigger.type = 'button';
  trigger.setAttribute('aria-label',merchant?'客户消息与售后':'联系商家');
  if (!merchant) {
    const icon=document.createElementNS('http://www.w3.org/2000/svg','svg');
    icon.setAttribute('viewBox','0 0 24 24');icon.setAttribute('aria-hidden','true');
    const path=document.createElementNS('http://www.w3.org/2000/svg','path');
    path.setAttribute('d','M21 11.5a8.4 8.4 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7a8.4 8.4 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.4 8.4 0 0 1 3.8-.9h.5a8.5 8.5 0 0 1 8 8v.5Z');
    icon.append(path);trigger.prepend(icon);
  }

  function placeTrigger() {
    // 商家端放到顶栏右侧（挨着“查看买家端”），不再用右下角悬浮入口。
    if(merchant) {
      const bar=document.querySelector('header.admin-top .user') || document.querySelector('header.admin-top');
      if(bar&&trigger.parentElement!==bar) bar.prepend(trigger);
      else if(!trigger.isConnected) document.body.append(trigger);
      return;
    }
    const target=document.querySelector('.store-nav');
    trigger.hidden=!target;
    if(target&&trigger.parentElement!==target)target.append(trigger);
  }
  placeTrigger();
  // 商家页重绘顶栏后入口会被移除，这里按需重新挂回（只检查是否还在文档里，开销可忽略）。
  if (merchant) new MutationObserver(() => { if (!trigger.isConnected) placeTrigger(); }).observe(document.body, {childList: true, subtree: true});
  let panel, main, nav, notice, tab = 'chat', token, controller, timer, conversation, cursor = 0, firstId = 0;
  let orders = [], conversations = [], code, polling = false, pendingSend = null, orderContext = '';
  function close() { clearInterval(timer); controller?.abort(); panel?.remove(); panel = null; conversation = null; cursor = 0; firstId = 0; trigger.setAttribute('aria-expanded', 'false'); }
  async function call(path, options = {}) {
    const requestToken=sessionStorage.getItem(key), requestPanel=panel;
    const result = await createApi(key)('/api/v1/support' + path, {...options, signal:controller.signal});
    if (sessionStorage.getItem(key) !== requestToken || requestPanel!==panel || !panel || requestToken!==token) throw new DOMException('账号已切换','AbortError');
    return result;
  }
  const json = (method, body) => ({method, body:JSON.stringify(body)});
  function error(err) { if (panel && err.name !== 'AbortError') notice.textContent = err.message; }
  function action(label, fn, cls='') { const b = el('button', cls, label); b.type='button'; b.addEventListener('click', async () => { b.disabled=true; notice.textContent=''; try { await fn(); } catch(e) {error(e);} finally {b.disabled=false;} }); return b; }
  function input(form, label, name, multiline=false, max=500) {
    const wrap=el('label','support-field',label), field=el(multiline?'textarea':'input'); field.name=name; field.maxLength=max; field.required=true; wrap.append(field); form.append(wrap); return field;
  }
  function selectOrder(form, selected='', chatOnly=false) {
    const label=el('label','support-field','关联订单'), select=el('select'); select.name='order_no';
    select.append(new Option('请选择订单', ''));
    orders.filter(order=>!chatOnly||!merchant||order.buyer_username===conversation?.customer_username).forEach(order => select.append(new Option(`${order.order_no} · ${order.status_label} · ¥${order.total_yuan}`, order.order_no)));
    select.value=selected; label.append(select); form.append(label); return select;
  }
  async function loadOrders() {
    const requestToken=sessionStorage.getItem(key), requestPanel=panel;
    const result = await createApi(key)(merchant ? '/api/v1/b/orders' : `/api/v1/c/orders?share_code=${encodeURIComponent(code)}`, {signal:controller.signal});
    if (sessionStorage.getItem(key)!==requestToken||requestPanel!==panel||!panel) throw new DOMException('账号已切换','AbortError');
    orders=result;
  }
  function events(container, rows) {
    const list=el('ol','support-timeline');
    [...rows].reverse().forEach(row => { const li=el('li'); li.append(el('small','', `${row.role==='merchant'?'商家':'买家'} · ${time(row.at)}`),el('p','',row.text)); list.append(li); }); container.append(list);
  }
  async function open(options={}) {
    const requestedTab=['chat','shipping','tickets'].includes(options.tab)?options.tab:'chat';
    const requestedOrder=/^PS\d{8,32}$/.test(options.orderNo||'')?options.orderNo:'';
    if (!sessionStorage.getItem(key)) {
      if (merchant) { location.href='/login'; return; }
      StoreAuth.openDialog({role:'customer',onSuccess:()=>open(options)}); return;
    }
    close(); tab=requestedTab;orderContext=requestedOrder;token=sessionStorage.getItem(key); controller=new AbortController();
    panel=el('section','support-panel'); panel.setAttribute('role','dialog'); panel.setAttribute('aria-label',merchant?'客户服务':'联系商家');
    const head=el('header','support-head'); head.append(el('div','', merchant?'客户服务':'店铺人工服务'),action('×',close,'support-close'));
    nav=el('nav','support-tabs');
    [['chat',merchant?'客户消息':'与商家聊天'],['shipping','订单物流'],['tickets','售后服务']].forEach(([value,label]) => nav.append(action(label, async()=>{tab=value; await paint();})));
    [...nav.children].forEach(button=>button.disabled=true);
    main=el('div','support-main'); notice=el('p','support-notice'); notice.setAttribute('role','status');
    panel.append(head,nav,notice,main); document.body.append(panel); trigger.setAttribute('aria-expanded','true');
    head.querySelector('button').setAttribute('aria-label','关闭客户服务');
    const openedPanel=panel;
    try {
      code=merchant ? (await createApi(key)('/api/v1/b/shop',{signal:controller.signal})).share_code : document.querySelector('.store-nav')?.dataset.shopCode||new URLSearchParams(location.search).get('code')||'nanzhi';
      if(panel!==openedPanel)return;
      await loadOrders();
      if(orderContext&&!orders.some(order=>order.order_no===orderContext))throw Error('未找到当前账号在本店的这个订单，请从订单中心重新选择');
      [...nav.children].forEach(button=>button.disabled=false);
      await paint();
      timer=setInterval(async()=>{
        if (!panel || document.hidden || polling) return;
        if (sessionStorage.getItem(key)!==token) {close(); return;}
        polling=true;
        try { if(tab==='chat') { if(merchant) await inbox(); if(conversation) await poll(); } } catch(e){error(e);} finally{polling=false;}
      },3000);
    } catch(e){error(e); if(panel)[...nav.children].forEach(button=>button.disabled=false);}
  }
  async function paint() {
    if(!panel) return;
    notice.textContent=''; main.replaceChildren();
    [...nav.children].forEach((n,i)=>n.classList.toggle('active',i===['chat','shipping','tickets'].indexOf(tab)));
    if(tab==='chat') await chat();
    else if(tab==='shipping') await shipping();
    else await tickets();
  }
  async function inbox() {
    conversations=await call('/conversations');
    const list=main.querySelector('.support-inbox'); if(!list||tab!=='chat') return;
    const signature=JSON.stringify([conversation?.id,conversations]);
    if(list.dataset.signature===signature)return;
    list.dataset.signature=signature;list.replaceChildren();
    if(!conversations.length) list.append(el('p','support-empty','还没有买家消息'));
    conversations.forEach(item=>{ const b=action(`${item.name}${item.unread?` · ${item.unread}条未读`:''}`,async()=>{conversation=item;cursor=0;firstId=0;pendingSend=null;await chat();}, item.id===conversation?.id?'selected':''); b.append(el('small','',item.last_message||'暂无消息')); list.append(b); });
  }
  async function chat() {
    if(!conversation&&(!merchant||orderContext)) conversation=await call(orderContext?`/orders/${encodeURIComponent(orderContext)}/conversation`:`/shops/${encodeURIComponent(code)}/conversation`,{method:'POST'});
    if(tab!=='chat'||!panel)return;
    cursor=0;firstId=0;main.replaceChildren();
    const layout=el('div','support-chat-layout');
    if(merchant) layout.append(el('aside','support-inbox'));
    const right=el('div','support-chat-content'); layout.append(right); main.append(layout);
    if(merchant) await inbox();
    if(tab!=='chat')return;
    if(!conversation) {right.append(el('p','support-empty','选择一位买家开始沟通'));return;}
    right.append(el('h3','',merchant?`与${conversation.name}沟通`:'给商家留言，回复会保存在这里'));
    right.append(action('加载更早消息',async()=>{
      if(!firstId)return; const rows=await call(`/conversations/${conversation.id}/messages?before=${firstId}`);
      if(!rows.length){notice.textContent='已经是最早的消息';return;}
      const fragment=document.createDocumentFragment();rows.forEach(row=>fragment.append(message(row)));log.prepend(fragment);firstId=rows[0].id;
    },'support-history'));
    const log=el('div','support-log'); log.setAttribute('role','log'); log.setAttribute('aria-live','polite'); right.append(log);
    const form=el('form','support-send');
    const order=selectOrder(form,orderContext,true); order.required=false;
    const text=input(form,'消息','content',true,2000); text.placeholder='输入想对商家说的话…';
    const send=el('button','support-primary','发送');send.type='submit';form.append(send);right.append(form);
    form.addEventListener('submit',async event=>{
      event.preventDefault(); if(send.disabled||!text.value.trim())return;
      const content=text.value.trim();
      if(!pendingSend||pendingSend.content!==content||pendingSend.order_no!==order.value)pendingSend={content,order_no:order.value,client_id:crypto.randomUUID()};
      send.disabled=true;notice.textContent='';
      try {await call(`/conversations/${conversation.id}/messages`,json('POST',pendingSend));text.value='';pendingSend=null;await poll();}
      catch(e){error(e);}finally{send.disabled=false;}
    });
    await poll();
  }
  function message(row) {
    const n=el('article',`support-message ${row.sender_role===(merchant?'merchant':'customer')?'mine':''}`); n.dataset.messageId=row.id;
    n.append(el('small','',`${row.sender_role==='merchant'?'商家':'买家'} · ${time(row.created_at)}`));
    if(row.order_no)n.append(el('span','support-order-ref',`订单 ${row.order_no}`));
    n.append(el('p','',row.content));return n;
  }
  async function poll() {
    const id=conversation?.id; const log=main.querySelector('.support-log');if(!id||!log)return;
    const rows=await call(`/conversations/${id}/messages?after=${cursor}`);
    if(conversation?.id!==id||!log.isConnected)return;
    const nearBottom=log.scrollHeight-log.scrollTop-log.clientHeight<80;
    rows.forEach(row=>{if(!log.querySelector(`[data-message-id="${row.id}"]`))log.append(message(row));cursor=Math.max(cursor,row.id);if(!firstId)firstId=row.id;});
    if(nearBottom||rows.length&&cursor===rows.length)log.scrollTop=log.scrollHeight;
    if(cursor&&!document.hidden)await call(`/conversations/${id}/read`,json('POST',{message_id:cursor}));
  }
  async function shipping() {
    await loadOrders();if(tab!=='shipping'||!panel)return;
    const form=el('form','support-stack');form.addEventListener('submit',e=>e.preventDefault());const select=selectOrder(form,orderContext);select.required=true;main.append(form);
    const detail=el('div','support-shipment'); main.append(detail);
    const show=async()=>{
      detail.replaceChildren();if(!select.value)return;
      const number=select.value,row=await call(`/orders/${number}/shipment`);
      if(select.value!==number||tab!=='shipping'||!panel)return;
      detail.append(el('h3','',row?`${row.carrier} · ${row.tracking_number}`:'暂未填写物流'));
      if(row){detail.append(el('p','support-muted',`${labels[row.status]} · 以下记录由商家更新`));events(detail,row.events);}
      if(merchant&&orders.some(o=>o.order_no===number&&['paid','shipped'].includes(o.status))) {
        const edit=el('form','support-stack');input(edit,'快递公司','carrier',false,40).value=row?.carrier||'';
        input(edit,'运单号','tracking_number',false,64).value=row?.tracking_number||'';
        const save=el('button','support-primary',row?'保存运单':'填写运单并发货');save.type='submit';edit.append(save);
        edit.addEventListener('submit',async e=>{e.preventDefault();save.disabled=true;try{await call(`/orders/${number}/shipment`,json('PUT',Object.fromEntries(new FormData(edit))));await show();}catch(err){error(err);}finally{save.disabled=false;}});detail.append(edit);
        if(row&&row.status!=='delivered'){
          const update=el('form','support-stack'), state=el('select');state.name='status';state.setAttribute('aria-label','物流状态');['transit','delivered','exception'].forEach(s=>state.append(new Option(labels[s],s)));update.append(state);
          input(update,'物流进展（商家更新）','description',true,300);const add=el('button','','更新物流进展');add.type='submit';update.append(add);
          update.addEventListener('submit',async e=>{e.preventDefault();add.disabled=true;try{await call(`/orders/${number}/shipment/events`,json('POST',Object.fromEntries(new FormData(update))));await show();}catch(err){error(err);}finally{add.disabled=false;}});detail.append(update);
        }
      }
    };
    select.addEventListener('change',()=>show().catch(error));
    if(orders.length){if(!select.value)select.value=orders[0].order_no;await show();}else main.append(el('p','support-empty','暂无订单'));
  }
  async function tickets() {
    await loadOrders();if(tab!=='tickets'||!panel)return;
    if(!merchant){
      const form=el('form','support-stack');form.append(el('h3','','申请售后'));const order=selectOrder(form,orderContext);order.required=true;
      const kind=el('select');kind.name='kind';kind.setAttribute('aria-label','售后类型');Object.entries(kinds).forEach(([k,v])=>kind.append(new Option(v,k)));form.append(kind);
      input(form,'问题说明','reason',true,500);const submit=el('button','support-primary','提交申请');submit.type='submit';form.append(submit);
      form.addEventListener('submit',async e=>{e.preventDefault();submit.disabled=true;try{await call(`/orders/${order.value}/after-sale`,json('POST',Object.fromEntries(new FormData(form))));await paint();}catch(err){error(err);}finally{submit.disabled=false;}});main.append(form);
    }
    const rows=await call('/after-sales');if(tab!=='tickets'||!panel)return;if(!rows.length)main.append(el('p','support-empty','暂无售后申请'));
    rows.forEach(row=>{
      const card=el('article','support-ticket');card.append(el('h3','',`${kinds[row.kind]} · ${labels[row.status]}`),el('small','',row.order_no),el('p','',row.reason));
      card.append(action('就此订单沟通',async()=>{conversation=await call(`/orders/${row.order_no}/conversation`,{method:'POST'});orderContext=row.order_no;tab='chat';await paint();}));
      if(row.return_tracking)card.append(el('p','',`退回运单：${row.return_carrier} ${row.return_tracking}`));
      events(card,row.events);
      const form=el('form','support-stack');form.addEventListener('submit',e=>e.preventDefault());input(form,'沟通 / 处理说明','note',true,500);
      const buttons=el('div','support-actions');
      const process=actionName=>async()=>{
        const note=form.elements.note.value.trim();if(note.length<2)throw Error('请填写至少2字处理说明');
        const body={action:actionName,note};if(actionName==='return_ship')Object.assign(body,{carrier:form.elements.carrier.value,tracking_number:form.elements.tracking_number.value});
        await call(`/after-sales/${row.id}/process`,json('POST',body));await paint();
      };
      if(merchant&&row.status==='requested')buttons.append(action('受理',process('accept'),'support-primary'),action('拒绝并说明',process('reject')));
      if(merchant&&['accepted','return_shipped'].includes(row.status))buttons.append(action('记录处理完成',process('resolve'),'support-primary'));
      if(!merchant&&row.status==='requested')buttons.append(action('撤销申请',process('withdraw')));
      if(!merchant&&row.status==='accepted'&&['return','exchange'].includes(row.kind)){
        input(form,'退回快递公司','carrier',false,40);input(form,'退回运单号','tracking_number',false,64);buttons.append(action('提交退回运单',process('return_ship'),'support-primary'));
      }
      if(buttons.children.length){form.append(buttons);card.append(form);} main.append(card);
    });
    main.append(el('p','support-muted','处理记录不代表退款到账；资金退款暂未接入。'));
  }
  document.addEventListener('store-support-open',event=>open(event.detail||{}));
  trigger.addEventListener('click',()=>panel?close():open());trigger.setAttribute('aria-expanded','false');
  document.addEventListener('keydown',e=>{if(e.key==='Escape'&&panel){close();trigger.focus();}});
  new MutationObserver(()=>{
    placeTrigger();
    if(merchant)trigger.hidden=!sessionStorage.getItem(key);
    if(panel&&(sessionStorage.getItem(key)!==token||(!merchant&&document.querySelector('.store-nav')?.dataset.shopCode!==code)))close();
  }).observe(document.getElementById('app'),{childList:true});
  placeTrigger();
  if(merchant)trigger.hidden=!sessionStorage.getItem(key);
  setInterval(async()=>{
    const current=sessionStorage.getItem(key); if(!current||panel||document.hidden)return;
    try {
      const rows=await createApi(key)('/api/v1/support/conversations');
      if(current!==sessionStorage.getItem(key)||panel)return;
      const unread=rows.reduce((sum,row)=>sum+row.unread,0);
      trigger.textContent=(merchant?'客户消息 / 售后':'联系商家')+(unread?` · ${unread}条未读`:'');
    } catch { /* The next poll retries; authorization handling belongs to createApi. */ }
  },15000);
})();
