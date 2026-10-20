const liveApi = createApi("token_b");
let decorationWorkspace = null;
let decorationActor = "";
let decorationSaving = false;

async function api(path, options = {}) {
  const method = options.method || "GET";
  const workspace = route().name === "home" ? decorationWorkspace : null;
  if (workspace) {
    if (path === "/api/v1/b/shop") {
      if (method === "GET") return workspace.shopView();
      if (method === "PATCH") {
        workspace.data = workspace.candidate("appearance", JSON.parse(options.body));
        workspace.persist();
        return workspace.shopView();
      }
    }
    const match = path.match(/^\/api\/v1\/b\/(banners|sections|testimonials)(?:\/(-?\d+))?$/);
    if (match) {
      const [, kind, id] = match;
      if (method === "GET") return structuredClone(workspace.data[kind]);
      return workspace.mutate(kind, method, options.body ? JSON.parse(options.body) : {}, id ? Number(id) : null);
    }
  }
  const result = await liveApi(path, options);
  if (workspace && path === "/api/v1/b/products" && method === "GET") workspace.products = result;
  return result;
}
let me = null;
let shopInfo = null;
let switchingAccount = false;
let renderVersion = 0;
const productFilters = { keyword: "", status: "", category: "", stock: "", sort: "default", page: 1 };
const expandedProducts = new Set();

function h(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

function route() {
  const parts = (location.hash || "#/dashboard").slice(1).split("/").filter(Boolean);
  return { name: parts[0] || "dashboard", id: parts[1] || "" };
}

function go(hash) {
  if (location.hash === hash) render();
  else location.hash = hash;
}

function loggedIn() {
  return Boolean(sessionStorage.getItem("token_b"));
}

function cover(url) {
  return url || "/covers/notebook.jpg";
}

function openFormDialog(form, title, trigger) {
  const mask = h("div", "modal admin-editor-mask");
  const panel = h("section", "panel admin-editor-panel");
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-modal", "true");
  panel.setAttribute("aria-label", title);
  const heading = h("div", "admin-editor-heading");
  const close = h("button", "btn-ghost", "×");
  close.type = "button";
  close.setAttribute("aria-label", "关闭编辑");
  heading.append(h("h2", "", title), close);
  const dismiss = () => {
    if (form.querySelector('button[type="submit"]:disabled')) return;
    mask.remove();
    if (trigger?.isConnected) trigger.focus();
    render();
  };
  form.classList.add("admin-dialog-form");
  const footer = h("div", "admin-editor-actions");
  const cancel = h("button", "btn-ghost", "取消");
  cancel.type = "button";
  cancel.addEventListener("click", dismiss);
  const submit = form.querySelector('button[type="submit"]');
  footer.append(cancel);
  if (route().name === "home" && form.previewCandidate) {
    const preview = h("button", "btn-ghost", "预览效果");
    preview.type = "button";
    preview.addEventListener("click", async () => {
      if (preview.disabled) return;
      preview.disabled = true;
      try { await previewDecoration(form.previewCandidate()); }
      catch (error) { toast(error.message, "bad"); }
      finally { preview.disabled = false; }
    });
    footer.append(preview);
  }
  if (route().name === "home" && submit) submit.textContent = "应用到草稿";
  if (submit) footer.append(submit);
  form.append(footer);
  panel.append(heading, form);
  mask.append(panel);
  close.addEventListener("click", dismiss);
  mask.addEventListener("click", event => { if (event.target === mask) dismiss(); });
  mask.addEventListener("keydown", event => {
    if (event.key === "Escape") { event.preventDefault(); dismiss(); }
    if (event.key === "Tab") {
      const controls = [...panel.querySelectorAll("input, textarea, select, button, a[href]")].filter(node => !node.disabled && node.getClientRects().length);
      const first = controls[0], last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }
  });
  document.body.append(mask);
  close.focus();
}

function editorAction(title, label, factory) {
  const bar = h("div", "admin-list-heading");
  const button = h("button", "btn", label);
  button.addEventListener("click", () => openFormDialog(factory(), label.replace(/^＋ /, ""), button));
  bar.append(h("h2", "", title), button);
  return bar;
}

function settingsSummary(form, title, entries) {
  const panel = h("div", "panel settings-summary");
  const header = editorAction(title, "编辑设置", () => form);
  const list = h("dl", "settings-summary-list");
  for (const [label, value] of entries) {
    const row = h("div");
    row.append(h("dt", "", label), h("dd", "", String(value || "未设置")));
    list.append(row);
  }
  panel.append(header, list);
  return panel;
}

function val(form, name) {
  const node = form.elements.namedItem(name);
  return node ? String(node.value).trim() : "";
}

/** 删掉就找不回来的操作先问一句，避免误点。 */
function confirmAction(title, detail, actionLabel = "确认删除") {
  return new Promise((resolve) => {
    const mask = h("div", "modal confirm-mask");
    const panel = h("div", "panel confirm-panel");
    panel.append(h("h3", "", title));
    if (detail) panel.append(h("p", "muted", detail));
    const row = h("div", "row confirm-actions");
    const cancel = h("button", "btn-ghost", actionLabel === "确认删除" ? "先不删" : "取消");
    cancel.type = "button";
    const sure = h("button", actionLabel === "确认删除" ? "btn danger-fill" : "btn", actionLabel);
    sure.type = "button";
    const done = (value) => {
      mask.remove();
      document.removeEventListener("keydown", onKey);
      resolve(value);
    };
    const onKey = (event) => {
      if (event.key === "Escape") done(false);
      if (event.key === "Tab") {
        event.preventDefault();
        (document.activeElement === cancel ? sure : cancel).focus();
      }
    };
    cancel.addEventListener("click", () => done(false));
    sure.addEventListener("click", () => done(true));
    mask.addEventListener("click", (event) => {
      if (event.target === mask) done(false);
    });
    document.addEventListener("keydown", onKey);
    row.append(cancel, sure);
    panel.append(row);
    mask.append(panel);
    panel.setAttribute("role", "dialog");
    panel.setAttribute("aria-modal", "true");
    panel.setAttribute("aria-label", title);
    document.body.append(mask);
    cancel.focus();
  });
}

function sortableRows(container, selector, kind) {
  makeSortable(container, selector, async ids => {
    try {
      if (route().name === "home") {
        const currentRows = decorationWorkspace.data[kind];
        decorationWorkspace.reorder(kind, ids);
        currentRows.forEach(row => { row.sort_order = ids.indexOf(row.id) + 1; });
        const toolbar = document.querySelector(".decoration-toolbar");
        if (toolbar) toolbar.replaceWith(decorationToolbar());
      } else {
        await liveApi(`/api/v1/b/sort/${kind}`, {method: "POST", body: JSON.stringify({ordered_ids: ids})});
      }
      container.querySelectorAll(".label-rank").forEach((cell, index) => {
        for (const node of [...cell.childNodes]) if (node.nodeType === Node.TEXT_NODE) node.remove();
        cell.append(document.createTextNode(String(index + 1).padStart(2, "0")));
      });
    } catch (error) { toast(error.message, "bad"); throw error; }
  });
}

const MENU = [
  ["dashboard", "经营概览"],
  ["products", "商品管理"],
  ["categories", "分类标签"],
  ["tags", "商品标签"],
  ["coupons", "优惠券管理"],
  ["orders", "订单管理"],
  ["home", "首页装修"],
  ["shop", "店铺设置"],
];

async function render() {
  const version = ++renderVersion;
  const root = document.querySelector("#app");
  // 弹窗挂在 body 上，路由切换时不会跟着 #app 一起清掉，先手动收走，
  // 不然一层遮罩会一直挡着后台
  document.querySelectorAll("body > .modal").forEach((node) => node.remove());
  root.replaceChildren(h("div", "panel admin-loading", "正在加载工作台…"));
  if (!loggedIn()) {
    root.replaceChildren(loginView());
    return;
  }
  if (!me) {
    try {
      me = await api("/api/v1/auth/me");
    } catch {
      sessionStorage.removeItem("token_b");
      if (version === renderVersion) root.replaceChildren(loginView());
      return;
    }
  }
  if (location.pathname === "/login" || location.pathname === "/login/") {
    history.replaceState(null, "", `/b.html${location.search}${location.hash}`);
  }
  if (!shopInfo) {
    try {
      shopInfo = await api("/api/v1/b/shop");
    } catch {
      shopInfo = null;
    }
  }
  if (shopInfo) {
    applyTheme(shopInfo.theme_color);
    applyStorefrontSettings(shopInfo);
    document.body.classList.toggle("tinted", shopInfo.strip_tint !== false);
  }
  // 先把页面内容备好，再搭外壳：页面里改了店铺信息（店名、主题色），
  // 顶栏这一次就能用上新值，不会慢一拍
  const main = h("main", "main");
  main.classList.add(["products", "orders"].includes(route().name) ? "workspace-wide" : "workspace-compact");
  try {
    main.append(await mainView());
  } catch (error) {
    const failure = h("div", "panel stack");
    failure.append(h("h2", "panel-title", "页面暂时无法加载"), h("p", "muted", error.message));
    const retry = h("button", "btn-ghost", "重新加载");
    retry.addEventListener("click", render);
    failure.append(retry);
    main.append(failure);
  }
  if (version !== renderVersion) return;
  const frame = h("div", "admin");
  frame.append(topBar());
  const body = h("div", "admin-body");
  body.append(sidebar(), main);
  frame.append(body);
  root.replaceChildren(frame);
  frame.append(merchantAssistantToggle());
  if (merchantChatOpen) frame.append(merchantAssistant());
}

function topBar() {
  const bar = h("header", "admin-top");
  const logo = h("div", "logo");
  const mark = shopInfo?.logo_url ? document.createElement("img") : h("span", "", shopInfo?.name?.slice(0, 1) || "店");
  if (shopInfo?.logo_url) { mark.src = shopInfo.logo_url; mark.alt = shopInfo.name; mark.className = "admin-brand-image"; }
  logo.append(mark, document.createTextNode(shopInfo ? shopInfo.name : "商家后台"));
  bar.append(logo, h("span", "env", storefrontSettings(shopInfo).merchant_title));
  bar.append(h("div", "spacer"));
  const user = h("div", "user");
  const preview = h("a", "link", "查看买家端 ↗");
  preview.href = shopInfo ? `/${shopInfo.share_path.replace(/^\//, "")}` : "/c.html?code=nanzhi";
  preview.target = "_blank";
  preview.style.color = "#ff8f1f";
  user.append(accountMenu(), preview);
  bar.append(user);
  return bar;
}

function leaveMerchantAccount(switching = false) {
  switchingAccount = switching;
  sessionStorage.removeItem("token_b");
  me = null; shopInfo = null; decorationWorkspace = null;
  merchantSession = ""; merchantMessages = []; merchantChatOpen = false;
  render();
}

function accountMenu() {
  const menu = h("details", "account-menu");
  const trigger = h("summary", "account-trigger", me?.nickname || me?.username || "我的账号");
  trigger.setAttribute("aria-label", "账号菜单");
  trigger.append(h("span", "account-chevron"));
  const list = h("div", "account-menu-panel");
  list.append(h("strong", "", me?.nickname || me?.username), h("small", "", `账号：${me?.username || ""}`));
  [["用户信息", () => accountDialog(false)], ["切换账号", () => leaveMerchantAccount(true)], ["退出登录", leaveMerchantAccount], ["注销账号", () => accountDialog(true)]].forEach(([label, action]) => {
    const button = h("button", label === "注销账号" ? "account-danger" : "", label);
    button.type = "button";
    button.setAttribute("aria-label", label);
    button.addEventListener("click", () => { menu.open = false; action(); });
    list.append(button);
  });
  menu.append(trigger, list);
  return menu;
}

function accountDialog(closing) {
  const mask = h("div", "modal account-mask");
  const form = h("form", "panel stack account-panel");
  form.setAttribute("role", "dialog"); form.setAttribute("aria-modal", "true");
  form.setAttribute("aria-label", closing ? "注销账号" : "用户信息");
  form.append(h("h2", "panel-title", closing ? "注销账号" : "用户信息"));
  form.append(h("p", "muted", `登录账号：${me.username} · 商家账号`));
  if (closing) {
    form.append(h("p", "account-close-note", "注销后将无法登录，店铺会关闭。交易记录会保留；请先处理完所有未完成订单。此操作不可自行撤销。"));
    form.append(field("当前密码", "password", "", false, "password"), field("请输入“注销账号”确认", "confirmation", ""));
    form.querySelector('[name="password"]').autocomplete = "current-password";
  } else {
    form.append(field("昵称", "nickname", me.nickname));
    form.querySelector('[name="nickname"]').maxLength = 32;
    form.append(h("p", "muted", `所属店铺：${shopInfo?.name || "—"}。店铺名称与 Logo 可在“店铺设置”修改。`));
  }
  const error = h("p", "account-error"); error.setAttribute("role", "alert");
  const actions = h("div", "row account-actions");
  const cancel = h("button", "btn-ghost", "取消"); cancel.type = "button";
  const submit = h("button", closing ? "btn danger-fill" : "btn", closing ? "确认注销" : "保存信息"); submit.type = "submit";
  let busy = false;
  const close = () => { if (!busy) { mask.remove(); document.removeEventListener("keydown", onKey); } };
  const onKey = event => { if (event.key === "Escape") close(); };
  document.addEventListener("keydown", onKey);
  cancel.addEventListener("click", close);
  mask.addEventListener("click", event => { if (event.target === mask) close(); });
  form.addEventListener("submit", async event => {
    event.preventDefault(); if (busy) return;
    error.textContent = "";
    if (closing && (val(form, "confirmation") !== "注销账号" || !val(form, "password"))) { error.textContent = "请填写密码，并输入“注销账号”确认"; return; }
    if (closing && !(await confirmAction("确认注销当前账号？", "店铺将关闭，当前账号无法再次登录。请确认这是你要注销的账号。", "确认注销"))) return;
    busy = true; submit.disabled = true; cancel.disabled = true;
    try {
      if (closing) {
        await api("/api/v1/auth/me/close", {method:"POST", body:JSON.stringify({password:form.elements.namedItem("password").value, confirmation:val(form,"confirmation")})});
        busy = false; close(); leaveMerchantAccount();
      } else {
        me = await api("/api/v1/auth/me", {method:"PATCH", body:JSON.stringify({nickname:val(form,"nickname")})});
        busy = false; close(); render();
      }
    } catch (err) { error.textContent = err.message; }
    finally { busy = false; submit.disabled = false; cancel.disabled = false; }
  });
  actions.append(cancel, submit); form.append(error, actions); mask.append(form); document.body.append(mask);
  form.querySelector("input")?.focus();
}

document.addEventListener("click", event => {
  document.querySelectorAll(".account-menu[open]").forEach(menu => { if (!menu.contains(event.target)) menu.open = false; });
});
document.addEventListener("keydown", event => {
  if (event.key === "Escape") document.querySelectorAll(".account-menu[open]").forEach(menu => { menu.open = false; menu.querySelector("summary").focus(); });
});

function loginView() {
  if (location.pathname !== "/login") {
    history.replaceState(null, "", `/login${location.search}${location.hash}`);
  }
  const page = h("div", "auth-page");
  page.append(StoreAuth.createForm({role: "merchant", onSuccess: (data) => {
    me = data.user;
    switchingAccount = false;
    render();
  }}));
  return page;
}

function sidebar() {
  const side = h("aside", "side");
  side.append(h("div", "side-brand", "店铺管理"));
  MENU.forEach(([name, label]) => {
    const link = h("a", route().name === name ? "on" : "");
    const paths = {
      dashboard: "M4 20h16M7 16v-5m5 5V4m5 12V8",
      products: "m3 7 9-4 9 4-9 4-9-4Zm0 0v10l9 4 9-4V7M12 11v10M7.5 5l9 4",
      categories: "M3 3h7v7H3V3Zm11 0h7v7h-7V3ZM3 14h7v7H3v-7Zm11 0h7v7h-7v-7Z",
      tags: "M3 3h8l10 10-8 8L3 11V3Zm4 4h.01",
      coupons: "M3 5h18v5a2 2 0 0 0 0 4v5H3v-5a2 2 0 0 0 0-4V5Zm12 0v3m0 3v2m0 3v3",
      orders: "M6 3h12v18l-3-2-3 2-3-2-3 2V3Zm3 5h6m-6 4h6",
      home: "M3 3h18v18H3V3Zm0 6h18M9 9v12",
      shop: "M4 10v11h16V10M3 10l2-7h14l2 7M3 10a3 3 0 0 0 6 0 3 3 0 0 0 6 0 3 3 0 0 0 6 0M9 21v-7h6v7",
    };
    const icon = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    icon.setAttribute("viewBox", "0 0 24 24");
    icon.setAttribute("class", "side-nav-icon");
    icon.setAttribute("aria-hidden", "true");
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", paths[name]);
    icon.append(path);
    link.append(icon, h("span", "", label));
    link.href = `#/${name}`;
    side.append(link);
  });
  side.append(h("div", "spacer"));
  return side;
}

async function mainView() {
  const current = route();
  if (current.name === "assistant") {
    history.replaceState(null, "", "#/dashboard");
    current.name = "dashboard";
  }
  if (current.name === "products") return current.id ? productEditor(current.id) : productList();
  if (current.name === "categories") return categoriesAdmin();
  if (current.name === "tags") return tagsAdmin();
  if (current.name === "coupons") return couponsAdmin();
  if (current.name === "orders") return orderList(current.id);
  if (current.name === "home") return homeAdmin(current.id);
  if (current.name === "shop") return shopForm();
  return dashboard();
}

let merchantSession = "";
let merchantMessages = [];
let merchantChatUser = "";
let merchantChatOpen = false;
let merchantChatBusy = false;

function merchantAssistantToggle() {
  const button = h("button", "merchant-chat-fab", merchantChatOpen ? "×" : "💬");
  button.title = "智能助手";
  button.setAttribute("aria-label", merchantChatOpen ? "收起智能助手" : "打开智能助手");
  button.setAttribute("aria-expanded", String(merchantChatOpen));
  button.addEventListener("click", () => {
    merchantChatOpen = !merchantChatOpen;
    const frame = button.parentElement;
    frame.querySelector(".merchant-assistant")?.remove();
    button.replaceWith(merchantAssistantToggle());
    if (merchantChatOpen) frame.append(merchantAssistant());
  });
  return button;
}

function merchantAssistant() {
  if (merchantChatUser !== sessionStorage.getItem("token_b")) {
    merchantChatUser = sessionStorage.getItem("token_b");
    merchantSession = "";
    merchantMessages = [];
  }
  const panel = h("aside", "panel merchant-assistant");
  panel.setAttribute("aria-label", "智能运营助手");
  const header = h("header", "merchant-chat-header");
  const close = h("button", "btn-ghost", "×");
  close.setAttribute("aria-label", "关闭智能助手");
  close.addEventListener("click", () => {
    merchantChatOpen = false;
    panel.parentElement.querySelector(".merchant-chat-fab").replaceWith(merchantAssistantToggle());
    panel.remove();
  });
  header.append(h("h2", "", `${storeAssistantName(shopInfo)} · 智能运营助手`), close);
  panel.append(header, h("p", "muted", "商品 · 库存 · 订单 · 经营概览"));
  const log = h("div", "merchant-chat-log");
  const append = (data) => {
    const question = data.text.startsWith("你：");
    const content = h("div", question ? "merchant-question" : "merchant-answer", data.text);
    if (!question) renderAssistantMessage(content, data.text);
    log.append(content);
    (data.products || []).forEach((product) => {
      const link = h("a", "btn-ghost", `${product.name} · ${money(product.price_from)}起`);
      link.href = `#/products/${product.id}`;
      log.append(link);
    });
  };
  merchantMessages.forEach(append);
  const welcome = h("p", "muted", "从一个问题开始：查看本店经营概览，找出需要补货的 SKU，或追踪订单状态。");
  if (!merchantMessages.length) log.append(welcome);
  const form = document.createElement("form");
  const input = document.createElement("input");
  input.placeholder = "例如：经营概览 / 库存预警 / 本店订单";
  input.maxLength = 1000;
  input.required = true;
  const send = h("button", "btn", "发送");
  const reset = h("button", "btn-ghost", "新对话");
  send.disabled = reset.disabled = merchantChatBusy;
  reset.type = "button";
  reset.addEventListener("click", () => { merchantSession = ""; merchantMessages = []; log.replaceChildren(welcome); });
  form.append(input, send, reset);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const message = input.value.trim();
    if (!message || merchantChatBusy) return;
    merchantChatBusy = true;
    welcome.remove();
    const question = { text: `你：${message}` };
    merchantMessages.push(question);
    append(question);
    send.disabled = reset.disabled = true;
    const waiting = h("div", "muted", assistantWaitingText(shopInfo));
    let previewShown = false;
    log.append(waiting);
    try {
      const data = await streamChat("/api/v1/b/chat/stream", "token_b",
        { message, session_id: merchantSession || undefined }, () => {
          if (!previewShown) waiting.textContent = assistantWaitingText(shopInfo);
        }, event => {
          previewShown = true;
          renderAssistantMessage(waiting, `${event.answer}\n\n${assistantWaitingText(shopInfo)}`);
          log.scrollTop = log.scrollHeight;
        });
      merchantSession = data.session_id;
      const reply = { text: `${data.answer}${knowledgeSourceText(data)}\n${data.mode === "fallback" ? "规则查询 · " : ""}${data.notices.join("；")}`, products: data.products };
      merchantMessages.push(reply);
      append(reply);
      input.value = "";
    } catch (error) {
      append({ text: error.message + "，可再次发送重试。" });
    } finally {
      merchantChatBusy = false;
      waiting.remove();
      send.disabled = reset.disabled = false;
      log.scrollTop = log.scrollHeight;
      const visiblePanel = document.querySelector(".merchant-assistant");
      if (visiblePanel && visiblePanel !== panel) visiblePanel.replaceWith(merchantAssistant());
    }
  });
  panel.append(log, form);
  return panel;
}

