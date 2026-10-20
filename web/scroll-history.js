/* Scroll snapshots belong to history entries, never to transient layout positions. */
window.StoreScrollHistory = ({readState, restoreState}) => {
  const key = `store-scroll-v1:${location.pathname}${location.search}`;
  let entries = {}, active = null, rendering = false, revision = 0, guard = null;
  try { entries = JSON.parse(sessionStorage.getItem(key) || '{}'); } catch {}
  history.scrollRestoration = 'manual';
  const write = () => {
    try { sessionStorage.setItem(key, JSON.stringify(Object.fromEntries(Object.entries(entries).slice(-80)))); } catch {}
  };
  const remember = () => {
    if (!active || rendering || guard || entries[active]?.url !== location.href) return;
    entries[active] = {...entries[active], x:window.scrollX, y:window.scrollY, view:readState()};
  };
  const stopGuard = () => {
    if (!guard) return;
    guard.observer?.disconnect(); clearTimeout(guard.timeout);
    document.removeEventListener('load', guard.apply, true);
    guard = null;
  };
  const userMoved = event => {
    if (event.type === 'keydown' && !['ArrowUp','ArrowDown','PageUp','PageDown','Home','End',' '].includes(event.key)) return;
    stopGuard();
    remember();
  };
  window.addEventListener('scroll', remember, {passive:true});
  for (const name of ['wheel','touchstart','pointerdown','keydown']) window.addEventListener(name,userMoved,{passive:true});
  window.addEventListener('pagehide', () => {remember();write();});
  document.addEventListener('click', () => {remember();write();}, {capture:true});
  function begin({preserve = false} = {}) {
    // Once the URL changes, the browser may already have reset/clamped scrollY.
    // Only sample the outgoing page while its own URL is still active.
    if (!preserve) remember();
    stopGuard();
    const previous = active;
    let id = history.state?.storeScrollId;
    const known = id && entries[id]?.url === location.href;
    if (!known) {
      id = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
      entries[id] = {url:location.href,x:0,y:0,view:null};
      history.replaceState({...history.state,storeScrollId:id},'');
    }
    active = id; rendering = true;
    const ticket = {id,revision:++revision,changed:id!==previous,x:entries[id].x,y:entries[id].y,url:location.href};
    if (ticket.changed && known && entries[id].view) restoreState(entries[id].view);
    write();return ticket;
  }
  async function finish(ticket, ready) {
    await ready;
    const current = () => ticket.revision === revision && ticket.id === active && location.href === ticket.url;
    if (!current()) return;
    stopGuard();
    const state = {apply:null,observer:null,timeout:null};
    const apply = () => {
      if (!current() || guard !== state) return;
      window.scrollTo({left:ticket.x,top:ticket.y,behavior:'instant'});
    };
    state.apply = apply;guard = state;rendering = false;
    entries[active] = {...entries[active],view:readState()};
    // Keep the requested coordinates even if the document is temporarily too short.
    // Image/font/layout completion retries restoration; deliberate user scrolling wins.
    if (typeof ResizeObserver !== 'undefined') {
      state.observer = new ResizeObserver(apply);
      state.observer.observe(document.documentElement);
      const root=document.getElementById('app');if(root)state.observer.observe(root);
    }
    document.addEventListener('load',apply,true);
    document.fonts?.ready.then(apply).catch(()=>{});
    state.timeout = setTimeout(() => {if(guard===state){stopGuard();write();}},8000);
    apply();write();
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    apply();
  }
  window.addEventListener('pageshow', event => {
    if (event.persisted) { const ticket=begin({preserve:true});finish(ticket); }
  });
  return {begin,finish,remember};
};
