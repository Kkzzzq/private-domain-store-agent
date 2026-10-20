(() => {
  const shopId = Number(new URLSearchParams(location.search).get('shop_id'));
  if (!Number.isSafeInteger(shopId) || shopId < 1) throw Error('请从 OP 选择一家小店后进入维护');
  const rawFetch = window.fetch.bind(window);
  const scope = '/api/v1/op/shops/' + shopId;
  window.fetch = async (input, options = {}) => {
    const source = input instanceof Request ? input : null;
    const url = new URL(source ? source.url : input, location.origin);
    if (url.origin !== location.origin || !url.pathname.startsWith('/api/v1/')) return rawFetch(input,options);
    const method = String(options.method || source?.method || 'GET').toUpperCase();
    if (url.pathname.startsWith('/api/v1/b/') || url.pathname.startsWith('/api/v1/support/')) {
      url.pathname = scope + url.pathname.slice('/api/v1'.length);
    } else if (url.pathname === '/api/v1/auth/me' && method === 'GET') {
      url.pathname = '/api/v1/op/me';
    } else if (!url.pathname.startsWith('/api/v1/op/')) {
      throw Error('当前为平台维护工作区，请通过对应的运营入口操作');
    }
    const token=sessionStorage.getItem('token_op');
    if (!token) throw Error('请返回 OP 使用运营账号登录');
    const headers=new Headers(options.headers || source?.headers);
    headers.set('Authorization','Bearer '+token);
    if (!['GET','HEAD','OPTIONS'].includes(method)) {
      const reason=document.querySelector('#op-scope-reason').value.trim();
      if(reason.length<2)throw Error('请在顶部填写至少两个字的操作原因');
      headers.set('X-OP-Reason',encodeURIComponent(reason));
    }
    const response=await rawFetch(source?new Request(url,source):url,{...options,headers});
    if(sessionStorage.getItem('token_op')!==token)throw Error('运营身份已变化');
    if(response.ok && !['GET','HEAD','OPTIONS'].includes(method))parent.postMessage({type:'op-workspace-updated',shopId},location.origin);
    if(response.status===401)parent.postMessage({type:'op-workspace-expired'},location.origin);
    if (url.pathname===scope+'/b/shop' && method==='GET' && response.ok) {
      response.clone().json().then(shop=>{
        document.querySelector('#op-scope-shop').textContent=shop.name+' · #'+shop.id+(shop.platform_blocked?' · 平台已封店':'');
      });
    }
    return response;
  };
  window.StoreAuth={
    ensureSession:async()=>{
      const user=await createApi('token_op')('/api/v1/op/me');
      document.querySelector('.op-scope-brand').textContent='OP · '+(user.nickname||user.username);
      return {user,can_manage_shop:true};
    },
    createForm:()=>{const p=document.createElement('p');p.textContent='运营登录已失效，请返回OP重新登录。';return p;},
    logout:async()=>{throw Error('请返回OP退出运营账号');}
  };
  // A new logged-in operator must not inherit another operator's open workspace.
  const openedToken=sessionStorage.getItem('token_op');
  setInterval(()=>{if(sessionStorage.getItem('token_op')!==openedToken){document.querySelector('#app').textContent='运营身份已变化，请关闭后重新进入。';window.fetch=()=>Promise.reject(Error('运营身份已变化'));}},1000);
})();