/** 商家自己传图，成功返回可直接用的路径。 */
async function uploadImage(file) {
  // 后端也会校验一遍，这里先拦一次，省得白传一个 5MB 的文件
  const allowed = [".jpg", ".jpeg", ".png", ".webp", ".gif"];
  const suffix = `.${(file.name.split(".").pop() || "").toLowerCase()}`;
  if (!allowed.includes(suffix)) throw new Error("只支持 jpg / png / webp / gif");
  if (file.size > 5 * 1024 * 1024) throw new Error("图片不要超过 5MB");
  const form = new FormData();
  form.append("file", file);
  const token = sessionStorage.getItem("token_b");
  const response = await fetch("/api/v1/b/uploads", {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(detailOf(data));
  return data.url;
}

/** 图片选择：可以传本地文件，也可以直接填已有路径。 */
function imageField(label, name, value) {
  const wrap = h("label", "field");
  // 表格里用的时候不需要上面那行标签，传空字符串就跳过
  if (label) wrap.append(h("span", "", label));
  const row = h("div", "row");
  const input = document.createElement("input");
  input.name = name;
  input.value = value || "";
  input.placeholder = "/covers/xxx.jpg";
  input.style.flex = "1";
  const pick = h("button", "btn-ghost btn-mini", "上传图片");
  pick.type = "button";
  const file = document.createElement("input");
  file.type = "file";
  file.accept = "image/*";
  file.style.display = "none";
  pick.addEventListener("click", () => file.click());
  file.addEventListener("change", async () => {
    if (!file.files?.length) return;
    pick.disabled = true;
    pick.textContent = "上传中…";
    try {
      input.value = await uploadImage(file.files[0]);
      refresh();
      toast("图片已上传", "ok");
    } catch (error) {
      toast(error.message, "bad");
    }
    pick.disabled = false;
    pick.textContent = "上传图片";
  });
  const preview = document.createElement("img");
  preview.alt = "";
  preview.style.width = "56px";
  preview.style.height = "56px";
  preview.style.objectFit = "cover";
  preview.style.borderRadius = "6px";
  preview.style.background = "#f7f7f7";
  const refresh = () => {
    // 没填路径时给一个空图，别让预览挂着别的商品的图
    preview.src = input.value || "";
  };
  input.addEventListener("input", refresh);
  refresh();
  row.append(preview, input, pick, file);
  wrap.append(row);
  return wrap;
}

/* ---------------- 首页装修 ---------------- */
function decorationToolbar() {
  const workspace = decorationWorkspace;
  const bar = h("div", "decoration-toolbar");
  const status = h("div");
  status.append(h("strong", "", workspace.conflict ? "草稿与线上版本冲突" : workspace.dirty ? "有未保存的装修修改" : "当前为已保存版本"));
  status.append(h("p", "muted", "新增、编辑、隐藏、删除与拖拽只修改草稿；预览不发布，保存后买家端才生效。"));
  const actions = h("div", "row");
  const reset = h("button", "btn-ghost", "放弃草稿");
  reset.disabled = !workspace.dirty;
  reset.addEventListener("click", async () => {
    if (!(await confirmAction("放弃所有装修草稿？", "会重新加载线上版本，尚未保存的修改将丢失。", "确认放弃"))) return;
    sessionStorage.removeItem(workspace.key);
    decorationWorkspace = null;
    render();
  });
  const preview = h("button", "btn-ghost", "预览");
  preview.addEventListener("click", async () => {
    if (preview.disabled) return;
    preview.disabled = true;
    try { await previewDecoration(workspace.data); }
    catch (error) { toast(error.message, "bad"); }
    finally { preview.disabled = false; }
  });
  const save = h("button", "btn decoration-save", "保存并生效");
  save.disabled = !workspace.dirty || workspace.conflict || decorationSaving;
  save.addEventListener("click", () => saveDecoration(workspace.data));
  actions.append(reset, preview, save);
  bar.append(status, actions);
  return bar;
}

async function saveDecoration(candidate) {
  if (decorationSaving) return;
  decorationSaving = true;
  document.querySelectorAll(".decoration-save").forEach(button => { button.disabled = true; });
  try {
    const snapshot = await liveApi("/api/v1/b/decoration", {method: "PUT", body: JSON.stringify(decorationPayload(candidate))});
    sessionStorage.removeItem(decorationWorkspace.key);
    shopInfo = await liveApi("/api/v1/b/shop");
    decorationWorkspace = new DecorationWorkspace(snapshot, shopInfo, sessionStorage, me.id);
    toast("装修已保存，买家端刷新后可见", "ok");
    render();
  } catch (error) { toast(error.message, "bad"); }
  finally {
    decorationSaving = false;
    document.querySelectorAll(".decoration-save").forEach(button => { button.disabled = false; });
  }
}

async function previewDecoration(candidate) {
  const snapshot = structuredClone(candidate);
  const version = renderVersion;
  const trigger = document.activeElement;
  const data = await liveApi("/api/v1/b/decoration/preview", {method: "POST", body: JSON.stringify(decorationPayload(snapshot))});
  if (version !== renderVersion) return;
  const mask = h("div", "modal decoration-preview-mask");
  const panel = h("section", "panel decoration-preview-panel");
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-modal", "true");
  panel.setAttribute("aria-label", "未保存装修预览");
  const header = h("div", "decoration-preview-heading");
  header.append(h("strong", "", "未保存预览 · 仅当前商家可见，不可下单"));
  const actions = h("div", "row");
  const save = h("button", "btn decoration-save", "保存并生效");
  save.disabled = decorationWorkspace.conflict ||
    JSON.stringify(decorationPayload(snapshot)) === JSON.stringify(decorationWorkspace.baseline);
  save.addEventListener("click", () => saveDecoration(snapshot));
  const close = h("button", "btn-ghost", "返回编辑");
  const dismiss = () => { mask.remove(); if (trigger?.isConnected) trigger.focus(); };
  close.addEventListener("click", dismiss);
  actions.append(save, close);
  header.append(actions);
  const frame = document.createElement("iframe");
  const nonce = crypto.randomUUID();
  frame.title = "装修草稿买家端预览";
  frame.tabIndex = -1;
  frame.src = `/c.html?code=${encodeURIComponent(decorationWorkspace.shop.share_code)}&preview=${nonce}`;
  frame.addEventListener("load", () => frame.contentWindow.postMessage({type: "decoration-preview", nonce, data}, location.origin));
  panel.append(header, frame);
  mask.append(panel);
  mask.addEventListener("keydown", event => {
    if (event.key === "Escape") dismiss();
    if (event.key === "Tab") {
      event.preventDefault();
      (document.activeElement === close && !save.disabled ? save : close).focus();
    }
  });
  document.body.append(mask);
  close.focus();
}

function draftMessage(message) {
  return route().name === "home" ? "草稿已更新，尚未发布" : message;
}

async function homeAdmin(tab) {
  const actor = `${me.id}:${shopInfo.id}`;
  if (!decorationWorkspace || decorationActor !== actor) {
    const [snapshot, shop] = await Promise.all([liveApi("/api/v1/b/decoration"), liveApi("/api/v1/b/shop")]);
    decorationWorkspace = new DecorationWorkspace(snapshot, shop, sessionStorage, me.id);
    decorationActor = actor;
  }
  const current = tab || "banners";
  const box = h("div");
  box.append(h("h1", "page-title", "首页装修"));
  box.append(h("p", "page-sub", "买家端首页轮播、商品栏目和反馈展示在这里配置，保存后刷新买家端可见"));
  box.append(decorationToolbar());

  const tabs = h("div", "tabs");
  [["banners", "轮播图"], ["sections", "商品栏目"], ["testimonials", "反馈展示"], ["appearance", "首页样式"]].forEach(
    ([value, label]) => {
      const button = h("button", value === current ? "on" : "", label);
      button.addEventListener("click", () => go(`#/home/${value}`));
      tabs.append(button);
    }
  );
  box.append(tabs);

  if (current === "sections") box.append(await sectionsAdmin());
  else if (current === "testimonials") box.append(await testimonialsAdmin());
  else if (current === "appearance") box.append(await appearanceAdmin());
  else box.append(await bannersAdmin());
  return box;
}

/** 首页样式：轮播高度和顶栏浅色底，都是买家端一眼能看到的。 */
async function appearanceAdmin() {
  const shop = await api("/api/v1/b/shop");
  shopInfo = shop;
  const box = h("div");

  const panel = h("form", "panel stack");
  panel.append(h("h2", "panel-title", "首页样式"));
  panel.append(h("p", "muted", "这里改的是买家端首页的外观，保存后刷新买家端就能看到"));

  const grid = h("div", "form-grid");
  const heightWrap = h("label", "field");
  heightWrap.append(h("span", "", "轮播主视觉高度"));
  const height = document.createElement("select");
  [["460", "矮（460px，适合横图）"], ["560", "标准（560px）"], ["640", "高（640px，推荐）"], ["720", "很高（720px）"]].forEach(
    ([value, label]) => height.append(new Option(label, value))
  );
  height.value = String(shop.hero_height || 640);
  if (!height.value) height.value = "640";
  heightWrap.append(height);
  grid.append(heightWrap);

  const tintWrap = h("label", "field");
  tintWrap.append(h("span", "", "顶部一行底色"));
  const tint = document.createElement("select");
  tint.append(new Option("主题色浅底（推荐）", "on"), new Option("仅背景底色，不叠加渐变", "off"));
  tint.value = shop.strip_tint === false ? "off" : "on";
  tintWrap.append(tint);
  grid.append(tintWrap);
  panel.append(grid);

  const storefront = storefrontSettings(shop);
  const configurable = Boolean(shop.storefront);
  panel.append(h("h2", "panel-title", "C端全店外观与内容"));
  panel.append(h("p", "muted", configurable ? "设置会同步到商品页、购物车和结算。运费数值影响真实下单；保障文案请与规则保持一致。" : "当前后端尚未加载全店配置接口，新配置暂不可编辑，需正常重启后端。"));
  const presentationGrid = h("div", "form-grid");
  const presentationInputs = {};
  const controls = [
    ["background_color", "C端背景底色", "color"], ["surface_color", "卡片背景色", "color"],
    ["text_color", "主要文字色", "color"], ["muted_color", "辅助文字色", "color"],
    ["product_image_ratio", "商品图比例", [["1/1", "正方形"], ["4/5", "竖向4:5"], ["3/4", "竖向3:4"]]],
    ["rail_columns", "桌面每行商品数", [["3", "3张"], ["3.5", "3张半"], ["4", "4张"]]],
    ["hero_enabled", "首页轮播", [["true", "展示"], ["false", "隐藏"]]],
    ["promises_enabled", "首页及详情保障条", [["true", "展示"], ["false", "隐藏"]]],
    ["assistant_enabled", "C端助手入口", [["true", "展示"], ["false", "隐藏"]]],
    ["merchant_title", "后台顶栏说明文字", "text"],
    ["brand_slogan", "入口页品牌短语", "text"],
    ["portal_title", "入口页主标题", "text"],
    ["portal_description", "入口页介绍文字", "text"],
    ["product_subtitle", "商品标题下说明", "text"], ["footer_about", "页脚店铺简介", "text"],
    ["footer_service", "页脚联系说明", "text"], ["dispatch_text", "发货说明", "text"],
    ["return_text", "退换货说明", "text"], ["free_shipping_yuan", "包邮门槛（元，0表示全店包邮）", "number"],
    ["base_freight_yuan", "未满门槛运费（元）", "number"],
    ["assistant_welcome", "助手欢迎语（自动带昵称前缀）", "text"],
    ["testimonial_title", "首页反馈区标题", "text"], ["testimonial_subtitle", "首页反馈区说明", "text"],
  ];
  controls.forEach(([key, label, type]) => {
    const wrap = h("label", "field");
    wrap.append(h("span", "", label));
    const input = document.createElement(Array.isArray(type) ? "select" : "input");
    if (Array.isArray(type)) type.forEach(([value, text]) => input.append(new Option(text, value)));
    else { input.type = type; if (type === "number") { input.min = "0"; input.step = "0.01"; } }
    input.value = String(storefront[key]);
    input.disabled = !configurable;
    presentationInputs[key] = input;
    wrap.append(input);
    presentationGrid.append(wrap);
  });
  for (const [key, label, value] of [
    ["quick_questions", "助手快捷问题（每行一条，最多6条，留空隐藏）", storefront.quick_questions.join("\n")],
    ["detail_sections", "商品详情通用说明（每行 标题：内容，最多6段，留空不展示）", storefront.detail_sections.map(item => `${item.title}：${item.body}`).join("\n")],
  ]) {
    const wrap = h("label", "field full");
    wrap.append(h("span", "", label));
    const input = document.createElement("textarea");
    input.rows = 4; input.value = value; input.disabled = !configurable;
    presentationInputs[key] = input;
    wrap.append(input); presentationGrid.append(wrap);
  }
  panel.append(presentationGrid);

  panel.append(
    h(
      "p",
      "muted",
      "顶栏浅色底由「店铺设置」里的主题色自动调出来；轮播图左右两侧的模糊渐变跟着图片走，不用另外配。"
    )
  );

  // 首页最下面那条售后保障，改这里买家端立刻生效
  panel.append(h("h2", "panel-title", "售后保障条"));
  panel.append(h("p", "muted", "买家端首页最下面那一条，最多 6 项；只填标题也行"));
  const promiseRows = h("div", "promise-rows");
  const rows = (shop.promises || []).map((row) => ({ ...row }));
  const paint = () => {
    promiseRows.replaceChildren();
    rows.forEach((row, index) => {
      const line = h("div", "promise-row");
      const title = document.createElement("input");
      title.value = row.title;
      title.placeholder = "标题";
      title.maxLength = 16;
      title.addEventListener("input", () => (row.title = title.value));
      const sub = document.createElement("input");
      sub.value = row.sub;
      sub.placeholder = "一行说明";
      sub.maxLength = 40;
      sub.addEventListener("input", () => (row.sub = sub.value));
      const remove = h("button", "btn-ghost btn-mini", "删除");
      remove.type = "button";
      remove.addEventListener("click", () => {
        rows.splice(index, 1);
        paint();
      });
      line.append(title, sub, remove);
      promiseRows.append(line);
    });
    if (!rows.length) promiseRows.append(h("p", "muted", "未填写时恢复默认保障内容；如需隐藏，请关闭上方保障条开关。"));
  };
  paint();
  const addPromise = h("button", "btn-ghost btn-mini", "加一条");
  addPromise.type = "button";
  addPromise.addEventListener("click", () => {
    if (rows.length >= 6) return toast("最多 6 条", "bad");
    rows.push({ title: "", sub: "" });
    paint();
  });
  panel.append(promiseRows, addPromise);

  const error = h("p", "muted", "");
  const submit = h("button", "btn", "保存样式");
  const readAppearance = () => {
    const settings = { ...storefront };
    if (configurable) {
      controls.forEach(([key, , type]) => {
        settings[key] = typeof storefront[key] === "boolean" ? presentationInputs[key].value === "true"
          : type === "number" ? Number(presentationInputs[key].value) : presentationInputs[key].value.trim();
      });
      settings.quick_questions = presentationInputs.quick_questions.value.split("\n").map(item => item.trim()).filter(Boolean);
      settings.detail_sections = presentationInputs.detail_sections.value.split("\n").map(item => item.trim()).filter(Boolean).map(item => {
        const match = item.match(/^(.+?)[：:](.+)$/);
        if (!match) throw new Error("通用说明请按“标题：内容”填写");
        return { title: match[1].trim(), body: match[2].trim() };
      });
    }

    return { hero_height: Number(height.value), ...(configurable ? {storefront: settings} : {}), strip_tint: tint.value === "on",
      promises: rows.filter(row => row.title.trim()).map(row => ({title: row.title.trim(), sub: row.sub.trim()})) };
  };
  panel.previewCandidate = () => decorationWorkspace.candidate("appearance", readAppearance());
  submit.type = "submit";
  panel.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (submit.disabled) return;
    submit.disabled = true;
    try {
      shopInfo = await api("/api/v1/b/shop", { method: "PATCH", body: JSON.stringify(readAppearance()) });
      toast(draftMessage("样式已保存"), "ok");
      render();
    } catch (err) {
      error.textContent = err.message;
    } finally {
      submit.disabled = false;
    }
  });
  panel.append(error, submit);
  box.append(settingsSummary(panel, "外观与内容配置", [
    ["首页轮播", storefront.hero_enabled ? `展示 · ${shop.hero_height || 640}px` : "已隐藏"],
    ["商品展示", `${storefront.rail_columns}列 · 图片${storefront.product_image_ratio}`],
    ["背景 / 卡片", `${storefront.background_color} / ${storefront.surface_color}`],
    ["文字 / 辅助文字", `${storefront.text_color} / ${storefront.muted_color}`],
    ["运费规则", storeShippingText(shop)],
    ["发货与退换", `${storefront.dispatch_text}；${storefront.return_text}`],
    ["店内助手", storefront.assistant_enabled ? `已开启 · ${storefront.quick_questions.length}条快捷问题` : "已隐藏"],
    ["通用详情说明", `${storefront.detail_sections.length}段`],
    ["售后保障条", storefront.promises_enabled ? `展示 · ${rows.length}项` : "已隐藏"],
  ]));
  return box;
}

