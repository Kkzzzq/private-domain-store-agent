const STATUS = {
  draft: "草稿",
  on: "在售",
  off: "下架",
  banned: "禁售",
  open: "营业中",
  closed: "已停业",
  pending: "待支付",
  paid: "已支付",
  shipped: "已发货",
  completed: "已完成",
  cancelled: "已取消",
};

/* 面向用户的回答不展示检索来源与知识库术语：这里曾经拼接“来源（关键词检索）…”，已按运营要求移除。 */

function money(value) {
  return `¥${Number(value || 0).toFixed(2)}`;
}

function detailOf(data) {
  if (!data) return "请求失败";
  if (typeof data.detail === "string") return data.detail;
  if (Array.isArray(data.detail)) return data.detail.map((item) => item.msg).join("；");
  return "请求失败";
}

function expireAuth(response, tokenKey, token) {
  if (response.status === 401 && token && sessionStorage.getItem(tokenKey) === token) {
    sessionStorage.removeItem(tokenKey);
    window.dispatchEvent(new CustomEvent("store-auth-expired", {detail: {tokenKey}}));
  }
}

function createApi(tokenKey) {
  return async function api(path, options = {}) {
    const headers = { ...(options.headers || {}) };
    const token = sessionStorage.getItem(tokenKey);
    if (token) headers.Authorization = `Bearer ${token}`;
    if (options.body) headers["Content-Type"] = "application/json";
    const response = await fetch(path, { ...options, headers });
    expireAuth(response, tokenKey, token);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(detailOf(data));
    return data;
  };
}

function storefrontSettings(shop) {
  return {
    background_color: "#faf7f2", surface_color: "#fffcf7", text_color: "#38332e", muted_color: "#756b62",
    product_image_ratio: "4/5", rail_columns: "3.5", hero_enabled: true, promises_enabled: true, assistant_enabled: true,
    merchant_title: "商家工作台",
    brand_slogan: "器物有温度，日常有心意",
    portal_title: "让喜欢的好物，走进日常。",
    portal_description: "逛逛小店，发现一件心仪之物。也让每一份用心经营，都有条不紊。",
    product_subtitle: "店主直发 · 小批量手作", footer_about: "私域独立店铺 · 分享码进店",
    footer_service: "有问题点右下角问店内助手", dispatch_text: "付款后48小时内发货",
    return_text: "7天无理由退货，定制品和已使用商品除外", free_shipping_yuan: 99, base_freight_yuan: 8,
    assistant_welcome: "可以推荐商品、查询库存和你自己的订单，也能检索售后和养护说明哦。",
    quick_questions: ["抱枕还有货吗", "我的订单到哪了", "定制品能退吗"],
    testimonial_title: "买家反馈", testimonial_subtitle: "店铺展示的买家反馈", detail_sections: [],
    ...(shop?.storefront || {}),
  };
}

