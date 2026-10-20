/* Per-history-entry restoration for asynchronous hash routes. No business data is cached. */
window.StoreScrollHistory = ({readState, restoreState}) => {
  const key = `store-scroll-v1:${location.pathname}${location.search}`;
  let entries = {}, active = null, rendering = false, revision = 0;
  try { entries = JSON.parse(sessionStorage.getItem(key) || '{}'); } catch {}
  history.scrollRestoration = 'manual';
  const remember = () => {
    if (!active || rendering || entries[active]?.url !== location.href) return;
    entries[active] = {...entries[active], x:window.scrollX, y:window.scrollY, view:readState()};
  };
  const persist = () => {
    remember();
    try { sessionStorage.setItem(key, JSON.stringify(Object.fromEntries(Object.entries(entries).slice(-80)))); } catch {}
  };
  window.addEventListener('scroll', remember, {passive:true});
  window.addEventListener('pagehide', persist);
  document.addEventListener('click', remember, {capture:true});
  function begin() {
    const previous = active;
    // During traversal the URL already points to the destination; the old DOM is still mounted.
    if (previous && !rendering) entries[previous] = {...entries[previous],x:window.scrollX,y:window.scrollY};
    let id = history.state?.storeScrollId;
    const known = id && entries[id]?.url === location.href;
    if (!known) {
      id = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
      entries[id] = {url:location.href,x:0,y:0,view:null};
      history.replaceState({...history.state,storeScrollId:id},'');
    }
    const changed = id !== previous;
    active = id; rendering = true;
    const ticket = {id,revision:++revision,changed,x:entries[id].x,y:entries[id].y};
    if (changed && known && entries[id].view) restoreState(entries[id].view);
    return ticket;
  }
  async function finish(ticket, ready) {
    await ready;
    if (ticket.revision !== revision || ticket.id !== active) return;
    if (ticket.changed) window.scrollTo({left:ticket.x,top:ticket.y,behavior:'instant'});
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    if (ticket.revision !== revision || ticket.id !== active) return;
    if (ticket.changed) window.scrollTo({left:ticket.x,top:ticket.y,behavior:'instant'});
    rendering = false;remember();persist();
  }
  return {begin,finish,remember};
};