async function bannersAdmin() {
  const box = h("div");
  const [banners, products, sections] = await Promise.all([
    api("/api/v1/b/banners"),
    api("/api/v1/b/products"),
    api("/api/v1/b/sections"),
  ]);
  const onSale = products.filter((product) => product.status === "on");

  const list = h("div", "panel");
  if (!banners.length) list.append(h("p", "muted", "还没有轮播图，点击右上角新增"));
  const items = h("div", "sortable-rows");
  banners.forEach((banner, index) => items.append(bannerRow(banner, banners, index, onSale, sections)));
  list.append(items);
  sortableRows(items, ".banner-row", "banners");
  list.append(h("p", "muted", "拖动左侧手柄调整顺序，预览确认后点击保存并生效。"));

  list.prepend(editorAction(`轮播图（${banners.length}）`, "＋ 新增轮播图", () => bannerForm(onSale, sections)));
  box.append(list);
  return box;
}

function bannerRow(banner, banners, index, products, sections) {
  const row = h("div", "banner-row");
  row.dataset.sortId = banner.id;
  row.dataset.sortName = banner.title || "轮播图";
  const image = document.createElement("img");
  image.src = banner.image_url;
  image.alt = banner.title;
  const words = h("div");
  words.style.flex = "1";
  words.append(h("div", "", banner.title || "（没有标题）"));
  const target =
    banner.link_type === "product"
      ? products.find((item) => String(item.id) === banner.link_value)?.name || "商品已下架"
      : banner.link_type === "section"
        ? sections.find((item) => String(item.id) === banner.link_value)?.title || "栏目已删除"
        : "不跳转";
  words.append(h("div", "muted", `跳转：${target}`));
  const state = h("span", `pill ${banner.enabled ? "on" : "off"}`, banner.enabled ? "展示中" : "已隐藏");

  const ops = h("div", "ops");
  const toggle = h("button", "", banner.enabled ? "隐藏" : "展示");
  toggle.addEventListener("click", async () => {
    await api(`/api/v1/b/banners/${banner.id}`, {
      method: "PATCH",
      body: JSON.stringify({ enabled: !banner.enabled }),
    });
    toast(draftMessage(banner.enabled ? "已隐藏" : "已展示"), "ok");
    render();
  });
  const remove = h("button", "danger", "删除");
  remove.addEventListener("click", async () => {
    const ok = await confirmAction("删掉这张轮播图？", banner.title || "（没有标题）");
    if (!ok) return;
    try {
      await api(`/api/v1/b/banners/${banner.id}`, { method: "DELETE" });
      toast(draftMessage("已删除"), "ok");
      render();
    } catch (error) {
      toast(error.message, "bad");
    }
  });
  const edit = h("button", "", "编辑");
  edit.addEventListener("click", () => openFormDialog(bannerForm(products, sections, banner), "编辑轮播图", edit));
  ops.append(edit, toggle, remove);
  row.append(image, words, state, ops);
  return row;
}

