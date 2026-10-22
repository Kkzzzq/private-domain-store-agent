(() => {
  const managed = ['accounts', 'shops', 'products', 'orders', 'shipments', 'after-sales', 'management-audits', 'coupons'];
  let serial = 0, previous = '', page = 1, search = '', shop = '', shopName = '', days = '7', status = '';
  const e = value => String(value ?? '—').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const money = n => '¥' + (Number(n || 0) / 100).toFixed(2);
  const date = value => value ? new Date(value.endsWith('Z') || /[+]\d\d:\d\d$/.test(value) ? value : value + 'Z').toLocaleString('zh-CN', {hour12:false}) : '—';
  const labels = {pending:'待支付',paid:'待发货',shipped:'已发货',completed:'已完成',cancelled:'已取消',on:'在售',off:'已下架',draft:'草稿',banned:'禁售',open:'营业中',closed:'已停业',unshipped:'未发货',requested:'待受理',approved:'已受理',rejected:'已拒绝',resolved:'已处理',delivered:'已签收',refund:'仅退款',return:'退货退款'};
  Object.assign(labels,{accepted:'已受理',return_shipped:'已寄回',withdrawn:'已撤销',transit:'运输中',exception:'物流异常',exchange:'换货',repair:'维修',other:'其他',active:'可领取',scheduled:'未开始',expired:'已过期',disabled:'已停用',exhausted:'已领完',return:'退货'});
  const badge = value => `<span class="badge ${['banned','closed','cancelled'].includes(value)?'bad':''}">${e(labels[value] || value)}</span>`;
  const titles = {accounts:'平台账号',shops:'全部小店',products:'商品治理',orders:'购买订单',shipments:'物流查询','after-sales':'售后订单','management-audits':'平台管理记录',coupons:'优惠券全生命周期'};
  function dialog(title, body) {
    document.querySelectorAll('.op-detail').forEach(d => d.remove());
    const d = document.createElement('dialog'); d.className = 'op-detail';
    d.innerHTML = `<div class="detail-head"><div><span>PLATFORM MANAGEMENT</span><h2>${e(title)}</h2></div><button class="detail-close" aria-label="关闭">×</button></div><div class="detail-body">${body}</div>`;
    document.body.append(d);d.querySelector('.detail-close').onclick=()=>d.close();d.addEventListener('close',()=>d.remove());d.addEventListener('click',ev=>{if(ev.target===d){const r=d.getBoundingClientRect();if(ev.clientX<r.left||ev.clientX>r.right||ev.clientY<r.top||ev.clientY>r.bottom)d.close();}});d.showModal();return d;
  }
  const pairs = values => `<dl class="detail-grid">${values.map(([label,value])=>`<div><dt>${e(label)}</dt><dd>${value}</dd></div>`).join('')}</dl>`;
  async function orderDetail(id, api, current) {
    const data = await api('/op/platform/orders/' + id);if(!current())return;
    const shipment = data.shipment, sale=data.after_sale;
    const events = list => (list||[]).map(v=>`<li><time>${e(date(v.at||v.created_at||v.time))}</time><span>${e(v.text||v.description||v.content||v.action||'更新记录')}</span></li>`).join('') || '<li class="muted">暂无更新轨迹</li>';
    const detailDialog=dialog('订单 ' + data.order_no, `<div class="detail-summary">${badge(data.status)}<span>${e(data.shop_name)} · ${e(data.buyer.username)}</span><strong>${money(data.total_cents)}</strong></div><h3>购买明细</h3><div class="table-wrap"><table><thead><tr><th>商品</th><th>规格</th><th>单价</th><th>数量</th><th>小计</th></tr></thead><tbody>${data.items.map(i=>`<tr><td>${e(i.name)}</td><td>${e(i.spec)}</td><td>${money(i.price_cents)}</td><td>${i.quantity}</td><td>${money(i.subtotal_cents)}</td></tr>`).join('')}</tbody></table></div>${pairs([['下单时间',e(date(data.created_at))],['买家昵称',e(data.buyer.nickname)],['运费',money(data.freight_cents)],['优惠抵扣',money(data.discount_cents)],['收货人',e(data.receiver)],['联系电话',e(data.phone)],['收货地址',e(data.address)]])}<h3>物流信息</h3>${shipment?`${pairs([['承运公司',e(shipment.carrier)],['物流单号',e(shipment.tracking_number)],['配送状态',badge(shipment.status)]])}<p class="notice">以下轨迹由商家填写，未接入快递公司实时查询。</p><ol class="shipment-timeline">${events(shipment.events)}</ol>`:'<div class="detail-empty">尚未填写物流运单</div>'}<h3>售后信息</h3>${sale?`${pairs([['售后类型',e(sale.kind)],['处理状态',badge(sale.status)],['申请原因',e(sale.reason)],['退货运单',e(sale.return_tracking||'—')]])}<ol class="shipment-timeline">${events(sale.events)}</ol>`:'<div class="detail-empty">暂无售后申请</div>'}`);
    if(data.status==='pending'){
      const cancel=document.createElement('button');cancel.className='primary';cancel.textContent='平台取消待支付订单';cancel.onclick=async()=>{cancel.disabled=true;try{const reason=await window.OPDialogs.prompt('取消待支付订单原因（2—200字）');if(reason===null)return;if(reason.trim().length<2)throw Error('请填写操作原因');await api('/op/governance/orders/'+id+'/cancel',{method:'POST',body:JSON.stringify({action:'cancel',reason})});detailDialog.close();if(current())document.querySelector('#refresh').click();}catch(err){window.OPDialogs.alert(err.message);}finally{cancel.disabled=false;}};detailDialog.querySelector('.detail-body').append(cancel);
    }
  }
  async function mount(container, {tab, api, navigate}) {
    const ticket=++serial, token=sessionStorage.getItem('token_op');
    const current=()=>ticket===serial && container.isConnected && sessionStorage.getItem('token_op')===token;
    if(previous!==tab){page=1;search='';status='';previous=tab;}
    container.innerHTML='<p>正在读取平台管理数据…</p>';
    const reload=()=>mount(container,{tab,api,navigate});
    try {
      const isOrders=['orders','shipments','after-sales'].includes(tab), hasShop=['products','orders','shipments','after-sales','coupons'].includes(tab);
      const shops=hasShop?await api('/op/platform/shops?size=100'):{items:[]};if(!current())return;
      if(shop && !shops.items.some(s=>String(s.id)===shop))shops.items.push({id:shop,name:shopName||'选定店铺'});
      const params=new URLSearchParams({page:String(page),q:search,days,status});if(shop)params.set('shop_id',shop);
      let url='/op/platform/'+tab;
      if(tab==='shipments'){url='/op/platform/orders';params.set('shipped_only','true');params.delete('status');if(status)params.set('shipment_status',status);}
      if(tab==='after-sales'){url='/op/platform/orders';params.set('after_sales_only','true');params.delete('status');if(status)params.set('after_sale_status',status);}
      if(tab==='products')url='/op/records/products';
      if(tab==='management-audits')url='/op/platform/audits';
      const data=await api(url+'?'+params);if(!current())return;
      const columns=tab==='coupons'?['优惠券 / 小店','发行状态','门槛 / 优惠','已领 / 发行','未用 / 锁定 / 核销','有效期','操作']:tab==='accounts'?['账号','昵称','关联小店','开店权限','平台权限','状态','操作']:tab==='shops'?['小店名称','店主账号','分享码','商品数','订单数','营业状态','管理入口']:tab==='products'?['商品','所属小店','分类','库存','状态','操作']:isOrders?['订单号','小店 / 买家',tab==='shipments'?'物流状态':tab==='after-sales'?'售后状态':'订单状态','应付金额','物流单号','下单时间','详情']:['操作人','对象类型','对象ID','动作','原因','时间'];
      const action=(name,id,text)=>`<button data-action="${name}" data-id="${id}">${text}</button>`;
      const rows=data.items.map(r=>{
        let cells=[];
        if(tab==='coupons')cells=[`${e(r.name)}<small class="cell-sub">${e(r.shop_name)}</small>`,badge(r.issuance_state),`${money(r.threshold_cents)} / −${money(r.amount_cents)}`,`${r.claimed_count} / ${r.total_count}`,`${r.unused_count} / ${r.reserved_count} / ${r.used_count}`,`${e(date(r.starts_at))}<small class="cell-sub">至 ${e(date(r.ends_at))}</small>`,action('coupon-workspace',r.shop_id,'管理优惠券')];
        else if(tab==='accounts')cells=[e(r.username),e(r.nickname),e(r.shop_name),r.merchant_enabled?'已授权':'未授权',r.operator?'平台管理员':'普通账号',r.closed?'已注销':r.disabled?'已禁用':'正常',r.closed?'—':`${action('account',r.id,'编辑')}${action('purchases',r.id,'购买记录')}${action('customer-info',r.id,'买家资料')}${action(r.disabled?'enable':'disable',r.id,r.disabled?'恢复账号':'禁用账号')}${action('reset_password',r.id,'重置密码')}${action(r.operator?'revoke_operator':'grant_operator',r.id,r.operator?'撤销平台权限':'授予平台权限')}${action(r.merchant_enabled?'revoke':'grant',r.id,r.merchant_enabled?'撤销开店':'授权开店')}`];
        else if(tab==='shops')cells=[e(r.name),e(r.owner),e(r.share_code),r.products,r.orders,r.platform_blocked?badge('banned'):badge(r.status),`${action('full-workspace',r.id,'完整维护')}${action(r.platform_blocked?'unfreeze':'freeze',r.id,r.platform_blocked?'解除封店':'平台封店')}${action('shop',r.id,'设置')}${action('shop-products',r.id,'商品')}${action('shop-orders',r.id,'订单')}`];
        else if(tab==='products')cells=[e(r.name),e(r.shop_name),e(r.category),r.stock,badge(r.status),`${action('full-product',r.id,'完整编辑')}${action('product',r.id,'规格详情')}${action(r.status==='banned'?'release':'ban',r.id,r.status==='banned'?'解除禁售':'禁售')}`];
        else if(isOrders)cells=[e(r.order_no),`${e(r.shop_name)}<small class="cell-sub">${e(r.buyer)}</small>`,badge(tab==='shipments'?r.shipment_status:tab==='after-sales'?r.after_sale_status:r.status),money(r.total_cents),`${e(r.tracking_number||'未发货')}<small class="cell-sub">${e(r.carrier||'')}</small>`,e(date(r.created_at)),action('order',r.id,'查看详情')];
        else cells=[r.operator_id,e(r.target_type),r.target_id,e(r.action),e(r.reason),e(date(r.created_at))];
        return `<tr>${cells.map(v=>`<td>${v}</td>`).join('')}</tr>`;
      }).join('');
      container.innerHTML=`<div class="list-heading"><div><h2>${titles[tab]}</h2><span>${data.needs_filter?'按店铺或关键词查询，不默认展示全平台订单':`共 ${data.total} 条记录 · 跨店铺统一管理`}</span></div>${tab==='accounts'?'<button data-create-account class="primary">新增账号</button>':'<span class="list-tag">平台视角</span>'}</div><form class="toolbar management-toolbar">${hasShop?`<select name="shop" aria-label="选择店铺"><option value="">${isOrders?'请先选择小店':'全部小店'}</option>${shops.items.map(s=>`<option value="${s.id}" ${String(s.id)===shop?'selected':''}>${e(s.name)}</option>`).join('')}</select>`:''}${tab!=='management-audits'?`<input name="q" value="${e(search)}" placeholder="${isOrders?'订单号 / 买家账号 / 物流单号':'搜索账号或名称'}" aria-label="搜索关键词">`:''}${isOrders?`<select name="days" aria-label="时间范围">${[7,30,90,365].map(n=>`<option value="${n}" ${String(n)===days?'selected':''}>最近 ${n} 天</option>`).join('')}</select>`:''}${['products','orders','shipments','after-sales','coupons'].includes(tab)?`<select name="status" aria-label="状态筛选"><option value="">全部状态</option>${(tab==='products'?['on','off','draft','banned']:tab==='shipments'?['shipped','transit','exception','delivered']:tab==='after-sales'?['requested','accepted','rejected','return_shipped','resolved','withdrawn']:tab==='coupons'?['active','scheduled','expired','disabled','exhausted']:['pending','paid','shipped','completed','cancelled']).map(s=>`<option value="${s}" ${status===s?'selected':''}>${labels[s]}</option>`).join('')}</select>`:''}<button class="primary">查询</button><button type="button" data-reset>重置</button></form>${data.needs_filter?'<section class="order-start"><div>⌕</div><h3>先定位小店，再查看订单</h3><p>选择一家小店查看最近 7 天订单，或输入订单号、买家账号、物流单号查找。</p><small>搜索关键词时查询历史记录；时间筛选用于按店铺浏览。</small></section>':`<div class="table-wrap"><table><thead><tr>${columns.map(c=>`<th>${c}</th>`).join('')}</tr></thead><tbody>${rows||`<tr><td colspan="${columns.length}" class="empty-cell">暂无符合条件的记录</td></tr>`}</tbody></table></div><div class="pager"><button data-prev ${page===1?'disabled':''}>上一页</button><span>${page} / ${Math.max(1,Math.ceil(data.total/20))}</span><button data-next ${page*20>=data.total?'disabled':''}>下一页</button></div>`}<p class="notice">${isOrders?'订单按条件分页展示。购买信息为下单时快照，物流轨迹由商家维护。':hasShop?'可选择具体小店管理。超过100家小店时，可先在店铺管理中搜索定位，再进入商品或订单。':'账号的开店授权与平台运营权限分别管理；操作记录可在平台管理记录中查看。'}</p>`;
      container.querySelector('[data-create-account]')?.addEventListener('click',()=>window.OPComplete.createAccount(api,reload));
      const form=container.querySelector('form');form.onsubmit=ev=>{ev.preventDefault();const values=new FormData(form);search=String(values.get('q')||'');status=String(values.get('status')||'');days=String(values.get('days')||days);shop=String(values.get('shop')??shop);shopName=form.querySelector('[name=shop]')?.selectedOptions[0]?.textContent||shopName;page=1;reload();};
      container.querySelector('[data-reset]').onclick=()=>{search='';status='';shop='';days='7';page=1;reload();};
      container.querySelector('[data-prev]')?.addEventListener('click',()=>{page--;reload();});container.querySelector('[data-next]')?.addEventListener('click',()=>{page++;reload();});
      container.querySelectorAll('[data-action]').forEach(button=>button.onclick=async()=>{
        if(button.disabled)return;button.disabled=true;const id=Number(button.dataset.id), action=button.dataset.action, row=data.items.find(r=>r.id===id);
        try {
          if(action==='full-workspace'){window.OPComplete.workspace(id,'dashboard',row.name);return;}
          if(action==='full-product'){window.OPComplete.workspace(row.shop_id,'products/'+id,row.shop_name);return;}
          if(action==='customer-info'){window.OPComplete.customer(id,row.username,api);return;}
          if(action==='coupon-workspace'){window.OPComplete.workspace(id,'coupons','优惠券管理');return;}
          if(['freeze','unfreeze','disable','enable','reset_password','grant_operator','revoke_operator'].includes(action)){if(await window.OPComplete.control(['freeze','unfreeze'].includes(action)?'shops':'accounts',id,action,api))reload();return;}
          if(action==='purchases'){previous='orders';page=1;search=row.username;status='';shop='';navigate('orders');return;}
          if(action==='order'){await orderDetail(id,api,current);return;}
          if(action==='shop-products'||action==='shop-orders'){shop=String(id);shopName=row.name;navigate(action==='shop-orders'?'orders':'products');return;}
          if(action==='product'){const p=await api('/op/platform/products/'+id);if(!current())return;const skuDialog=dialog(p.name,`${pairs([['所属小店',e(p.shop_name)],['商品状态',badge(p.status)],['分类',e(p.category)]])}<p>${e(p.description)}</p><h3>规格与库存</h3><div class="table-wrap"><table><thead><tr><th>SKU</th><th>规格</th><th>价格</th><th>库存</th><th>状态</th><th>平台操作</th></tr></thead><tbody>${p.skus.map(s=>`<tr><td>${s.id}</td><td>${e(s.spec)}</td><td>${money(s.price_cents)}</td><td>${s.stock}</td><td>${badge(s.status)}</td><td><button data-sku="${s.id}" data-sku-action="${s.status==='banned'?'unban':'ban'}">${s.status==='banned'?'解除禁售':'禁售规格'}</button></td></tr>`).join('')}</tbody></table></div>` );skuDialog.querySelectorAll('[data-sku]').forEach(btn=>btn.onclick=async()=>{btn.disabled=true;try{if(await window.OPComplete.control('skus',btn.dataset.sku,btn.dataset.skuAction,api)){skuDialog.close();if(current())reload();}}catch(err){window.OPDialogs.alert(err.message);}finally{btn.disabled=false;}});return;}
          if(['grant','revoke','ban','release'].includes(action)){
            const reason=await window.OPDialogs.prompt('请填写'+({grant:'授权开店',revoke:'撤销开店',ban:'禁售商品',release:'解除禁售'}[action])+'原因（2—200字）');if(reason===null)return;if(reason.trim().length<2||reason.length>200)throw Error('请填写2—200字的操作原因');
            if(action==='grant'||action==='revoke')await api('/op/platform/accounts/'+id,{method:'PATCH',body:JSON.stringify({merchant_enabled:action==='grant',reason})});
            else await api('/op/products/'+id+'/moderate',{method:'POST',body:JSON.stringify({action,reason})});
            if(current())reload();return;
          }
          if(action==='account'||action==='shop'){
            const info=action==='shop'?await api('/op/platform/shops/'+id):row;if(!current())return;
            const d=dialog(action==='shop'?'管理 '+info.name:'管理账号 '+info.username,`<form class="management-edit">${action==='shop'?`<label>店铺名称<input name="name" required maxlength="64" value="${e(info.name)}"></label><label>店铺公告<textarea name="notice" maxlength="2000">${e(info.notice)}</textarea></label><label>营业状态<select name="status"><option value="open" ${info.status==='open'?'selected':''}>营业中</option><option value="closed" ${info.status==='closed'?'selected':''}>已停业</option></select></label><p class="notice">这里设置店铺当前营业状态，商家可在B端自行调整营业状态。</p>`:`<label>账号昵称<input name="nickname" required maxlength="32" value="${e(info.nickname)}"></label><p class="notice">账号：${e(info.username)} · 关联小店：${e(info.shop_name)}</p>`}<label>操作原因<input name="reason" required minlength="2" maxlength="200" placeholder="请填写修改原因"></label><p class="edit-error" role="alert"></p><button type="submit" class="primary">保存修改</button></form>`);
            d.querySelector('form').onsubmit=async ev=>{ev.preventDefault();const form=ev.currentTarget,submit=form.querySelector('[type=submit]');submit.disabled=true;try{await api('/op/platform/'+(action==='shop'?'shops':'accounts')+'/'+id,{method:'PATCH',body:JSON.stringify(Object.fromEntries(new FormData(form)))});d.close();if(current())reload();}catch(err){form.querySelector('.edit-error').textContent=err.message;}finally{submit.disabled=false;}};
          }
        } catch(error){if(current())window.OPDialogs.alert(error.message);} finally{button.disabled=false;}
      });
    } catch(error){if(current())container.innerHTML=`<p class="error">${e(error.message)}。请刷新重试。</p>`;}
  }
  window.OPManagement={handles:tab=>managed.includes(tab),cancel:()=>{serial++;document.querySelectorAll('.op-detail').forEach(d=>d.remove());},mount};
})();
