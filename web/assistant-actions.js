/* Role-specific assistant shortcuts. Actions use existing authenticated business pages. */
(() => {
  const node = (tag, cls, text) => { const el=document.createElement(tag); el.className=cls; if(text!=null)el.textContent=text; return el; };
  const button = (text, callback) => { const el=node('button','assistant-action',text); el.type='button'; el.addEventListener('click',callback); return el; };
  function support(tab='chat', orderNo='', shopCode='') {
    document.dispatchEvent(new CustomEvent('store-support-open',{detail:{tab,orderNo,shopCode}}));
  }
  function toolbar({role,ask,orders,shopCode=''}) {
    const merchant=role==='merchant', box=node('nav','assistant-action-bar');
    box.setAttribute('aria-label',merchant?'商家助手功能':'买家助手功能');
    const specs=merchant ? [
      ['本店订单',()=>ask('查询本店订单')],['订单管理',orders],
      ['发货与物流',()=>support('shipping')],['客户消息',()=>support('chat')],
      ['售后处理',()=>support('tickets')],['配置商品',()=>ask('帮我配置商品，请先询问需要的商品名称、规格、售价和库存')],
      ['库存预警',()=>ask('本店库存预警')],['经营概览',()=>ask('本店经营概览')]
    ] : [
      ['查我的订单',()=>ask('查询我的订单')],['订单中心',orders],
      ['订单物流',()=>support('shipping','',shopCode)],['联系商家',()=>support('chat','',shopCode)],
      ['申请售后',()=>support('tickets','',shopCode)]
    ];
    specs.forEach(([text,fn])=>box.append(button(text,fn)));return box;
  }
  function orderActions(container,text,{role,orders,shopCode=''}) {
    if(/没有找到|还没有订单|暂无订单/.test(text||''))return;
    const numbers=[...new Set((text||'').toUpperCase().match(/\bPS\d{8,32}\b/g)||[])].slice(0,5);
    numbers.forEach(number=>{
      const box=node('section','assistant-order-actions');box.setAttribute('aria-label',`订单${number}操作`);
      box.append(node('strong','',number),button('查看订单',orders),
        button(role==='merchant'?'发货 / 物流':'查看物流',()=>support('shipping',number,shopCode)),
        button(role==='merchant'?'联系买家':'就此订单联系商家',()=>support('chat',number,shopCode)),
        button(role==='merchant'?'处理售后':'申请售后',()=>support('tickets',number,shopCode)));
      container.append(box);
    });
  }
  window.StoreAssistantActions={toolbar,orderActions,support};
})();