function bannerForm(products, sections, banner = null) {
  const panel = h("form", "panel stack");
  panel.append(h("h2", "panel-title", banner ? "编辑轮播图" : "新增轮播图"));
  const grid = h("div", "form-grid");
  grid.append(imageField("横屏大图", "image_url", banner?.image_url || ""));
  grid.append(field("标题（大字）", "title", banner?.title || ""));
  grid.append(field("副标题", "subtitle", banner?.subtitle || ""));
  panel.append(grid);

  const linkRow = h("div", "form-grid");
  const typeWrap = h("label", "field");
  typeWrap.append(h("span", "", "点击跳转"));
  const type = document.createElement("select");
  type.name = "link_type";
  [["none", "不跳转，只展示"], ["product", "跳到商品详情"], ["section", "跳到某个栏目"]].forEach(([value, label]) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    type.append(option);
  });
  typeWrap.append(type);
  type.value = banner?.link_type || "none";

  const valueWrap = h("label", "field");
  valueWrap.append(h("span", "", "跳转目标"));
  const target = document.createElement("select");
  target.name = "link_value";
  const fill = () => {
    target.replaceChildren();
    if (type.value === "product") {
      if (!products.length) target.append(new Option("还没有在售商品", ""));
      products.forEach((product) => target.append(new Option(product.name, String(product.id))));
    } else if (type.value === "section") {
      if (!sections.length) target.append(new Option("还没有栏目", ""));
      sections.forEach((section) => target.append(new Option(section.title, String(section.id))));
    } else {
      target.append(new Option("不需要选", ""));
    }
    if (banner?.link_value && type.value === banner.link_type &&
        ![...target.options].some(option => option.value === banner.link_value)) {
      target.append(new Option("原跳转目标（当前不在可选列表）", banner.link_value));
    }
    target.disabled = type.value === "none";
  };
  type.addEventListener("change", fill);
  fill();
  if (banner?.link_value) target.value = banner.link_value;
  valueWrap.append(target);
  linkRow.append(typeWrap, valueWrap);
  panel.append(linkRow);

  const error = h("p", "muted", "");
  const submit = h("button", "btn", banner ? "保存修改" : "添加轮播图");
  panel.previewCandidate = () => decorationWorkspace.candidate("banners", {
    image_url: val(panel, "image_url"), title: val(panel, "title"), subtitle: val(panel, "subtitle"),
    link_type: type.value, link_value: type.value === "none" ? "" : target.value,
  }, banner?.id);
  submit.type = "submit";
  panel.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (submit.disabled) return;
    submit.disabled = true;
    try {
      await api(`/api/v1/b/banners${banner ? "/" + banner.id : ""}`, {
        method: banner ? "PATCH" : "POST",
        body: JSON.stringify({
          image_url: val(panel, "image_url"),
          title: val(panel, "title"),
          subtitle: val(panel, "subtitle"),
          link_type: type.value,
          link_value: type.value === "none" ? "" : target.value,
        }),
      });
      toast(draftMessage(banner ? "轮播图已保存" : "轮播图已添加"), "ok");
      render();
    } catch (err) {
      error.textContent = err.message;
    } finally {
      submit.disabled = false;
    }
  });
  panel.append(error, submit);
  return panel;
}

async function sectionsAdmin() {
  const box = h("div");
  const [sections, products] = await Promise.all([api("/api/v1/b/sections"), api("/api/v1/b/products")]);
  const onSale = products.filter((product) => product.status === "on");

  const list = h("div", "panel");
  list.append(h("p", "muted", "拖动左侧手柄调整买家端首页的栏目顺序，保存后生效。"));
  if (!sections.length) list.append(h("p", "muted", "还没有栏目"));
  const items = h("div", "sortable-rows");
  sections.forEach((section, index) => items.append(sectionRow(section, sections, index, onSale)));
  list.append(items);
  sortableRows(items, ".sec-row", "sections");
  list.prepend(editorAction(`商品栏目（${sections.length}）`, "＋ 新增栏目", () => sectionForm(onSale)));
  box.append(list);
  return box;
}

function sectionRow(section, sections, index, products) {
  const row = h("div", "sec-row");
  row.dataset.sortId = section.id;
  row.dataset.sortName = section.title;
  const words = h("div");
  words.style.flex = "1";
  words.append(h("div", "", `${section.title}　${section.source === "sales" ? "（按销量自动）" : "（手选）"}`));
  if (section.subtitle) words.append(h("div", "muted", section.subtitle));
  words.append(
    h(
      "div",
      "muted",
      section.source === "sales"
        ? "展示销量前 6 件在售商品"
        : section.product_names.length
          ? `已选：${section.product_names.join("、")}`
          : "还没有选商品"
    )
  );
  const ops = h("div", "ops");
  const state = h("span", `pill ${section.enabled ? "on" : "off"}`, section.enabled ? "展示中" : "已隐藏");
  const toggle = h("button", "", section.enabled ? "隐藏" : "展示");
  toggle.addEventListener("click", async () => {
    await api(`/api/v1/b/sections/${section.id}`, {
      method: "PATCH",
      body: JSON.stringify({ enabled: !section.enabled }),
    });
    render();
  });
  const edit = h("button", "", "编辑");
  edit.addEventListener("click", () => sectionEditor(section, products));
  const remove = h("button", "danger", "删除");
  remove.addEventListener("click", async () => {
    const ok = await confirmAction(`删掉栏目「${section.title}」？`, "栏目里的商品不会删，只是这一行不再展示。");
    if (!ok) return;
    try {
      await api(`/api/v1/b/sections/${section.id}`, { method: "DELETE" });
      toast(draftMessage("栏目已删除"), "ok");
      render();
    } catch (error) {
      toast(error.message, "bad");
    }
  });
  ops.append(state, toggle, edit, remove);
  row.append(words, ops);
  return row;
}

function sectionEditor(section, products) {
  openFormDialog(sectionForm(products, section), "编辑商品栏目", document.activeElement);
}

function sectionForm(products, section = null) {
  const panel = h("form", "panel stack");
  panel.append(h("h2", "panel-title", section ? "编辑栏目" : "新增栏目"));
  const grid = h("div", "form-grid");
  grid.append(field("栏目标题", "title", section?.title || ""), field("副标题", "subtitle", section?.subtitle || ""));
  const sourceWrap = h("label", "field");
  sourceWrap.append(h("span", "", "商品来源"));
  const source = document.createElement("select");
  [["manual", "手选商品"], ["sales", "按销量自动取前 6"]].forEach(([value, label]) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    source.append(option);
  });
  sourceWrap.append(source);
  source.value = section?.source || "manual";
  grid.append(sourceWrap);
  panel.append(grid);

  const picked = new Set(section?.product_ids || []);
  const counter = h("p", "muted", "");
  const paintCount = () => {
    counter.textContent = `已选 ${picked.size} / 24 件（首页展示前6件，合集页展示全部）`;
  };
  const list = h("div", "pick-list");
  products.forEach((product) => {
    const label = h("label", "pick-item");
    const check = document.createElement("input");
    check.type = "checkbox";
    check.className = "check";
    check.checked = picked.has(product.id);
    check.addEventListener("change", () => {
      if (check.checked && picked.size >= 24) {
        check.checked = false;
        toast("手工栏目最多选 24 件", "bad");
        return;
      }
      if (check.checked) picked.add(product.id);
      else picked.delete(product.id);
      paintCount();
    });
    const thumb = document.createElement("img");
    thumb.src = cover(product.image_url);
    thumb.alt = product.name;
    label.append(check, thumb, h("span", "", product.name));
    list.append(label);
  });
  const hint = h("p", "muted", "手选最多24件，首页按勾选顺序展示前6件，合集页展示全部；按销量自动时无需勾选。");
  panel.append(h("div", "field-label", "手选商品"), counter, list, hint);
  const updateSource = () => { list.hidden = source.value === "sales"; counter.hidden = list.hidden; };
  source.addEventListener("change", updateSource);
  updateSource();
  paintCount();

  const error = h("p", "muted", "");
  const submit = h("button", "btn", section ? "保存修改" : "添加栏目");
  panel.previewCandidate = () => decorationWorkspace.candidate("sections", {
    title: val(panel, "title"), subtitle: val(panel, "subtitle"), source: source.value, product_ids: [...picked],
  }, section?.id);
  submit.type = "submit";
  panel.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (submit.disabled) return;
    submit.disabled = true;
    try {
      await api(`/api/v1/b/sections${section ? "/" + section.id : ""}`, {
        method: section ? "PATCH" : "POST",
        body: JSON.stringify({
          title: val(panel, "title"),
          subtitle: val(panel, "subtitle"),
          source: source.value,
          product_ids: [...picked],
        }),
      });
      toast(draftMessage(section ? "栏目已保存" : "栏目已添加"), "ok");
      render();
    } catch (err) {
      error.textContent = err.message;
    } finally {
      submit.disabled = false;
    }
  });
  panel.append(error, submit);
  return panel;
}

async function testimonialsAdmin() {
  const box = h("div");
  const rows = await api("/api/v1/b/testimonials");
  const list = h("div", "panel");
  list.append(h("p", "muted", "这些是商家维护的首页展示内容，不会修改用户真实订单评价。"));
  if (!rows.length) list.append(h("p", "muted", "还没有评价"));
  const items = h("div", "sortable-rows");
  rows.forEach((row, index) => {
    const item = h("div", "quote-row");
    item.dataset.sortId = row.id;
    item.dataset.sortName = row.nickname;
    const words = h("div");
    words.style.flex = "1";
    const who = h("div", "row");
    who.append(h("b", "", row.nickname), ratingStars(row.rating));
    words.append(who, h("div", "muted", row.content));
    const ops = h("div", "ops");
    const state = h("span", `pill ${row.enabled ? "on" : "off"}`, row.enabled ? "展示中" : "已隐藏");
    const toggle = h("button", "", row.enabled ? "隐藏" : "展示");
    toggle.addEventListener("click", async () => {
      await api(`/api/v1/b/testimonials/${row.id}`, {
        method: "PATCH",
        body: JSON.stringify({ enabled: !row.enabled }),
      });
      render();
    });
    const remove = h("button", "danger", "删除");
    remove.addEventListener("click", async () => {
      const ok = await confirmAction("删掉这条评价？", `${row.nickname}：${row.content}`);
      if (!ok) return;
      try {
        await api(`/api/v1/b/testimonials/${row.id}`, { method: "DELETE" });
        toast(draftMessage("已删除"), "ok");
        render();
      } catch (error) {
        toast(error.message, "bad");
      }
    });
    const edit = h("button", "", "编辑");
    edit.addEventListener("click", () => openFormDialog(testimonialForm(row), "编辑反馈展示", edit));
    ops.append(state, edit, toggle, remove);
    item.append(words, ops);
    items.append(item);
  });

  list.append(items);
  sortableRows(items, ".quote-row", "testimonials");
  list.prepend(editorAction(`反馈展示（${rows.length}）`, "＋ 新增反馈", () => testimonialForm()));
  box.append(list);
  return box;
}

function testimonialForm(row = null) {
  const panel = h("form", "panel stack");
  panel.append(h("h2", "panel-title", row ? "编辑反馈" : "新增反馈"));
  const grid = h("div", "form-grid");
  grid.append(field("昵称", "nickname", row?.nickname || ""));
  const ratingWrap = h("label", "field");
  ratingWrap.append(h("span", "", "评分"));
  const rating = document.createElement("select");
  [5, 4, 3, 2, 1].forEach((value) => {
    const option = document.createElement("option");
    option.value = String(value);
    option.textContent = `${value} 星`;
    rating.append(option);
  });
  rating.value = String(row?.rating || 5);
  ratingWrap.append(rating);
  grid.append(ratingWrap);
  grid.append(field("评价内容", "content", row?.content || "", true, "textarea"));
  panel.append(grid);

  const error = h("p", "muted", "");
  const submit = h("button", "btn", row ? "保存修改" : "添加反馈");
  panel.previewCandidate = () => decorationWorkspace.candidate("testimonials", {
    nickname: val(panel, "nickname"), content: val(panel, "content"), rating: Number(rating.value),
  }, row?.id);
  submit.type = "submit";
  panel.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (submit.disabled) return;
    submit.disabled = true;
    try {
      await api(`/api/v1/b/testimonials${row ? "/" + row.id : ""}`, {
        method: row ? "PATCH" : "POST",
        body: JSON.stringify({
          nickname: val(panel, "nickname"),
          content: val(panel, "content"),
          rating: Number(rating.value),
        }),
      });
      toast(draftMessage("评价已添加"), "ok");
      render();
    } catch (err) {
      error.textContent = err.message;
    } finally {
      submit.disabled = false;
    }
  });
  panel.append(error, submit);
  return panel;
}

/** 类目选择：选项来自后台维护的分类标签，也允许现场填个新的。 */
function categoryField(names, value) {
  const wrap = h("label", "field");
  wrap.append(h("span", "", "类目"));
  const input = document.createElement("input");
  input.name = "category";
  input.maxLength = 15;
  input.value = value || names[0] || "";
  input.setAttribute("list", "cat-options");
  input.placeholder = "选一个或直接填新的";
  const datalist = document.createElement("datalist");
  datalist.id = "cat-options";
  names.forEach((name) => {
    const option = document.createElement("option");
    option.value = name;
    datalist.append(option);
  });
  wrap.append(input, datalist);
  wrap.append(h("small", "muted", "填了没见过的名字，保存后会自动加进「分类标签」"));
  return wrap;
}