function applyStorefrontSettings(shop) {
  const settings = storefrontSettings(shop);
  const style = document.documentElement.style;
  for (const [field, variable] of [["background_color", "--store-background"], ["surface_color", "--store-surface"], ["text_color", "--ink"], ["muted_color", "--muted"]]) {
    if (/^#[\da-f]{6}$/i.test(settings[field])) style.setProperty(variable, settings[field]);
  }
  const columns = ["3", "3.5", "4"].includes(settings.rail_columns) ? Number(settings.rail_columns) : 3.5;
  style.setProperty("--store-rail-columns", String(columns));
  style.setProperty("--store-rail-gap-total", `${(Math.ceil(columns) - 1) * 17}px`);
  style.setProperty("--store-card-ratio", settings.product_image_ratio);
}

function storeShippingText(shop) {
  const settings = storefrontSettings(shop);
  return settings.free_shipping_yuan === 0 || settings.base_freight_yuan === 0 ? "全店包邮"
    : `满 ${settings.free_shipping_yuan} 元包邮，未满收 ${settings.base_freight_yuan} 元运费`;
}

function storeFreight(shop, goodsYuan) {
  const settings = storefrontSettings(shop);
  return goodsYuan <= 0 || Math.round(goodsYuan * 100) >= Math.round(settings.free_shipping_yuan * 100) ? 0 : settings.base_freight_yuan;
}

function storeAssistantName(shop) {
  const brand = (shop?.name || "店").replace(/[^\u4e00-\u9fffA-Za-z0-9]/g, "").replace(/(?:手作|生活馆|店铺|小店|商城|商店|店)$/, "");
  return shop?.assistant_name || `小${/^[\u4e00-\u9fff]+$/.test(brand) ? brand.slice(-1) : "店"}`;
}

function assistantWaitingText(shop) {
  return `${storeAssistantName(shop)}正在理解并且为您提供最优方案`;
}

function renderAssistantMessage(element, text) {
  element.replaceChildren();
  element.classList.add("assistant-markdown");
  const inline = (parent, value, depth = 0) => {
    if (depth > 4) { parent.append(document.createTextNode(value)); return; }
    const pattern = /(`[^`\n]+`|\*\*[^\n]+?\*\*|\[[^\]\n]+\]\([^\s)]+\))/g;
    let offset = 0;
    for (const match of value.matchAll(pattern)) {
      parent.append(document.createTextNode(value.slice(offset, match.index)));
      const part = match[0];
      if (part.startsWith("**")) {
        const strong = document.createElement("strong");
        inline(strong, part.slice(2, -2), depth + 1);
        parent.append(strong);
      } else if (part.startsWith("`")) {
        const code = document.createElement("code");
        code.textContent = part.slice(1, -1);
        parent.append(code);
      } else {
        const link = part.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
        let url;
        try { url = new URL(link[2]); } catch {}
        if (url && ["http:", "https:"].includes(url.protocol)) {
          const anchor = document.createElement("a");
          anchor.href = url.href;
          anchor.rel = "noopener noreferrer";
          inline(anchor, link[1], depth + 1);
          parent.append(anchor);
        } else parent.append(document.createTextNode(part));
      }
      offset = match.index + part.length;
    }
    parent.append(document.createTextNode(value.slice(offset)));
  };
  let list = null;
  let paragraph = null;
  let codeBlock = null;
  for (const line of String(text || "").replace(/\r\n/g, "\n").split("\n")) {
    if (/^\s*```/.test(line)) {
      if (codeBlock) codeBlock = null;
      else {
        const pre = document.createElement("pre");
        codeBlock = document.createElement("code");
        pre.append(codeBlock);
        element.append(pre);
      }
      list = paragraph = null;
      continue;
    }
    if (codeBlock) { codeBlock.append(document.createTextNode(line + "\n")); continue; }
    if (!line.trim()) { list = paragraph = null; continue; }
    const item = line.match(/^\s*(?:(\d+)[.)、]|([-*]))\s+(.+)$/);
    if (item) {
      const tag = item[1] ? "ol" : "ul";
      if (!list || list.tagName.toLowerCase() !== tag) {
        list = document.createElement(tag);
        if (item[1]) list.start = Number(item[1]);
        element.append(list);
      }
      const child = document.createElement("li");
      inline(child, item[3]);
      list.append(child);
      paragraph = null;
      continue;
    }
    list = null;
    const heading = line.match(/^#{1,6}\s+(.+)$/);
    if (heading) {
      const title = document.createElement("h4");
      inline(title, heading[1]);
      element.append(title);
      paragraph = null;
      continue;
    }
    if (!paragraph) { paragraph = document.createElement("p"); element.append(paragraph); }
    else paragraph.append(document.createElement("br"));
    inline(paragraph, line);
  }
}

async function streamChat(path, tokenKey, body, onProgress, onPreview = () => {}) {
  const token = sessionStorage.getItem(tokenKey) || "";
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify(body),
  });
  expireAuth(response, tokenKey, token);
  if (!response.ok) throw new Error(detailOf(await response.json().catch(() => ({}))));
  if (!response.body) throw new Error("浏览器不支持流式响应，请更新浏览器");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  const labels = { accepted: "请求已接收", context: "正在读取本次会话", model: "模型正在理解需求与组织回答", model_done: "模型已完成本轮处理", tool: "正在查询实时业务数据", tool_done: "数据查询完成", saving: "正在保存会话" };
  const tools = { get_store_catalog: "正在了解本店商品", recommend_products: "正在按需求筛选商品和库存", search_products: "正在查询商品和库存", check_inventory: "正在核对库存", search_knowledge: "正在查询店铺资料", query_orders: "正在查询你有权限查看的订单", merchant_overview: "正在查询本店经营概况", low_inventory: "正在查询库存预警" };
  try {
    while (true) {
      const { done, value } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      const lines = buffer.split("\n");
      buffer = lines.pop();
      if (done && buffer.trim()) { lines.push(buffer); buffer = ""; }
      for (const line of lines) {
        if (!line.trim()) continue;
        const event = JSON.parse(line);
        if (event.type === "error") throw new Error(event.detail || "助手暂时不可用");
        if (event.type === "result") return event.data;
        if (event.type === "preview") onPreview(event);
        if (event.type === "progress") onProgress(`${(event.stage === "tool" && tools[event.tool]) || labels[event.stage] || "正在处理"}…`);
        if (event.type === "heartbeat") onProgress(`请求仍在处理，已等待 ${Math.floor(event.elapsed_ms / 1000)} 秒…`);
      }
      if (done) throw new Error("回复连接中断，请重试");
    }
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}

function statusActions(status) {
  if (status === "draft") return [["on", "发布上架"], ["off", "完成创建"]];
  if (status === "on") return [["off", "下架"], ["ban", "禁售"]];
  if (status === "off") return [["on", "上架"], ["ban", "禁售"]];
  return [];
}

function toast(message, kind = "info") {
  let host = document.querySelector(".toast-host");
  if (!host) {
    host = document.createElement("div");
    host.className = "toast-host";
    document.body.append(host);
  }
  const node = document.createElement("div");
  node.className = `toast ${kind}`;
  node.textContent = message;
  host.append(node);
  setTimeout(() => {
    node.classList.add("out");
    setTimeout(() => node.remove(), 280);
  }, 2400);
}

/** 把店铺主题色写到 :root，整站配色跟着变。 */
function applyTheme(color) {
  if (typeof color === "string" && /^#[0-9a-fA-F]{6}$/.test(color)) {
    document.documentElement.style.setProperty("--theme", color);
  }
}

function star(value) {
  const filled = "★".repeat(Math.round(value));
  const empty = "☆".repeat(Math.max(0, 5 - Math.round(value)));
  return `${filled}${empty}`;
}

/** Read-only scores render locally; interactive scoring uses wa-rating. */
function ratingStars(value, { readonly = true, size = "s", label = "评分" } = {}) {
  if (readonly) {
    const score = Math.min(5, Math.max(0, Number(value) || 0));
    const rating = document.createElement('span');
    rating.className = 'review-rating';
    rating.setAttribute('role','img');
    rating.setAttribute('aria-label', `${label} ${score.toFixed(1)} 分，满分 5 分`);
    const icons = document.createElement('span'); icons.className = 'review-rating-icons'; icons.setAttribute('aria-hidden','true');
    const star = () => {
      const svg = document.createElementNS('http://www.w3.org/2000/svg','svg');
      svg.setAttribute('viewBox','0 0 24 24');
      const path = document.createElementNS('http://www.w3.org/2000/svg','path');
      path.setAttribute('d','m12 3 2.78 5.63 6.22.91-4.5 4.38 1.06 6.19L12 17.19l-5.56 2.92 1.06-6.19L3 9.54l6.22-.91Z');
      svg.append(path);return svg;
    };
    for(let index=0;index<5;index++) {
      const slot=document.createElement('span');slot.className='review-rating-star';slot.append(star());
      const fill=document.createElement('span');fill.className='review-rating-fill';fill.style.width=`${Math.max(0,Math.min(1,score-index))*100}%`;fill.append(star());slot.append(fill);icons.append(slot);
    }
    const number=document.createElement('span');number.className='review-rating-score';number.textContent=score.toFixed(1);
    rating.append(icons,number);return rating;
  }
  const node = document.createElement("wa-rating");
  node.setAttribute("label", label);
  node.setAttribute("size", size);
  node.setAttribute("max", "5");
  node.setAttribute("value", String(value || 0));
  if (readonly) node.setAttribute("readonly", "");
  node.className = "stars-widget";
  return node;
}

function ratingText(value, count) {
  if (!count) return "暂无评价";
  return `${Number(value).toFixed(1)} 分 · ${count} 条评价`;
}

/** 待支付订单的剩余时间。 */
function remainText(seconds) {
  if (seconds == null) return "";
  const total = Math.max(0, Math.floor(seconds));
  const mm = String(Math.floor(total / 60)).padStart(2, "0");
  const ss = String(total % 60).padStart(2, "0");
  return `${mm}:${ss}`;
}

function applyTagStyle(node, tag) {
  for (const [key, variable] of [["color", "--tag"], ["background_color", "--tag-background"], ["border_color", "--tag-border"], ["text_color", "--tag-text"]]) {
    if (/^#[0-9a-f]{6}$/i.test(tag?.[key] || "")) node.style.setProperty(variable, tag[key]);
    else node.style.removeProperty(variable);
  }
}

function tagColorDefaults(tag) {
  const base = /^#[0-9a-f]{6}$/i.test(tag?.color || "") ? tag.color : "#c85032";
  const mix = (weight, other) => "#" + [1, 3, 5].map(offset =>
    Math.round(parseInt(base.slice(offset, offset + 2), 16) * weight +
      parseInt(other.slice(offset, offset + 2), 16) * (1 - weight)).toString(16).padStart(2, "0")).join("");
  return {
    background_color: tag?.background_color || mix(.08, "#ffffff"),
    border_color: tag?.border_color || mix(.24, "#ffffff"),
    text_color: tag?.text_color || mix(.83, "#24201c"),
  };
}

function maskName(name) {
  if (!name) return "买家";
  return name.length <= 1 ? name : name[0] + "*".repeat(name.length - 1);
}

