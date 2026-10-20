// The portal always belongs to the authenticated account, never a query-string shop.
(async () => {
  const login = () => location.replace('/account-login.html');
  try {
    if (!(await StoreAuth.currentUser())) { login(); return; }
    const preferred = sessionStorage.getItem('portal_role') === 'customer' ? ['token_c','token_b'] : ['token_b','token_c'];
    const token = sessionStorage.getItem(preferred[0]) || sessionStorage.getItem(preferred[1]);
    const response = await fetch('/api/v1/auth/portal-session', {method:'POST',headers:{Authorization:`Bearer ${token}`,'Content-Type':'application/json'},
      body:JSON.stringify({token_b:sessionStorage.getItem('token_b')||'',token_c:sessionStorage.getItem('token_c')||''})});
    if (response.status === 401) { login(); return; }
    if (!response.ok) throw Error('店铺入口暂时不可用，请刷新重试');
    const data=await response.json();
    StoreAuth.saveSession(data);
    const shop=data.shop, code=shop.share_code, settings=shop.storefront||{};
    document.title=`${shop.name} · 欢迎来到小店`;
    const name=document.querySelector('.brand-name');name.firstChild.textContent=shop.name;
    name.querySelector('small').textContent='PRIVATE STORE';
    document.querySelector('.brand').setAttribute('aria-label',`${shop.name}首页`);
    const oldMark=document.querySelector('.brand-mark');
    if(shop.logo_url){const mark=document.createElement('img');mark.className='brand-mark';mark.src=shop.logo_url;mark.alt=shop.name;oldMark.replaceWith(mark);}
    else oldMark.textContent=shop.name.slice(0,1);
    for(const [selector,key] of [['.header-note','brand_slogan'],['#welcome-title','portal_title'],['.intro-copy','portal_description']]){
      if(typeof settings[key]==='string')document.querySelector(selector).textContent=settings[key];
    }
    const buyer=document.querySelector('.entry-card');buyer.href=`/c.html?code=${encodeURIComponent(code)}`;
    buyer.querySelector('h2').textContent=`逛逛${shop.name}`;buyer.querySelector('.entry-code').textContent=`小店 · ${code}`;
    if(code!=='nanzhi')buyer.querySelector('.card-content > p').textContent='进入自己的店铺，查看商品与买家服务。';
    document.querySelector('.merchant-card').href='/b.html';
    document.querySelector('.portal-footer span').textContent=shop.name;
    const switcher=document.createElement('button');switcher.className='portal-account';switcher.type='button';switcher.textContent=`${data.user.nickname} · 切换账号`;
    switcher.addEventListener('click',async()=>{switcher.disabled=true;try{await StoreAuth.logout('token_b');location.href='/account-login.html?switch=1';}catch{switcher.textContent='退出失败，点击重试';switcher.disabled=false;}});
    document.querySelector('.portal-header').append(switcher);
    document.body.classList.remove('auth-pending');
  } catch(error) {
    const box=document.createElement('p');box.className='portal-error';box.textContent=error.message;document.body.append(box);
  }
})();