async function labelEditor(kind, row, trigger) {
  const category = kind === "categories";
  const title = `${row ? "编辑" : "新增"}${category ? "分类" : "商品标签"}`;
  const mask = h("div", "modal label-editor-mask");
  const panel = h("form", "panel stack label-editor");
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-modal", "true");
  panel.setAttribute("aria-label", title);
  const heading = h("div", "label-editor-heading");
  const close = h("button", "btn-ghost", "×");
  close.type = "button";
  close.setAttribute("aria-label", "关闭");
  heading.append(h("h2", "", title), close);
  panel.append(heading, field("名称", "name", row?.name || ""));
  const input = panel.querySelector('input[name="name"]');
  input.required = true;
  input.maxLength = category ? 15 : 16;
  const colors = {};
  if (!category) {
    const defaults = tagColorDefaults(row);
    const preview = h("span", "tag-preview", row?.name || "标签预览");
    const grid = h("div", "label-colors-grid");
    const update = () => {
      preview.textContent = input.value.trim() || "标签预览";
      applyTagStyle(preview, Object.fromEntries(Object.entries(colors).map(([key, control]) => [key, control.value])));
    };
    for (const [key, title] of [["background_color", "背景颜色"], ["border_color", "边框颜色"], ["text_color", "文字颜色"]]) {
      const wrap = h("label", "field");
      wrap.append(h("span", "", title));
      const control = document.createElement("input");
      control.type = "color";
      control.value = defaults[key];
      control.name = key;
      colors[key] = control;
      control.addEventListener("input", update);
      wrap.append(control);
      grid.append(wrap);
    }
    input.addEventListener("input", update);
    update();
    const example = h("div", "label-preview-line");
    example.append(h("span", "muted", "买家端效果"), preview);
    panel.append(grid, example);
  }
  panel.append(h("p", "muted", category
    ? "名称最多15字；修改后，该分类下的商品会同步更新。"
    : "列表越靠前，商品卡展示该标签的优先级越高。"));
  const error = h("p", "label-editor-error");
  error.setAttribute("role", "alert");
  const actions = h("div", "label-editor-actions");
  const cancel = h("button", "btn-ghost", "取消");
  cancel.type = "button";
  const submit = h("button", "btn", row ? "保存修改" : "确认新增");
  submit.type = "submit";
  actions.append(cancel, submit);
  panel.append(error, actions);
  mask.append(panel);
  let saving = false;
  let confirming = false;
  const dismiss = () => {
    if (saving || confirming) return;
    mask.remove();
    if (trigger?.isConnected) trigger.focus();
  };
  close.addEventListener("click", dismiss);
  cancel.addEventListener("click", dismiss);
  mask.addEventListener("click", event => { if (event.target === mask) dismiss(); });
  mask.addEventListener("keydown", event => {
    if (event.key === "Escape") { event.preventDefault(); dismiss(); }
    if (event.key === "Tab") {
      const controls = [...panel.querySelectorAll("input, button")].filter(node => !node.disabled);
      const first = controls[0];
      const last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }
  });
  panel.addEventListener("submit", async event => {
    event.preventDefault();
    if (saving || confirming) return;
    const name = input.value.trim();
    if (!name) { error.textContent = "请填写名称"; input.focus(); return; }
    if (category && row && name !== row.name) {
      confirming = true;
      const ok = await confirmAction("确认修改分类名称？",
        `将「${row.name}」改为「${name}」，该分类下的 ${row.product_count} 件商品也会同步更新。`, "确认修改");
      confirming = false;
      if (!ok) { input.focus(); return; }
    }
    saving = true;
    submit.disabled = true;
    close.disabled = true;
    cancel.disabled = true;
    error.textContent = "";
    try {
      const payload = category ? { name } : { name, ...Object.fromEntries(Object.entries(colors).map(([key, control]) => [key, control.value])) };
      await api(`/api/v1/b/${kind}${row ? "/" + row.id : ""}`, {
        method: row ? "PATCH" : "POST", body: JSON.stringify(payload)
      });
      mask.remove();
      toast(row ? "已保存" : "已新增", "ok");
      render();
    } catch (failure) {
      error.textContent = failure.message;
    } finally {
      saving = false;
      submit.disabled = false;
      close.disabled = false;
      cancel.disabled = false;
    }
  });
  document.body.append(mask);
  input.focus();
}

async function labelsAdmin(kind) {
  const category = kind === "categories";
  const box = h("div", "label-admin");
  const header = h("div", "label-page-heading");
  const titles = h("div");
  titles.append(h("h1", "page-title", category ? "分类标签" : "商品标签"));
  titles.append(h("p", "page-sub", category
    ? "管理买家端的分类筛选与商品类目。修改名称后，关联商品同步更新。"
    : "管理商品卡片角标。一件商品可关联多个，优先展示排序最靠前的标签。"));
  const add = h("button", "btn", category ? "＋ 新增分类" : "＋ 新增标签");
  add.addEventListener("click", () => labelEditor(kind, null, add));
  header.append(titles, add);
  box.append(header);
  const rows = await api(`/api/v1/b/${kind}`);
  const panel = h("div", "panel label-list-panel");
  const top = h("div", "label-list-heading");
  top.append(h("h2", "", `全部${category ? "分类" : "标签"}`), h("span", "label-total", `${rows.length} 个`));
  panel.append(top, h("p", "muted label-list-note", category
    ? "顺序与买家端分类展示一致；有关联商品的分类不可删除。"
    : "拖动左侧手柄调整展示优先级，松开后自动保存；删除标签不会删除商品。"));
  const scroll = h("div", "label-table-scroll");
  const table = h("table", "label-table");
  const head = h("thead");
  const headRow = h("tr");
  for (const text of category ? ["排序", "分类名称", "关联商品", "操作"] : ["排序", "标签名称", "展示预览", "关联商品", "操作"]) {
    const cell = h("th", "", text);
    cell.scope = "col";
    headRow.append(cell);
  }
  head.append(headRow);
  const body = h("tbody");
  rows.forEach((row, index) => {
    const item = h("tr");
    item.dataset.sortId = row.id;
    item.dataset.sortName = row.name;
    item.append(h("td", "label-rank", String(index + 1).padStart(2, "0")), h("td", "label-name", row.name));
    if (!category) {
      const cell = h("td");
      const preview = h("span", "tag-preview", row.name);
      applyTagStyle(preview, row);
      cell.append(preview);
      item.append(cell);
    }
    item.append(h("td", "label-count", `${row.product_count} 件商品`));
    const cell = h("td");
    const ops = h("div", "label-ops");
    const edit = h("button", "label-edit", "编辑");
    edit.setAttribute("aria-label", `编辑${row.name}`);
    edit.addEventListener("click", () => labelEditor(kind, row, edit));
    ops.append(edit);
    const remove = h("button", "label-delete", "删除");
    remove.setAttribute("aria-label", `删除${row.name}`);
    remove.disabled = category && row.product_count > 0;
    remove.title = remove.disabled ? "请先移走该分类下的商品" : "";
    remove.addEventListener("click", async () => {
      const ok = await confirmAction(`删除「${row.name}」？`, category
        ? "删除后无法恢复。" : `关联的 ${row.product_count} 件商品会移除此角标，商品本身不受影响。`);
      if (!ok) return;
      try {
        await api(`/api/v1/b/${kind}/${row.id}`, { method: "DELETE" });
        toast("已删除", "ok"); render();
      } catch (failure) { toast(failure.message, "bad"); }
    });
    ops.append(remove);
    cell.append(ops);
    item.append(cell);
    body.append(item);
  });
  table.append(head, body);
  sortableRows(body, "tr", kind);
  scroll.append(table);
  panel.append(scroll);
  if (!rows.length) panel.append(h("p", "label-empty", "暂无记录，点击右上角按钮添加"));
  box.append(panel);
  return box;
}

async function categoriesAdmin() {
  return labelsAdmin("categories");
}

async function tagsAdmin() {
  return labelsAdmin("tags");
}

/** 商品编辑里的标签多选，最多 4 个，和接口上限一致。 */
function tagPicker(names, value) {
  const wrap = h("label", "field");
  wrap.append(h("span", "", "商品标签（卡片左上角显示排最前的那个）"));
  const chosen = new Set(value || []);
  const row = h("div", "tag-picker");
  names.forEach((name) => {
    const chip = h("button", chosen.has(name) ? "chip on" : "chip", name);
    chip.type = "button";
    chip.addEventListener("click", () => {
      if (chosen.has(name)) chosen.delete(name);
      else if (chosen.size >= 4) return toast("一件商品最多挂 4 个标签", "bad");
      else chosen.add(name);
      chip.classList.toggle("on", chosen.has(name));
    });
    row.append(chip);
  });
  if (!names.length) row.append(h("span", "muted", "还没有标签，先去「商品标签」加几个"));
  wrap.append(row);
  wrap.append(h("small", "muted", "没勾就是不带角标，买家端会退回显示折扣或热销"));
  // 提交时按商家定义的标签顺序取，排最前的那个会显示在卡片上
  wrap.selected = () => names.filter((name) => chosen.has(name));
  return wrap;
}

/* ---------------- 概览 ---------------- */
async function dashboard() {
  const box = h("div");
  box.append(h("h1", "page-title", "经营概览"));
  box.append(h("p", "page-sub", "商品和库存一改，买家端刷新就会看到同一份数据"));
  const data = await api("/api/v1/b/dashboard");

  const stats = h("div", "stats");
  const lowCount = data.low_stock.length;
  const cards = [
    ["在售商品", data.on_sale, `共 ${data.product_total} 件商品`, ""],
    ["成交额", money(data.sales_yuan), "已付款订单合计", "accent"],
    ["待发货", data.pending_ship, "需要尽快处理", data.pending_ship ? "alert" : ""],
    ["库存预警", lowCount, lowCount ? "有规格低于 5 件" : "库存都还充足", lowCount ? "alert" : ""],
  ];
  cards.forEach(([label, value, hint, cls]) => {
    const card = h("div", `stat ${cls}`.trim());
    card.append(h("div", "k", label), h("div", "v", String(value)), h("div", "hint", hint));
    stats.append(card);
  });
  box.append(stats);

  const cols = h("div", "two-col");
  const recent = h("div", "panel");
  const recentTitle = h("h2", "panel-title", "最近订单");
  const more = h("a", "more", "全部订单 →");
  more.href = "#/orders";
  recentTitle.append(more);
  recent.append(recentTitle);
  if (!data.recent_orders.length) {
    recent.append(h("p", "muted", "还没有订单"));
  } else {
    const list = h("div", "mini-list");
    data.recent_orders.forEach((order) => {
      const item = h("div", "item");
      const left = h("div");
      left.append(h("div", "who", order.order_no), h("div", "tagx", order.buyer || "买家"));
      const right = h("div", "row");
      right.append(h("span", `pill ${order.status}`, STATUS[order.status] || order.status));
      right.append(h("span", "price", money(order.total_yuan)));
      item.append(left, right);
      list.append(item);
    });
    recent.append(list);
  }

  const ranking = h("div", "panel");
  ranking.append(h("h2", "panel-title", "商品销量排行"));
  const products = await api("/api/v1/b/products");
  const ranked = [...products].sort((a, b) => b.sales_count - a.sales_count).slice(0, 6);
  if (!ranked.length) {
    ranking.append(h("p", "muted", "还没有商品"));
  } else {
    const top = Math.max(...ranked.map((item) => item.sales_count), 1);
    const bars = h("div", "bars");
    ranked.forEach((item) => {
      const col = h("div");
      const bar = document.createElement("i");
      bar.style.height = `${Math.max(8, Math.round((item.sales_count / top) * 100))}%`;
      col.append(h("span", "", String(item.sales_count)), bar, h("span", "", item.name.slice(0, 2)));
      bars.append(col);
    });
    ranking.append(bars);
  }

  cols.append(recent, ranking);
  box.append(cols);

  const low = h("div", "panel");
  low.append(h("h2", "panel-title", "库存预警"));
  if (!lowCount) {
    low.append(h("p", "muted", "所有在售规格库存都高于 5 件"));
  } else {
    const list = h("div", "mini-list");
    data.low_stock.forEach((row) => {
      const item = h("div", "item");
      const left = h("div");
      left.append(h("div", "who", row.product_name), h("div", "tagx", `规格 ${row.spec}`));
      const tag = h("span", row.stock === 0 ? "pill banned" : "pill pending", `剩 ${row.stock} 件`);
      item.append(left, tag);
      list.append(item);
    });
    low.append(list);
  }
  box.append(low);

  const quick = h("div", "panel");
  quick.append(h("h2", "panel-title", "常用操作"));
  const row = h("div", "row");
  const addProduct = h("button", "btn", "发布新商品");
  addProduct.addEventListener("click", () => openProductEditor("new", addProduct));
  const toOrders = h("button", "btn-ghost", `处理待发货（${data.pending_ship}）`);
  toOrders.addEventListener("click", () => go("#/orders/paid"));
  const toShop = h("button", "btn-ghost", "修改店铺公告");
  toShop.addEventListener("click", () => go("#/shop"));
  const toBuyer = h("a", "btn-ghost", "打开买家端 ↗");
  toBuyer.href = shopInfo ? shopInfo.share_path : "/c.html?code=nanzhi";
  toBuyer.target = "_blank";
  row.append(addProduct, toOrders, toShop, toBuyer);
  quick.append(row);
  box.append(quick);
  return box;
}

