function decorationPayload(data) {
  const fields = {
    banners: ["id", "image_url", "title", "subtitle", "link_type", "link_value", "enabled"],
    sections: ["id", "title", "subtitle", "source", "product_ids", "enabled"],
    testimonials: ["id", "nickname", "content", "rating", "enabled"],
  };
  const payload = {revision: data.revision, appearance: structuredClone(data.appearance)};
  for (const [kind, keys] of Object.entries(fields)) {
    payload[kind] = data[kind].map(row => Object.fromEntries(keys.map(key => [key, row[key]])));
  }
  return payload;
}

class DecorationWorkspace {
  constructor(snapshot, shop, storage, actorId) {
    this.shop = shop;
    this.storage = storage;
    this.key = `decoration-draft:${actorId}:${shop.id}`;
    this.baseline = decorationPayload(snapshot);
    this.data = structuredClone(snapshot);
    this.products = [];
    this.conflict = false;
    try {
      const cached = JSON.parse(storage.getItem(this.key) || "null");
      if (cached?.revision && cached.appearance && Array.isArray(cached.banners) && Array.isArray(cached.sections) && Array.isArray(cached.testimonials)) {
        this.data = cached;
        this.conflict = cached.revision !== snapshot.revision;
      }
    } catch {}
  }

  get dirty() {
    return JSON.stringify(decorationPayload(this.data)) !== JSON.stringify(this.baseline);
  }

  persist() {
    try {
      if (this.dirty) this.storage.setItem(this.key, JSON.stringify(this.data));
      else this.storage.removeItem(this.key);
    } catch {}
  }

  shopView() {
    return {...this.shop, ...structuredClone(this.data.appearance)};
  }

  candidate(kind, payload, id) {
    const next = structuredClone(this.data);
    if (kind === "appearance") next.appearance = {...next.appearance, ...payload};
    else {
      const index = next[kind].findIndex(row => row.id === id);
      if (index >= 0) next[kind][index] = {...next[kind][index], ...payload};
      else next[kind].push({id: Math.min(0, ...next[kind].map(row => row.id)) - 1, enabled: true, ...payload});
    }
    return next;
  }

  mutate(kind, method, payload, id) {
    if (method === "DELETE") {
      this.data[kind] = this.data[kind].filter(row => row.id !== id);
      if (kind === "sections") {
        for (const banner of this.data.banners) {
          if (banner.link_type === "section" && banner.link_value === String(id)) {
            banner.link_type = "none"; banner.link_value = "";
          }
        }
      }
    } else this.data = this.candidate(kind, payload, id);
    if (kind === "sections") {
      for (const row of this.data.sections) row.product_names = row.product_ids.map(productId =>
        this.products.find(product => product.id === productId)?.name || "原关联商品");
    }
    this.persist();
    return id == null ? structuredClone(this.data[kind].at(-1)) : structuredClone(this.data[kind].find(row => row.id === id) || {ok: true});
  }

  reorder(kind, ids) {
    const rows = this.data[kind];
    if (new Set(ids).size !== rows.length || ids.some(id => !rows.some(row => row.id === id))) throw new Error("排序列表已变化，请重试");
    this.data[kind] = ids.map((id, index) => ({...rows.find(row => row.id === id), sort_order: index + 1}));
    this.persist();
  }
}