/* ---------------- 商品 ---------------- */
async function productList() {
  const box = h("div", "product-workspace");
  box.append(h("h1", "page-title", "商品管理"));
  box.append(h("p", "page-sub", "上下架、禁售、价格和库存的改动会立刻同步到买家端"));
  let products = await api("/api/v1/b/products");

  const busy = false;
  const stats = h("div", "product-stats");
  box.append(stats);
  const bar = h("div", "toolbar-inline");
  const keyword = document.createElement("input");
  keyword.placeholder = "搜索商品名称或编号";
  keyword.setAttribute("aria-label", "搜索商品名称或编号");
  keyword.value = productFilters.keyword;
  const select = (label, options, value) => {
    const node = document.createElement("select");
    node.setAttribute("aria-label", label);
    options.forEach(([key, text]) => { const option = h("option", "", text); option.value = key; node.append(option); });
    node.value = value;
    return node;
  };
  const status = select("商品状态", [["", "全部状态"], ["draft", "草稿"], ["on", "在售"], ["off", "下架"], ["banned", "禁售"]], productFilters.status);
  const category = select("商品类目", [["", "全部类目"], ...[...new Set(products.map(p => p.category).filter(Boolean))].map(name => [name, name])], productFilters.category);
  const stockFilter = select("库存筛选", [["", "全部库存"], ["low", "库存预警（≤5）"], ["zero", "已售罄"]], productFilters.stock);
  const sort = select("商品排序", [["default", "默认排序"], ["sales", "销量从高到低"], ["stock", "库存从低到高"], ["price", "价格从低到高"]], productFilters.sort);
  const reset = h("button", "btn-ghost", "重置");
  const add = h("button", "btn push", "＋ 发布商品");
  add.addEventListener("click", () => openProductEditor("new", add));
  bar.append(keyword, status, category, stockFilter, sort, reset, add);
  box.append(bar);
  const host = h("div");
  const pager = h("div", "admin-pagination");
  box.append(host, pager);
  const stock = p => p.skus.reduce((sum, sku) => sum + sku.stock, 0);
  const low = p => p.skus.some(sku => sku.status === "on" && sku.stock <= 5);
  function paint() {
    const query = productFilters.keyword.trim().toLowerCase();
    const rows = products.filter(p => (!query || p.name.toLowerCase().includes(query) || String(p.id).includes(query)) && (!productFilters.status || p.status === productFilters.status) && (!productFilters.category || p.category === productFilters.category) && (!productFilters.stock || (productFilters.stock === "zero" ? stock(p) === 0 : low(p))));
    if (productFilters.sort === "sales") rows.sort((a, b) => b.sales_count - a.sales_count);
    if (productFilters.sort === "stock") rows.sort((a, b) => stock(a) - stock(b));
    if (productFilters.sort === "price") rows.sort((a, b) => (a.price_from ?? Infinity) - (b.price_from ?? Infinity));
    const pages = Math.max(1, Math.ceil(rows.length / 10));
    productFilters.page = Math.min(productFilters.page, pages);
    const pageRows = rows.slice((productFilters.page - 1) * 10, productFilters.page * 10);
    stats.replaceChildren();
    [["全部商品", products.length, ""], ["草稿", products.filter(p => p.status === "draft").length, "draft"], ["在售商品", products.filter(p => p.status === "on").length, "on"], ["已下架", products.filter(p => p.status === "off").length, "off"], ["库存预警", products.filter(low).length, "low"]].forEach(([label, count, filter]) => {
      const card = h("button", "product-stat" + ((filter === "low" ? productFilters.stock === "low" : productFilters.status === filter) ? " active" : ""));
      card.append(h("span", "", label), h("strong", "", String(count)));
      card.disabled = busy;
      card.addEventListener("click", () => { productFilters.status = filter === "low" ? "" : filter; productFilters.stock = filter === "low" ? "low" : ""; status.value = productFilters.status; stockFilter.value = productFilters.stock; productFilters.page = 1;  paint(); });
      stats.append(card);
    });
    host.replaceChildren(rows.length ? productTable(pageRows, { reload, busy }) : h("div", "panel empty", "没有匹配的商品，试试重置筛选条件"));
    const prev = h("button", "btn-ghost", "上一页");
    const next = h("button", "btn-ghost", "下一页");
    prev.disabled = busy || productFilters.page === 1;
    next.disabled = busy || productFilters.page === pages;
    prev.addEventListener("click", () => { productFilters.page--;  paint(); });
    next.addEventListener("click", () => { productFilters.page++;  paint(); });
    pager.replaceChildren(h("span", "muted", `共 ${rows.length} 件 · 第 ${productFilters.page} / ${pages} 页`), prev, next);
  }
  async function reload() { products = await api("/api/v1/b/products");  paint(); }
  [keyword, status, category, stockFilter, sort].forEach(node => node.addEventListener(node === keyword ? "input" : "change", () => {
    Object.assign(productFilters, { keyword: keyword.value, status: status.value, category: category.value, stock: stockFilter.value, sort: sort.value, page: 1 });  paint();
  }));
  reset.addEventListener("click", () => { Object.assign(productFilters, { keyword: "", status: "", category: "", stock: "", sort: "default", page: 1 }); keyword.value = status.value = category.value = stockFilter.value = ""; sort.value = "default";  paint(); });
  paint();
  return box;
}

function productTable(products, options = {}) {
  const wrap = h("div", "table-wrap");
  const table = h("table", "table");
  const head = document.createElement("thead");
  const headRow = document.createElement("tr");
  const expandHead = h("th", "expand-cell");
  // 表头留空，仅保留各商品的展开按钮。
  headRow.append(expandHead);
  ["商品", "类目", "价格", "库存", "状态", "销量", "操作"].forEach((text) => headRow.append(h("th", "", text)));
  head.append(headRow);
  const body = document.createElement("tbody");

  products.forEach((product) => {
    const tr = document.createElement("tr");
    const expandCell = h("td", "expand-cell");
    const expand = h("button", "sku-expand");
    expand.type = "button";
    expand.disabled = options.busy;
    expandCell.append(expand); tr.append(expandCell);
    const info = document.createElement("td");
    const row = h("div", "row");
    const image = document.createElement("img");
    image.className = "thumb";
    image.src = cover(product.image_url);
    image.alt = product.name;
    const words = h("div");
    words.append(h("div", "name", product.name));
    words.append(h("div", "muted", `#${product.id} · ${product.skus.length} 个规格`));
    row.append(image, words);
    info.append(row);

    const category = document.createElement("td");
    category.textContent = product.category || "-";
    const price = document.createElement("td");
    price.textContent = product.price_from == null ? "-" : money(product.price_from);
    const stockCell = document.createElement("td");
    const stock = product.skus.reduce((sum, sku) => sum + sku.stock, 0);
    const lowSku = product.skus.filter((sku) => sku.status === "on" && sku.stock <= 5).length;
    stockCell.append(document.createTextNode(String(stock)));
    if (lowSku) stockCell.append(h("div", "low", `${lowSku} 个规格偏低`));
    const state = document.createElement("td");
    state.append(h("span", `pill ${product.status}`, STATUS[product.status] || product.status));
    const sales = document.createElement("td");
    sales.textContent = String(product.sales_count);

    const ops = h("td");
    const opsRow = h("div", "ops");
    const edit = h("a", "", "编辑");
    edit.href = `#/products/${product.id}`;
    edit.addEventListener("click", event => {
      if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      openProductEditor(String(product.id), edit);
    });
    if (product.status !== "banned") opsRow.append(edit);
    else opsRow.append(h("span", "muted", "平台禁售 · 只读"));

    statusActions(product.status).filter(([action]) => action !== "ban").forEach(([act, label]) => {
      const button = h("button", act === "ban" ? "danger" : "", label);
      button.disabled = options.busy;
      button.addEventListener("click", async () => {
        if (button.disabled) return;
        if (act === "ban" && !(await confirmAction(`禁售「${product.name}」？`, "禁售后买家将无法查看或购买，解禁后商品会回到下架状态。", "确认禁售"))) return;
        button.disabled = true;
        try {
          await api(`/api/v1/b/products/${product.id}/status`, {
            method: "POST",
            body: JSON.stringify({ action: act }),
          });
          toast(`${product.name} 已${label}`, "ok");
          if (options.reload) await options.reload(); else render();
        } catch (error) {
          toast(error.message, "bad");
        } finally {
          button.disabled = false;
        }
      });
      opsRow.append(button);
    });
    ops.append(opsRow);

    tr.append(info, category, price, stockCell, state, sales, ops);
    body.append(tr);
    const detailRow = h("tr", "sku-expansion-row");
    const detailCell = h("td");
    detailCell.colSpan = 8;
    detailRow.append(detailCell);
    body.append(detailRow);
    let mounted = false;
    function paintExpansion() {
      const open = expandedProducts.has(product.id);
      expand.textContent = open ? "−" : "＋";
      expand.setAttribute("aria-label", `${open ? "收起" : "展开"}${product.name}的 SKU`);
      expand.setAttribute("aria-expanded", String(open));
      detailRow.id = `product-skus-${product.id}`;
      expand.setAttribute("aria-controls", detailRow.id);
      detailRow.hidden = !open;
      if (open && !mounted) {
        detailCell.append(renderSkuPanel(product, options.reload));
        mounted = true;
      }
    }

    expand.addEventListener("click", () => {
      expandedProducts.has(product.id) ? expandedProducts.delete(product.id) : expandedProducts.add(product.id);
      paintExpansion();
    });
    paintExpansion();
  });

  table.append(head, body);
  wrap.append(table);
  return wrap;
}

async function openProductEditor(id, trigger) {
  const version = renderVersion;
  try {
    const content = await productEditor(id, true);
    if (version !== renderVersion || !trigger.isConnected) return;
    const form = content.querySelector("form");
    if (!form) { toast("没有找到这个商品", "bad"); return; }
    openFormDialog(form, id === "new" ? "发布商品" : "编辑商品信息", trigger);
  } catch (error) { toast(error.message, "bad"); }
}

async function productEditor(id, basicOnly = false) {
  const creating = id === "new";
  const box = h("div");
  box.append(h("h1", "page-title", creating ? "发布商品" : "编辑商品"));
  box.append(h("p", "page-sub", creating ? "保存为商品草稿，确认后可发布上架或完成创建；草稿不会出现在买家端" : "改动会立刻生效到买家端"));
  const back = h("button", "btn-ghost", "← 返回商品列表");
  back.addEventListener("click", () => go("#/products"));
  box.append(back);

  const panel = h("form", "panel stack");
  panel.style.marginTop = "16px";
  let product = { name: "", category: "", description: "", image_url: "", skus: [] };
  if (!creating) {
    const products = await api("/api/v1/b/products");
    product = products.find((item) => String(item.id) === id);
    if (!product) return h("div", "panel", "没有找到这个商品");
    if (product.status === "banned") {
      box.append(h("p", "panel", "该商品已被平台禁售，只能查看；商家不能编辑或自行解禁，请联系平台处理。"), renderSkuPanel(product));
      return box;
    }
  }
  let catNames = [];
  let tagNames = [];
  try {
    catNames = (await api("/api/v1/b/categories")).map((item) => item.name);
  } catch {
    catNames = [];
  }
  try {
    tagNames = (await api("/api/v1/b/tags")).map((item) => item.name);
  } catch {
    tagNames = [];
  }
  const tagField = tagPicker(tagNames, (product.tags || []).map((tag) => tag.name));

  panel.append(h("h2", "panel-title", "基本信息"));
  const grid = h("div", "form-grid");
  grid.append(
    field("商品名称", "name", product.name),
    categoryField(catNames, product.category),
    imageField("商品主图", "image_url", product.image_url),
    field("每人限购（0 表示不限）", "limit_per_user", String(product.limit_per_user ?? 0)),    field("商品说明", "description", product.description, true, "textarea")
  );
  panel.append(grid, tagField);
  if (!creating) panel.append(field("商品排序（数字越小越靠前）", "sort_order", String(product.sort_order || 0)));
  if (creating) {
    panel.append(h("h2", "panel-title", "首个规格"));
    const skuGrid = h("div", "form-grid");
    skuGrid.append(field("规格名", "spec", "默认"), field("价格", "price", "39"), field("库存", "stock", "10"));
    panel.append(skuGrid);
  }

  const error = h("p", "muted", "");
  const submit = h("button", "btn", creating ? "保存商品草稿" : "保存修改");
  submit.type = "submit";
  panel.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (submit.disabled) return;
    const name = val(panel, "name");
    const limit = Number(val(panel, "limit_per_user"));
    if (!name) { error.textContent = "请填写商品名称"; return; }
    if (!Number.isInteger(limit) || limit < 0) { error.textContent = "限购数量应为大于等于 0 的整数"; return; }
    if (creating && (!val(panel, "spec") || !Number.isFinite(Number(val(panel, "price"))) || Number(val(panel, "price")) <= 0 || !val(panel, "stock") || !Number.isInteger(Number(val(panel, "stock"))) || Number(val(panel, "stock")) < 0)) {
      error.textContent = "请填写规格名、有效售价和大于等于 0 的整数库存";
      return;
    }
    error.textContent = "";
    submit.disabled = true;
    submit.textContent = "正在保存…";
    try {
      const payload = {
        name: val(panel, "name"),
        category: val(panel, "category"),
        description: val(panel, "description"),
        image_url: val(panel, "image_url"),
        limit_per_user: Number(val(panel, "limit_per_user") || 0),
        tag_names: tagField.selected(),
        ...(!creating ? { sort_order: Number(val(panel, "sort_order") || 0) } : {}),
      };
      if (creating) {
        payload.skus = [
          { spec: val(panel, "spec"), price_yuan: Number(val(panel, "price")), stock: Number(val(panel, "stock")) },
        ];
        payload.status = "draft";
        await api("/api/v1/b/products", { method: "POST", body: JSON.stringify(payload) });
        Object.assign(productFilters, {keyword: "", status: "draft", category: "", stock: "", page: 1});
        toast("已保存商品草稿，确认后再发布上架", "ok");
      } else {
        await api(`/api/v1/b/products/${product.id}`, { method: "PATCH", body: JSON.stringify(payload) });
        toast("已保存", "ok");
      }
      go("#/products");
    } catch (err) {
      error.textContent = err.message;
    } finally {
      submit.disabled = false;
      submit.textContent = creating ? "保存商品草稿" : "保存修改";
    }
  });
  panel.append(error, submit);
  box.append(panel);

  if (!creating && !basicOnly) {
    box.append(renderSkuPanel(product));
  }
  return box;
}

function renderSkuPanel(product, reload = render) {
  const panel = h("div", "panel");
  let unsaved = false;
  panel.addEventListener("input", () => { unsaved = true; });
  panel.append(h("h2", "panel-title", `规格与库存（${product.skus.length}）`));
  panel.append(h("p", "muted", product.status === "banned" ? "平台禁售商品：规格、图片、价格、库存和状态均只读。" : "拖动规格左侧手柄排序，松开后自动保存并同步买家端规格与缩略图顺序。"));
  const wrap = h("div", "table-wrap");
  const table = h("table", "table sku-table");
  const head = document.createElement("thead");
  const headRow = document.createElement("tr");
  ["规格", "规格图", "划线价", "售价", "库存", "状态", "操作"].forEach((text) => headRow.append(h("th", "", text)));
  head.append(headRow);
  const tbody = document.createElement("tbody");
  product.skus.forEach((sku) => {
    const tr = document.createElement("tr");
    tr.dataset.sortId = sku.id;
    tr.dataset.sortName = sku.spec;
    const specCell = document.createElement("td");
    const specInput = document.createElement("input");
    specInput.className = "stock-input spec-input";
    specInput.value = sku.spec;
    specInput.maxLength = 40;
    specInput.setAttribute("aria-label", `${sku.spec} 规格名`);
    specCell.append(specInput);
    const parameterEditor = document.createElement("details");
    parameterEditor.className = "sku-parameter-editor";
    parameterEditor.append(h("summary", "", "商品参数（选填）"));
    const parameterInput = document.createElement("textarea");
    parameterInput.rows = 4;
    parameterInput.placeholder = "每行一项，例如：\n容量：350 mL\n材质：陶瓷";
    parameterInput.setAttribute("aria-label", `${sku.spec} 商品参数（选填）`);
    parameterInput.value = (sku.parameters || []).map(item => `${item.name}：${item.value}`).join("\n");
    parameterInput.disabled = !Array.isArray(sku.parameters);
    parameterEditor.append(parameterInput, h("small", "muted", parameterInput.disabled ? "后端尚未加载参数功能，重启后可配置。" : "可留空，最多12项；买家悬停对应规格时显示。"));
    specCell.append(parameterEditor);

    // 每个规格一张图，买家端详情页切规格就会换主图
    const imageCell = document.createElement("td");
    const imageWrap = skuImageField(`sku-image-${sku.id}`, sku.image_url);
    imageCell.append(imageWrap);

    const marketCell = document.createElement("td");
    const marketInput = document.createElement("input");
    marketInput.className = "stock-input sku-market";
    marketInput.value = sku.market_price_yuan ?? "";
    marketInput.placeholder = "不设";
    marketInput.setAttribute("aria-label", `${sku.spec} 划线价`);
    marketCell.append(marketInput);

    const priceCell = document.createElement("td");
    const priceInput = document.createElement("input");
    priceInput.className = "stock-input sku-price";
    priceInput.value = sku.price_yuan;
    priceInput.setAttribute("aria-label", `${sku.spec} 售价`);
    priceCell.append(priceInput);

    const stockCell = document.createElement("td");
    const stockInput = document.createElement("input");
    stockInput.className = "stock-input sku-stock";
    stockInput.value = sku.stock;
    stockInput.setAttribute("aria-label", `${sku.spec} 库存`);
    if (sku.status === "on" && sku.stock <= 5) stockInput.classList.add("low");
    stockCell.append(stockInput);

    const state = document.createElement("td");
    state.append(h("span", `pill ${sku.status}`, STATUS[sku.status] || sku.status));
    const ops = h("td");
    const opsRow = h("div", "ops");
    const save = h("button", "", "保存");
    save.addEventListener("click", async () => {
      if (save.disabled) return;
      const errors = checkSkuInput(specInput, priceInput, stockInput, marketInput);
      if (errors) return toast(errors, "bad");
      save.disabled = true;
      try {
        const payload = {
          spec: specInput.value.trim(),
          price_yuan: Number(priceInput.value),
          stock: Number(stockInput.value),
          image_url: imageWrap.querySelector("input").value.trim(),
        };
        if (!parameterInput.disabled) payload.parameters = readSkuParameters(parameterInput.value);
        payload.market_price_yuan = marketInput.value ? Number(marketInput.value) : null;
        await api(`/api/v1/b/skus/${sku.id}`, { method: "PATCH", body: JSON.stringify(payload) });
        toast(`${payload.spec} 已更新`, "ok");
        await reload();
      } catch (error) {
        toast(error.message, "bad");
      } finally {
        save.disabled = false;
      }
    });
    opsRow.append(save);
    statusActions(sku.status).filter(([action]) => action !== "ban").forEach(([act, label]) => {
      const button = h("button", act === "ban" ? "danger" : "", label);
      button.addEventListener("click", async () => {
        if (button.disabled) return;
        button.disabled = true;
        try {
          await api(`/api/v1/b/skus/${sku.id}/status`, { method: "POST", body: JSON.stringify({ action: act }) });
          toast(`${sku.spec} 已${label}`, "ok");
          await reload();
        } catch (error) {
          toast(error.message, "bad");
        } finally {
          button.disabled = false;
        }
      });
      opsRow.append(button);
    });
    ops.append(opsRow);
    tr.append(specCell, imageCell, marketCell, priceCell, stockCell, state, ops);
    if (product.status === "banned" || sku.status === "banned") {
      tr.querySelectorAll("input, textarea, button").forEach(node => { node.disabled = true; });
      opsRow.replaceChildren(h("span", "muted", "平台禁售 · 只读"));
    }
    tbody.append(tr);
  });
  table.append(head, tbody);
  if (product.status !== "banned" && product.skus.every(sku => sku.status !== "banned")) {
    makeSortable(tbody, "tr", async ids => {
      try {
        if (unsaved) throw new Error("请先保存规格内容的修改，再拖拽排序");
        const sorted = await api(`/api/v1/b/products/${product.id}/skus/sort`, {method: "POST", body: JSON.stringify({ordered_ids: ids})});
        product.skus.splice(0, product.skus.length, ...sorted.skus);
      } catch (error) { toast(error.message, "bad"); throw error; }
    });
  }
  wrap.append(table);
  panel.append(wrap);

  const addRow = h("div", "toolbar-inline");
  addRow.style.marginTop = "16px";
  const spec = document.createElement("input");
  spec.placeholder = "新规格名";
  const price = document.createElement("input");
  price.placeholder = "价格";
  const stock = document.createElement("input");
  stock.placeholder = "库存";
  const add = h("button", "btn-ghost", "＋ 添加规格");
  add.addEventListener("click", async () => {
    if (add.disabled) return;
    const errors = checkSkuInput(spec, price, stock);
    if (errors) return toast(errors, "bad");
    add.disabled = true;
    try {
      await api(`/api/v1/b/products/${product.id}/skus`, {
        method: "POST",
        body: JSON.stringify({
          spec: spec.value.trim(),
          price_yuan: Number(price.value),
          stock: Number(stock.value),
        }),
      });
      toast("规格已添加", "ok");
      await reload();
    } catch (error) {
      toast(error.message, "bad");
    } finally {
      add.disabled = false;
    }
  });
  addRow.append(spec, price, stock, add);
  if (product.status === "banned") addRow.querySelectorAll("input, button").forEach(node => { node.disabled = true; });
  panel.append(addRow);
  return panel;
}

/** 规格表单的本地校验，先拦一次，省得拿英文的接口报错去给商家看。 */
function readSkuParameters(text) {
  const lines = text.split(/\r?\n/).map(line => line.trim()).filter(Boolean);
  if (lines.length > 12) throw new Error("商品参数最多12项");
  return lines.map(line => {
    const at = line.search(/[:：]/);
    const name = line.slice(0, at).trim();
    const value = line.slice(at + 1).trim();
    if (at <= 0 || !name || !value) throw new Error("参数请按“名称：内容”填写，每行一项");
    if (name.length > 24 || value.length > 100) throw new Error("参数名称最多24字，内容最多100字");
    return { name, value };
  });
}

function checkSkuInput(specInput, priceInput, stockInput, marketInput) {
  const spec = specInput.value.trim();
  if (!spec) return "规格名不能为空";
  const price = Number(priceInput.value);
  if (!priceInput.value.trim() || !Number.isFinite(price) || price <= 0) return "售价要填一个大于 0 的数字";
  const stock = Number(stockInput.value);
  if (!stockInput.value.trim() || !Number.isInteger(stock) || stock < 0) return "库存要填 0 或以上的整数";
  if (marketInput && marketInput.value.trim()) {
    const market = Number(marketInput.value);
    if (!Number.isFinite(market) || market <= 0) return "划线价要么留空，要么填大于 0 的数字";
    if (market <= price) return "划线价要高于售价，不然买家端看不到折扣";
  }
  return "";
}

/** 规格图：预览 + 上传 + 清除，路径输入框单独一行，表格里也放得下。 */
function skuImageField(name, value) {
  const wrap = h("div", "field sku-image");
  const head = h("div", "row sku-image-head");
  const preview = h("div", "sku-image-preview");
  const input = document.createElement("input");
  input.name = name;
  input.value = value || "";
  input.placeholder = "/covers/xxx.jpg";
  const file = document.createElement("input");
  file.type = "file";
  file.accept = "image/*";
  file.style.display = "none";
  const paint = () => {
    preview.classList.toggle("empty", !input.value);
    preview.style.backgroundImage = input.value ? `url("${input.value}")` : "";
  };
  const pick = h("button", "btn-ghost btn-mini", "上传");
  pick.type = "button";
  pick.addEventListener("click", () => file.click());
  file.addEventListener("change", async () => {
    if (!file.files?.length) return;
    pick.disabled = true;
    pick.textContent = "上传中…";
    try {
      input.value = await uploadImage(file.files[0]);
      paint();
      toast("图片已上传，记得点这一行的「保存」", "ok");
    } catch (error) {
      toast(error.message, "bad");
    }
    pick.disabled = false;
    pick.textContent = "上传";
  });
  const clear = h("button", "btn-ghost btn-mini", "清除");
  clear.type = "button";
  clear.addEventListener("click", () => {
    input.value = "";
    paint();
  });
  input.addEventListener("input", paint);
  paint();
  head.append(preview, pick, clear, file);
  wrap.append(head, input);
  return wrap;
}

/* ---------------- 订单 ---------------- */
async function orderList(status) {
  const box = h("div");
  box.append(h("h1", "page-title", "订单管理"));
  box.append(h("p", "page-sub", "买家付款后这里会出现待发货，点发货买家就能看到物流状态"));
  const tabs = h("div", "tabs");
  [["", "全部"], ["pending", "待支付"], ["paid", "待发货"], ["shipped", "已发货"], ["completed", "已完成"], ["cancelled", "已取消"]].forEach(
    ([value, label]) => {
      const button = h("button", value === status ? "on" : "", label);
      button.addEventListener("click", () => go(value ? `#/orders/${value}` : "#/orders"));
      tabs.append(button);
    }
  );
  box.append(tabs);

  const orders = await api(`/api/v1/b/orders?status=${status}`);
  if (!orders.length) {
    box.append(h("div", "panel empty", "这里还没有订单"));
    return box;
  }
  const picked = new Set();
  const searchBar = h("div", "toolbar-inline");
  const searchInput = h("input");
  searchInput.placeholder = "搜索订单号、买家、收货人或商品";
  searchInput.setAttribute("aria-label", searchInput.placeholder);
  const orderCount = h("span", "muted", `共 ${orders.length} 笔订单`);
  searchBar.append(searchInput, orderCount);
  box.append(searchBar);
  const wrap = h("div", "table-wrap");
  const table = h("table", "table");
  const head = document.createElement("thead");
  const headRow = document.createElement("tr");
  const headCheck = h("th");
  const allCheck = document.createElement("input");
  allCheck.type = "checkbox";
  allCheck.className = "check";
  allCheck.setAttribute("aria-label", "选择当前可见的待发货订单");
  const shippable = orders.filter((order) => order.status === "paid").map((order) => order.order_no);
  headCheck.append(allCheck);
  headRow.append(headCheck);
  ["订单号", "买家", "商品", "收货信息", "金额", "状态", "操作"].forEach((text) => headRow.append(h("th", "", text)));
  head.append(headRow);

  const tbody = h("tbody");
  const orderRows = [];
  orders.forEach((order) => {
    const tr = document.createElement("tr");
    orderRows.push({ order, tr, text: [order.order_no, order.buyer_nickname, order.receiver, ...order.items.map(item => item.product_name)].join(" ").toLowerCase() });
    const checkCell = h("td");
    if (order.status === "paid") {
      const check = document.createElement("input");
      check.type = "checkbox";
      check.className = "check";
      check.setAttribute("aria-label", `选择订单${order.order_no}`);
      check.addEventListener("change", () => {
        if (check.checked) picked.add(order.order_no);
        else picked.delete(order.order_no);
        syncBatch();
      });
      checkCell.append(check);
    }
    tr.append(checkCell);
    tr.append(h("td", "", order.order_no));
    tr.append(h("td", "", order.buyer_nickname || "-"));
    const goods = document.createElement("td");
    order.items.forEach((item) => goods.append(h("div", "muted", `${item.product_name} ${item.sku_spec} x${item.quantity}`)));
    tr.append(goods);
    tr.append(h("td", "muted", `${order.receiver || ""} ${order.address}`));
    tr.append(h("td", "", money(order.total_yuan)));
    const state = document.createElement("td");
    state.append(h("span", `pill ${order.status}`, order.status_label));
    tr.append(state);
    const ops = h("td");
    const opsRow = h("div", "ops");
    const detail = h("button", "", "查看详情");
    detail.addEventListener("click", () => orderDetails(order));
    opsRow.append(detail);
    if (order.status === "paid") {
      const ship = h("button", "", "发货");
      ship.addEventListener("click", async () => {
        if (ship.disabled) return;
        if (!(await confirmAction(`确认发货订单 ${order.order_no}？`, "确认后订单将变为已发货，请确保已完成实际发货。", "确认发货"))) return;
        ship.disabled = true;
        try {
          await api(`/api/v1/b/orders/${order.order_no}/ship`, { method: "POST" });
          toast(`${order.order_no} 已发货`, "ok");
          render();
        } catch (error) {
          toast(error.message, "bad");
        } finally {
          ship.disabled = false;
        }
      });
      opsRow.append(ship);
    }
    ops.append(opsRow);
    tr.append(ops);
    tbody.append(tr);
  });
  table.append(head, tbody);
  wrap.append(table);

  const batchBar = h("div", "toolbar-inline");
  batchBar.style.marginTop = "14px";
  const batchButton = h("button", "btn", "批量发货");
  const batchHint = h("span", "muted", shippable.length ? `当前有 ${shippable.length} 个待发货订单` : "当前没有待发货订单");
  batchButton.disabled = true;
  batchButton.addEventListener("click", async () => {
    if (!picked.size) return toast("先勾选要发货的订单");
    if (batchButton.disabled) return;
    if (!(await confirmAction(`确认发货 ${picked.size} 笔订单？`, "确认后所选订单将同步为已发货。", "确认批量发货"))) return;
    batchButton.disabled = true;
    try {
      const result = await api("/api/v1/b/orders/ship-batch", {
        method: "POST",
        body: JSON.stringify({ order_nos: [...picked] }),
      });
      const skipped = result.skipped.length ? `，${result.skipped.length} 个被跳过` : "";
      toast(`已发货 ${result.shipped.length} 个${skipped}`, result.skipped.length ? "bad" : "ok");
      render();
    } catch (error) {
      toast(error.message, "bad");
    } finally {
      syncBatch();
    }
  });
  const syncBatch = () => {
    batchButton.disabled = picked.size === 0;
    batchButton.textContent = picked.size ? `批量发货（${picked.size}）` : "批量发货";
    const visible = orderRows.filter(row => !row.tr.hidden && row.order.status === "paid");
    const count = visible.filter(row => picked.has(row.order.order_no)).length;
    allCheck.disabled = visible.length === 0;
    allCheck.checked = count > 0 && count === visible.length;
    allCheck.indeterminate = count > 0 && count < visible.length;
  };
  allCheck.addEventListener("change", () => {
    picked.clear();
    if (allCheck.checked) orderRows.filter(row => !row.tr.hidden && row.order.status === "paid").forEach(row => picked.add(row.order.order_no));
    tbody.querySelectorAll("input[type=checkbox]").forEach((node) => {
      if (!node.disabled) node.checked = allCheck.checked && !node.closest("tr").hidden;
    });
    syncBatch();
  });
  batchBar.append(batchButton, batchHint);
  const noMatch = h("div", "panel empty", "没有匹配的订单，请更换关键词");
  noMatch.hidden = true;
  searchInput.addEventListener("input", () => {
    picked.clear();
    const query = searchInput.value.trim().toLowerCase();
    let count = 0;
    orderRows.forEach(row => { row.tr.hidden = !row.text.includes(query); if (!row.tr.hidden) count++; });
    tbody.querySelectorAll("input[type=checkbox]").forEach(check => { check.checked = false; });
    orderCount.textContent = `共 ${count} 笔订单`;
    noMatch.hidden = count !== 0;
    wrap.hidden = count === 0;
    syncBatch();
  });
  syncBatch();
  box.append(wrap, noMatch, batchBar);
  return box;
}

function orderDetails(order) {
  const mask = h("div", "modal");
  const panel = h("section", "panel order-detail-panel");
  panel.setAttribute("role", "dialog"); panel.setAttribute("aria-modal", "true");
  panel.setAttribute("aria-label", "订单详情");
  const previous = document.activeElement;
  const close = h("button", "btn-ghost", "关闭详情");
  const done = () => { mask.remove(); document.removeEventListener("keydown", onKey); previous?.focus(); };
  const onKey = event => { if (event.key === "Escape") done(); if (event.key === "Tab") { event.preventDefault(); close.focus(); } };
  close.addEventListener("click", done);
  mask.addEventListener("click", event => { if (event.target === mask) done(); });
  document.addEventListener("keydown", onKey);
  const header = h("div", "order-detail-head");
  header.append(h("h2", "panel-title", "订单详情"), close);
  panel.append(header, h("p", "muted", order.order_no), h("span", `pill ${order.status}`, order.status_label));
  const grid = h("dl", "order-detail-info");
  [["买家", order.buyer_nickname], ["收货人", order.receiver], ["联系电话", order.phone], ["收货地址", order.address], ["下单时间（北京时间）", order.created_at ? new Date(order.created_at).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" }) : "—"]].forEach(([label, value]) => { grid.append(h("dt", "muted", label), h("dd", "", value || "—")); });
  panel.append(grid, h("h3", "panel-title", "商品明细"));
  order.items.forEach(item => {
    const row = h("div", "order-detail-item");
    row.append(h("div", "", `${item.product_name} · ${item.sku_spec}`), h("span", "muted", `${money(item.price_yuan)} × ${item.quantity}`));
    panel.append(row);
  });
  panel.append(h("p", "muted", `商品 ${money(order.goods_yuan)} · 运费 ${money(order.freight_yuan)}${order.discount_yuan ? ` · ${order.coupon_name} 优惠 ${money(order.discount_yuan)}` : ""}`), h("div", "order-detail-total", `订单金额 ${money(order.total_yuan)}`));
  mask.append(panel); document.body.append(mask); close.focus();
}

/* ---------------- 店铺 ---------------- */
async function shopForm() {
  const shop = await api("/api/v1/b/shop");
  shopInfo = shop;
  const box = h("div");
  box.append(h("h1", "page-title", "店铺设置"));
  box.append(h("p", "page-sub", "店铺信息和公告会显示在买家端的店头上"));

  const panel = h("form", "panel stack");
  panel.append(h("h2", "panel-title", "店铺信息"));
  const grid = h("div", "form-grid");
  grid.append(
    field("店铺名称", "name", shop.name),
    field("专属 AI 昵称（最多10字，无空格）", "assistant_name", storeAssistantName(shop)),
    statusField(shop.status),
    imageField("店铺 Logo", "logo_url", shop.logo_url),
    field("主题色", "theme_color", shop.theme_color, false, "color"),
    field("店铺公告", "notice", shop.notice, true, "textarea")
  );
  panel.append(grid);
  grid.querySelector('[name="assistant_name"]').maxLength = 10;
  const hint = h("p", "muted", "主题色会直接用在买家端的按钮、价格和标签上，改完刷新买家端就能看到");
  panel.append(hint);
  const error = h("p", "muted", "");
  const submit = h("button", "btn", "保存设置");
  submit.type = "submit";
  panel.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (submit.disabled) return;
    submit.disabled = true;
    try {
      shopInfo = await api("/api/v1/b/shop", {
        method: "PATCH",
        body: JSON.stringify({
          name: val(panel, "name"),
          assistant_name: val(panel, "assistant_name"),
          notice: val(panel, "notice"),
          status: val(panel, "status") || "open",
          logo_url: val(panel, "logo_url"),
          theme_color: val(panel, "theme_color"),
        }),
      });
      if (!shopInfo.assistant_name) {
        error.textContent = "其他设置已保存；AI昵称接口尚未加载，请正常重启后端后再保存昵称。";
        return;
      }
      toast("店铺设置已保存", "ok");
      render();
    } catch (err) {
      error.textContent = err.message;
    } finally {
      submit.disabled = false;
    }
  });
  panel.append(error, submit);

  const share = h("div", "panel");
  share.append(h("h2", "panel-title", "买家入口"));
  share.append(h("p", "muted", "买家从这个链接进店，只会看到你这家店，不会看到别的商家"));
  const link = h("a", "link", shop.share_path);
  link.href = shop.share_path;
  link.target = "_blank";
  const copy = h("button", "btn-ghost", "复制链接");
  copy.style.marginLeft = "12px";
  copy.addEventListener("click", () => {
    navigator.clipboard?.writeText(`${location.origin}${shop.share_path}`);
    toast("链接已复制", "ok");
  });
  const row = h("div", "row");
  row.append(link, copy);
  share.append(row);

  box.append(settingsSummary(panel, "店铺信息", [
    ["店铺名称", shop.name], ["营业状态", shop.status === "open" ? "营业中" : "已休息"],
    ["AI昵称", storeAssistantName(shop)], ["主题色", shop.theme_color],
    ["店铺Logo", shop.logo_url ? "已配置" : "使用默认标识"], ["店铺公告", shop.notice],
  ]), share);
  return box;
}

function statusField(value) {
  const wrap = h("label", "field");
  wrap.append(h("span", "", "营业状态"));
  const select = document.createElement("select");
  select.name = "status";
  [["open", "营业中"], ["closed", "停业"]].forEach(([val_, label]) => {
    const option = document.createElement("option");
    option.value = val_;
    option.textContent = label;
    if (val_ === value) option.selected = true;
    select.append(option);
  });
  wrap.append(select);
  return wrap;
}

function field(label, name, value, full = false, type = "input") {
  const wrap = h("label", full ? "field full" : "field");
  wrap.append(h("span", "", label));
  const input = type === "textarea" ? document.createElement("textarea") : document.createElement("input");
  if (type === "textarea") input.rows = 3;
  if (type === "password") input.type = "password";
  if (type === "color") {
    input.type = "color";
    input.style.height = "42px";
    input.style.padding = "4px";
    input.style.cursor = "pointer";
  }
  input.name = name;
  input.value = value || "";
  wrap.append(input);
  return wrap;
}

window.addEventListener("hashchange", render);
render();


async function couponsAdmin() {
  const rows = await api("/api/v1/b/coupons");
  const box = h("div", "coupons-admin");
  box.append(h("h1", "page-title", "优惠券管理"), h("p", "muted", "店铺商品通用，每人每券限领一张，每单限用一张；按优惠前商品金额判断门槛和包邮，不抵运费。发放后规则固定，可随时停用。"));
  const form = h("form", "form-grid coupon-admin-form");
  const addField = (title, name, type, value, min, max) => {
    const label = h("label"); label.append(h("span", "", title));
    const input = h("input"); input.name = name; input.type = type; input.required = true; input.value = value;
    if (min !== undefined) input.min = min;
    if (max !== undefined) input.max = max;
    if (type === "number") input.step = name === "total_count" ? "1" : ".01";
    if (name === "name") input.maxLength = 60;
    label.append(input); form.append(label);
  };
  const localDate = date => new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0,16);
  addField("券名称", "name", "text", "店铺满减券");
  addField("使用门槛（元，0为无门槛）", "threshold", "number", "99", 0, 1000000);
  addField("优惠金额（元）", "amount", "number", "10", .01, 1000000);
  addField("发放总量", "total_count", "number", "100", 1, 1000000);
  addField("开始时间", "starts_at", "datetime-local", localDate(new Date()));
  addField("结束时间", "ends_at", "datetime-local", localDate(new Date(Date.now() + 30 * 86400000)));
  const error = h("p", "muted");
  const save = h("button", "btn", "创建并发放"); save.type = "submit";
  form.append(save, error);
  form.addEventListener("submit", async event => {
    event.preventDefault(); save.disabled = true; error.textContent = "";
    try {
      await api("/api/v1/b/coupons", {method:"POST", body:JSON.stringify({name:val(form,"name"), threshold_cents:Math.round(Number(val(form,"threshold"))*100), amount_cents:Math.round(Number(val(form,"amount"))*100), total_count:Number(val(form,"total_count")), starts_at:new Date(val(form,"starts_at")).toISOString(), ends_at:new Date(val(form,"ends_at")).toISOString()})});
      toast("优惠券已发放，买家可领取", "ok"); render();
    } catch (err) { error.textContent = err.message; save.disabled = false; }
  });
  box.append(editorAction(`全部优惠券（${rows.length}）`, "＋ 新增优惠券", () => form));
  const list = h("div", "panel coupon-admin-list");
  const stateNames = {active: "发放中", scheduled: "未开始", expired: "已结束", exhausted: "已领完", disabled: "已停用"};
  const filter = h("div", "tabs coupon-state-tabs");
  const cards = [];
  const noMatch = h("p", "muted", "当前状态暂无优惠券");
  noMatch.hidden = true;
  Object.entries({all: "全部", ...stateNames}).forEach(([key, label]) => {
    const count = key === "all" ? rows.length : rows.filter(coupon => coupon.issuance_state === key).length;
    const button = h("button", key === "all" ? "on" : "", `${label}（${count}）`);
    button.addEventListener("click", () => {
      filter.querySelectorAll("button").forEach(node => node.classList.toggle("on", node === button));
      cards.forEach(({card, coupon}) => { card.hidden = key !== "all" && coupon.issuance_state !== key; });
      noMatch.hidden = !cards.length || cards.some(({card}) => !card.hidden);
    });
    filter.append(button);
  });
  box.append(filter);
  if (!rows.length) list.append(h("p", "muted", "还没有优惠券，创建后会同步到买家端。"));
  rows.forEach(c => {
    const card = h("div", "coupon-admin-row");
    const info = h("div");
    const condition = c.threshold_cents ? `满${c.threshold_cents/100}减${c.amount_cents/100}` : `立减${c.amount_cents/100}`;
    info.append(h("b", "", `${c.name} · ${condition}`), h("p", "muted", `${new Date(c.starts_at).toLocaleString()} 至 ${new Date(c.ends_at).toLocaleString()}`),
      h("p", "muted", `已领 ${c.claimed_count}/${c.total_count} · 剩余可领 ${c.remaining_count ?? Math.max(0, c.total_count - c.claimed_count)} · 锁定 ${c.reserved_count || 0} · 已核销 ${c.used_count} · ${stateNames[c.issuance_state] || (!c.enabled ? "已停用" : c.active ? "发放中" : "未开始或已结束")}`));
    const toggle = h("button", "btn-ghost", c.enabled ? "停用" : "启用");
    toggle.addEventListener("click", async () => {
      toggle.disabled = true;
      try { await api(`/api/v1/b/coupons/${c.id}`, {method:"PATCH", body:JSON.stringify({enabled:!c.enabled})}); render(); }
      catch (err) { toast(err.message); toggle.disabled = false; }
    });
    card.append(info, toggle); list.append(card);
    cards.push({card, coupon: c});
  });
  list.append(noMatch);
  box.append(list); return box;
}
