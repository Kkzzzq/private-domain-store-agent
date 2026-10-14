const api = createApi("token_b");
let me = null;
let shopInfo = null;
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

/**
 * 上移 / 下移。把重排后的整份顺序按 1..n 写回，
 * 比只跟邻居交换稳（两张序号相同时交换会互相抵消，点了没反应）。
 */
async function shiftRow(kind, rows, index, delta) {
  const target = index + delta;
  if (target < 0 || target >= rows.length) return false;
  const next = rows.slice();
  const [moved] = next.splice(index, 1);
  next.splice(target, 0, moved);
  for (let order = 0; order < next.length; order += 1) {
    if (next[order].sort_order === order + 1) continue;
    await api(`/api/v1/b/${kind}/${next[order].id}`, {
      method: "PATCH",
      body: JSON.stringify({ sort_order: order + 1 }),
    });
  }
  toast("顺序已更新", "ok");
  return true;
}

/** 一排「上移 / 下移」按钮，几处列表共用。 */
function orderButtons(kind, rows, index) {
  const wrap = h("div", "row order-buttons");
  const up = h("button", "", "上移");
  up.type = "button";
  up.disabled = index === 0;
  up.addEventListener("click", async () => {
    if (await shiftRow(kind, rows, index, -1)) render();
  });
  const down = h("button", "", "下移");
  down.type = "button";
  down.disabled = index === rows.length - 1;
  down.addEventListener("click", async () => {
    if (await shiftRow(kind, rows, index, 1)) render();
  });
  wrap.append(up, down);
  return wrap;
}

const MENU = [
  ["dashboard", "📊 经营概览"],
  ["products", "📦 商品管理"],
  ["categories", "🏷️ 分类标签"],
  ["tags", "🔖 商品标签"],
  ["orders", "🧾 订单管理"],
  ["home", "🎨 首页装修"],
  ["shop", "🏪 店铺设置"],
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
  if (!shopInfo) {
    try {
      shopInfo = await api("/api/v1/b/shop");
    } catch {
      shopInfo = null;
    }
  }
  // 先把页面内容备好，再搭外壳：页面里改了店铺信息（店名、主题色），
  // 顶栏这一次就能用上新值，不会慢一拍
  const main = h("main", "main");
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
  logo.append(h("span", "", "南"), document.createTextNode(shopInfo ? shopInfo.name : "商家后台"));
  bar.append(logo, h("span", "env", "商家工作台 · 演示环境"));
  bar.append(h("div", "spacer"));
  const user = h("div", "user");
  const preview = h("a", "link", "查看买家端 ↗");
  preview.href = shopInfo ? `/${shopInfo.share_path.replace(/^\//, "")}` : "/c.html?code=nanzhi";
  preview.target = "_blank";
  preview.style.color = "#ff8f1f";
  user.append(h("span", "", me ? `${me.nickname}` : ""), preview);
  const logout = h("button", "", "退出");
  logout.addEventListener("click", () => {
    sessionStorage.removeItem("token_b");
    me = null;
    shopInfo = null;
    render();
  });
  user.append(logout);
  bar.append(user);
  return bar;
}

function loginView() {
  const panel = h("form", "panel stack");
  panel.style.maxWidth = "380px";
  panel.style.margin = "80px auto";
  panel.append(h("h2", "", "商家工作台"));
  panel.append(h("p", "muted", "请使用商家账号登录"));
  panel.append(field("账号", "username", "merchant"), field("密码", "password", "merchant123", false, "password"));
  const error = h("p", "muted", "");
  const submit = h("button", "btn", "进入后台");
  submit.type = "submit";
  submit.style.width = "100%";
  panel.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const data = await api("/api/v1/auth/login", {
        method: "POST",
        body: JSON.stringify({ username: val(panel, "username"), password: val(panel, "password") }),
      });
      if (data.user.role !== "merchant") throw new Error("请使用商家账号");
      sessionStorage.setItem("token_b", data.access_token);
      me = data.user;
      toast(`欢迎回来，${data.user.nickname}`, "ok");
      render();
    } catch (err) {
      error.textContent = err.message;
    }
  });
  panel.append(error, submit);
  return panel;
}

function sidebar() {
  const side = h("aside", "side");
  side.append(h("div", "side-brand", "店铺管理"));
  MENU.forEach(([name, label]) => {
    const link = h("a", route().name === name ? "on" : "", label);
    link.href = `#/${name}`;
    side.append(link);
  });
  side.append(h("div", "spacer"));
  const user = h("div", "side-user");
  user.append(h("div", "", `当前账号：${me ? me.username : ""}`));
  const logout = h("button", "", "退出登录");
  logout.addEventListener("click", () => {
    sessionStorage.removeItem("token_b");
    me = null;
    shopInfo = null;
    render();
  });
  user.append(logout);
  side.append(user);
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
  header.append(h("h2", "", "智能运营助手"), close);
  panel.append(header, h("p", "muted", "商品 · 库存 · 订单 · 经营概览"));
  const log = h("div", "merchant-chat-log");
  const append = (data) => {
    log.append(h("p", data.text.startsWith("你：") ? "merchant-question" : "merchant-answer", data.text));
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
    const waiting = h("p", "muted", "正在查询…");
    log.append(waiting);
    try {
      const data = await api("/api/v1/b/chat", { method: "POST", body: JSON.stringify({ message, session_id: merchantSession || undefined }) });
      merchantSession = data.session_id;
      const reply = { text: `${data.answer}\n${data.mode === "fallback" ? "规则查询 · " : ""}${data.notices.join("；")}`, products: data.products };
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
async function homeAdmin(tab) {
  const current = tab || "banners";
  const box = h("div");
  box.append(h("h1", "page-title", "首页装修"));
  box.append(h("p", "page-sub", "买家端首页的轮播图、商品栏目和用户评价都在这里改，保存后刷新买家端就能看到"));

  const tabs = h("div", "tabs");
  [["banners", "轮播图"], ["sections", "商品栏目"], ["testimonials", "用户评价"], ["appearance", "首页样式"]].forEach(
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
  tint.append(new Option("主题色浅底（推荐）", "on"), new Option("纯白", "off"));
  tint.value = shop.strip_tint === false ? "off" : "on";
  tintWrap.append(tint);
  grid.append(tintWrap);
  panel.append(grid);

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
    if (!rows.length) promiseRows.append(h("p", "muted", "现在一条都没有，买家端会隐藏这一条"));
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
  submit.type = "submit";
  panel.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      shopInfo = await api("/api/v1/b/shop", {
        method: "PATCH",
        body: JSON.stringify({
          hero_height: Number(height.value),
          strip_tint: tint.value === "on",
          promises: rows.filter((row) => row.title.trim()).map((row) => ({ title: row.title.trim(), sub: row.sub.trim() })),
        }),
      });
      toast("样式已保存", "ok");
      render();
    } catch (err) {
      error.textContent = err.message;
    }
  });
  panel.append(error, submit);
  box.append(panel);
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
  list.append(h("h2", "panel-title", `轮播图（${banners.length}）`));
  if (!banners.length) list.append(h("p", "muted", "还没有轮播图，先在下面加一张"));
  banners.forEach((banner, index) => {
    list.append(bannerRow(banner, banners, index, onSale, sections));
  });
  list.append(h("p", "muted", "顺序按列表从上到下，买家端点右侧按钮就是按这个顺序翻"));

  box.append(list, bannerForm(onSale, sections));
  return box;
}

function bannerRow(banner, banners, index, products, sections) {
  const row = h("div", "banner-row");
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
  const up = h("button", "", "上移");
  up.disabled = index === 0;
  up.addEventListener("click", async () => {
    if (await shiftRow("banners", banners, index, -1)) render();
  });
  const down = h("button", "", "下移");
  down.disabled = index === banners.length - 1;
  down.addEventListener("click", async () => {
    if (await shiftRow("banners", banners, index, 1)) render();
  });
  const toggle = h("button", "", banner.enabled ? "隐藏" : "展示");
  toggle.addEventListener("click", async () => {
    await api(`/api/v1/b/banners/${banner.id}`, {
      method: "PATCH",
      body: JSON.stringify({ enabled: !banner.enabled }),
    });
    toast(banner.enabled ? "已隐藏" : "已展示", "ok");
    render();
  });
  const remove = h("button", "danger", "删除");
  remove.addEventListener("click", async () => {
    const ok = await confirmAction("删掉这张轮播图？", banner.title || "（没有标题）");
    if (!ok) return;
    try {
      await api(`/api/v1/b/banners/${banner.id}`, { method: "DELETE" });
      toast("已删除", "ok");
      render();
    } catch (error) {
      toast(error.message, "bad");
    }
  });
  ops.append(up, down, toggle, remove);
  row.append(image, words, state, ops);
  return row;
}

function bannerForm(products, sections) {
  const panel = h("form", "panel stack");
  panel.append(h("h2", "panel-title", "新增轮播图"));
  const grid = h("div", "form-grid");
  grid.append(imageField("横屏大图", "image_url", ""));
  grid.append(field("标题（大字）", "title", ""));
  grid.append(field("副标题", "subtitle", ""));
  panel.append(grid);

  const linkRow = h("div", "form-grid");
  const typeWrap = h("label", "field");
  typeWrap.append(h("span", "", "点击跳转"));
  const type = document.createElement("select");
  [["none", "不跳转，只展示"], ["product", "跳到商品详情"], ["section", "跳到某个栏目"]].forEach(([value, label]) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    type.append(option);
  });
  typeWrap.append(type);

  const valueWrap = h("label", "field");
  valueWrap.append(h("span", "", "跳转目标"));
  const target = document.createElement("select");
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
    target.disabled = type.value === "none";
  };
  type.addEventListener("change", fill);
  fill();
  valueWrap.append(target);
  linkRow.append(typeWrap, valueWrap);
  panel.append(linkRow);

  const error = h("p", "muted", "");
  const submit = h("button", "btn", "添加轮播图");
  submit.type = "submit";
  panel.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await api("/api/v1/b/banners", {
        method: "POST",
        body: JSON.stringify({
          image_url: val(panel, "image_url"),
          title: val(panel, "title"),
          subtitle: val(panel, "subtitle"),
          link_type: type.value,
          link_value: type.value === "none" ? "" : target.value,
        }),
      });
      toast("轮播图已添加", "ok");
      render();
    } catch (err) {
      error.textContent = err.message;
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
  list.append(h("h2", "panel-title", `商品栏目（${sections.length}）`));
  list.append(h("p", "muted", "买家端首页从上到下就是这个顺序：先推荐，再畅销榜，然后是自定义栏目"));
  if (!sections.length) list.append(h("p", "muted", "还没有栏目"));
  sections.forEach((section, index) => list.append(sectionRow(section, sections, index, onSale)));
  box.append(list, sectionForm(onSale));
  return box;
}

function sectionRow(section, sections, index, products) {
  const row = h("div", "sec-row");
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
  const up = h("button", "", "上移");
  up.disabled = index === 0;
  up.addEventListener("click", async () => {
    if (await shiftRow("sections", sections, index, -1)) render();
  });
  const down = h("button", "", "下移");
  down.disabled = index === sections.length - 1;
  down.addEventListener("click", async () => {
    if (await shiftRow("sections", sections, index, 1)) render();
  });
  const toggle = h("button", "", section.enabled ? "隐藏" : "展示");
  toggle.addEventListener("click", async () => {
    await api(`/api/v1/b/sections/${section.id}`, {
      method: "PATCH",
      body: JSON.stringify({ enabled: !section.enabled }),
    });
    render();
  });
  const edit = h("button", "", "改商品");
  edit.addEventListener("click", () => sectionEditor(section, products));
  const remove = h("button", "danger", "删除");
  remove.addEventListener("click", async () => {
    const ok = await confirmAction(`删掉栏目「${section.title}」？`, "栏目里的商品不会删，只是这一行不再展示。");
    if (!ok) return;
    try {
      await api(`/api/v1/b/sections/${section.id}`, { method: "DELETE" });
      toast("栏目已删除", "ok");
      render();
    } catch (error) {
      toast(error.message, "bad");
    }
  });
  ops.append(state, up, down, toggle, edit, remove);
  row.append(words, ops);
  return row;
}

function sectionEditor(section, products) {
  const dialog = h("div", "modal");
  const panel = h("form", "panel stack");
  panel.append(h("h2", "panel-title", `编辑「${section.title}」`));
  const picked = new Set(section.product_ids);
  const counter = h("p", "muted", "");
  const list = h("div", "pick-list");
  const paintCount = () => {
    counter.textContent = `已选 ${picked.size} / 6 件${picked.size ? "：首页按勾选顺序展示前 6 件" : ""}`;
  };
  products.forEach((product) => {
    const label = h("label", "pick-item");
    const check = document.createElement("input");
    check.type = "checkbox";
    check.className = "check";
    check.checked = picked.has(product.id);
    check.addEventListener("change", () => {
      if (check.checked && picked.size >= 6) {
        check.checked = false;
        toast("手工栏目最多选 6 件，多出来的不会展示", "bad");
        return;
      }
      if (check.checked) picked.add(product.id);
      else picked.delete(product.id);
      paintCount();
    });
    const thumb = document.createElement("img");
    thumb.src = cover(product.image_url);
    thumb.alt = product.name;
    const name = h("span", "", product.name);
    label.append(check, thumb, name);
    list.append(label);
  });
  paintCount();

  const error = h("p", "muted", "");
  const save = h("button", "btn", "保存");
  save.type = "submit";
  const close = h("button", "btn-ghost", "取消");
  close.type = "button";
  close.addEventListener("click", () => dialog.remove());
  const row = h("div", "row");
  row.append(save, close);
  panel.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await api(`/api/v1/b/sections/${section.id}`, {
        method: "PATCH",
        body: JSON.stringify({ product_ids: [...picked] }),
      });
      dialog.remove();
      toast("已保存", "ok");
      render();
    } catch (err) {
      error.textContent = err.message;
    }
  });
  panel.append(list, counter, error, row);
  dialog.append(panel);
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.remove();
  });
  // 和删除确认一样，按 Esc 也能关
  const onKey = (event) => {
    if (event.key === "Escape") {
      dialog.remove();
      document.removeEventListener("keydown", onKey);
    }
  };
  document.addEventListener("keydown", onKey);
  document.body.append(dialog);
}

function sectionForm(products) {
  const panel = h("form", "panel stack");
  panel.append(h("h2", "panel-title", "新增栏目"));
  const grid = h("div", "form-grid");
  grid.append(field("栏目标题", "title", ""), field("副标题", "subtitle", ""));
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
  grid.append(sourceWrap);
  panel.append(grid);

  const picked = new Set();
  const counter = h("p", "muted", "");
  const paintCount = () => {
    counter.textContent = `已选 ${picked.size} / 6 件`;
  };
  const list = h("div", "pick-list");
  products.forEach((product) => {
    const label = h("label", "pick-item");
    const check = document.createElement("input");
    check.type = "checkbox";
    check.className = "check";
    check.addEventListener("change", () => {
      if (check.checked && picked.size >= 6) {
        check.checked = false;
        toast("手工栏目最多选 6 件", "bad");
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
  const hint = h("p", "muted", "手工栏目最多选 6 件，买家端按勾选顺序展示；选「按销量自动」就不用勾");
  panel.append(h("div", "field-label", "手选商品"), counter, list, hint);

  const error = h("p", "muted", "");
  const submit = h("button", "btn", "添加栏目");
  submit.type = "submit";
  panel.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await api("/api/v1/b/sections", {
        method: "POST",
        body: JSON.stringify({
          title: val(panel, "title"),
          subtitle: val(panel, "subtitle"),
          source: source.value,
          product_ids: [...picked],
        }),
      });
      toast("栏目已添加", "ok");
      render();
    } catch (err) {
      error.textContent = err.message;
    }
  });
  panel.append(error, submit);
  return panel;
}

async function testimonialsAdmin() {
  const box = h("div");
  const rows = await api("/api/v1/b/testimonials");
  const list = h("div", "panel");
  list.append(h("h2", "panel-title", `用户评价（${rows.length}）`));
  list.append(h("p", "muted", "这些是首页底部流动展示的短评，可以自己写，也可以把买家的真实评价整理进来"));
  if (!rows.length) list.append(h("p", "muted", "还没有评价"));
  rows.forEach((row, index) => {
    const item = h("div", "quote-row");
    const words = h("div");
    words.style.flex = "1";
    const who = h("div", "row");
    who.append(h("b", "", row.nickname), ratingStars(row.rating));
    words.append(who, h("div", "muted", row.content));
    const ops = h("div", "ops");
    const state = h("span", `pill ${row.enabled ? "on" : "off"}`, row.enabled ? "展示中" : "已隐藏");
    const up = h("button", "", "上移");
    up.disabled = index === 0;
    up.addEventListener("click", async () => {
      if (await shiftRow("testimonials", rows, index, -1)) render();
    });
    const down = h("button", "", "下移");
    down.disabled = index === rows.length - 1;
    down.addEventListener("click", async () => {
      if (await shiftRow("testimonials", rows, index, 1)) render();
    });
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
        toast("已删除", "ok");
        render();
      } catch (error) {
        toast(error.message, "bad");
      }
    });
    ops.append(state, up, down, toggle, remove);
    item.append(words, ops);
    list.append(item);
  });

  const panel = h("form", "panel stack");
  panel.append(h("h2", "panel-title", "新增评价"));
  const grid = h("div", "form-grid");
  grid.append(field("昵称", "nickname", ""));
  const ratingWrap = h("label", "field");
  ratingWrap.append(h("span", "", "评分"));
  const rating = document.createElement("select");
  [5, 4, 3, 2, 1].forEach((value) => {
    const option = document.createElement("option");
    option.value = String(value);
    option.textContent = `${value} 星`;
    rating.append(option);
  });
  ratingWrap.append(rating);
  grid.append(ratingWrap);
  grid.append(field("评价内容", "content", "", true, "textarea"));
  panel.append(grid);

  const error = h("p", "muted", "");
  const submit = h("button", "btn", "添加评价");
  submit.type = "submit";
  panel.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await api("/api/v1/b/testimonials", {
        method: "POST",
        body: JSON.stringify({
          nickname: val(panel, "nickname"),
          content: val(panel, "content"),
          rating: Number(rating.value),
        }),
      });
      toast("评价已添加", "ok");
      render();
    } catch (err) {
      error.textContent = err.message;
    }
  });
  panel.append(error, submit);
  box.append(list, panel);
  return box;
}

/** 类目选择：选项来自后台维护的分类标签，也允许现场填个新的。 */
function categoryField(names, value) {
  const wrap = h("label", "field");
  wrap.append(h("span", "", "类目"));
  const input = document.createElement("input");
  input.name = "category";
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

/* ---------------- 分类标签：合集页左侧那排 tag 就是这里定的 ---------------- */
async function categoriesAdmin() {
  const box = h("div");
  box.append(h("h1", "page-title", "分类标签"));
  box.append(
    h(
      "p",
      "page-sub",
      "合集页左侧的筛选项、商品编辑里的类目选项都来自这套标签。名字随时可以改，改完挂在旧类目下的商品会一起跟过来。"
    )
  );

  const rows = await api("/api/v1/b/categories");
  const list = h("div", "panel");
  list.append(h("h2", "panel-title", `当前标签（${rows.length}）`));
  if (!rows.length) list.append(h("p", "muted", "还没有标签，先在下面加一个"));
  if (rows.length > 1) list.append(h("p", "muted", "标签顺序就是买家端看到的顺序，可以上下调整"));

  const move = async (index, delta) => {
    if (await shiftRow("categories", rows, index, delta)) render();
  };

  rows.forEach((row, index) => {
    const item = h("div", "quote-row");
    const input = document.createElement("input");
    input.className = "cat-name";
    input.value = row.name;

    const ops = h("div", "ops");
    const count = h("span", "pill", `${row.product_count} 件商品`);
    const save = h("button", "", "改名");
    save.addEventListener("click", async () => {
      const name = input.value.trim();
      if (!name || name === row.name) return;
      try {
        await api(`/api/v1/b/categories/${row.id}`, { method: "PATCH", body: JSON.stringify({ name }) });
        toast("已改名，旧类目下的商品一起改了", "ok");
        render();
      } catch (error) {
        toast(error.message, "bad");
      }
    });
    const up = h("button", "", "上移");
    up.disabled = index === 0;
    up.addEventListener("click", () => move(index, -1));
    const down = h("button", "", "下移");
    down.disabled = index === rows.length - 1;
    down.addEventListener("click", () => move(index, 1));
    const remove = h("button", "danger", "删除");
    remove.disabled = row.product_count > 0;
    remove.title = row.product_count > 0 ? "还有商品挂在这个标签下，先改掉再删" : "";
    remove.addEventListener("click", async () => {
      const ok = await confirmAction(`删掉分类「${row.name}」？`, "没有商品挂在它下面才可以删。");
      if (!ok) return;
      try {
        await api(`/api/v1/b/categories/${row.id}`, { method: "DELETE" });
        toast("已删除", "ok");
        render();
      } catch (error) {
        toast(error.message, "bad");
      }
    });
    ops.append(count, save, up, down, remove);
    item.append(input, ops);
    list.append(item);
  });

  const panel = h("form", "panel stack");
  panel.append(h("h2", "panel-title", "新增标签"));
  panel.append(h("p", "muted", "比如「家居」「餐具」「香氛」「文具」，短一点买家扫得快"));
  const grid = h("div", "form-grid");
  grid.append(field("标签名", "name", ""));
  panel.append(grid);

  const error = h("p", "muted", "");
  const submit = h("button", "btn", "添加标签");
  submit.type = "submit";
  panel.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await api("/api/v1/b/categories", { method: "POST", body: JSON.stringify({ name: val(panel, "name") }) });
      toast("标签已添加", "ok");
      render();
    } catch (err) {
      error.textContent = err.message;
    }
  });
  panel.append(error, submit);

  box.append(list, panel);
  return box;
}

/* ---------------- 商品标签：买家端卡片左上角那个角标 ---------------- */
async function tagsAdmin() {
  const box = h("div");
  box.append(h("h1", "page-title", "商品标签"));
  box.append(
    h(
      "p",
      "page-sub",
      "买家端商品卡左上角的角标（促销 / 爆款 / 新上线 …）就是这套标签。一件商品可以挂多个，卡片上显示排在最前面的那个。"
    )
  );

  const rows = await api("/api/v1/b/tags");
  const list = h("div", "panel");
  list.append(h("h2", "panel-title", `当前标签（${rows.length}）`));
  if (!rows.length) list.append(h("p", "muted", "还没有标签，先在下面加一个"));
  if (rows.length > 1) list.append(h("p", "muted", "顺序决定商品卡上显示哪一个，越靠前越优先"));

  const save = async (row, payload, done) => {
    try {
      await api(`/api/v1/b/tags/${row.id}`, { method: "PATCH", body: JSON.stringify(payload) });
      toast(done, "ok");
      render();
    } catch (error) {
      toast(error.message, "bad");
    }
  };

  const move = async (index, delta) => {
    if (await shiftRow("tags", rows, index, delta)) render();
  };

  rows.forEach((row, index) => {
    const item = h("div", "quote-row");
    const input = document.createElement("input");
    input.className = "cat-name";
    input.value = row.name;

    const color = document.createElement("input");
    color.type = "color";
    color.className = "tag-color";
    color.value = row.color || "#ff5000";

    // 预览：和买家端商品卡上那个角标一模一样的样式，改颜色即时跟着变
    const preview = h("span", "tag-preview", row.name);
    const paintPreview = () => preview.style.setProperty("--tag", color.value || row.color || "");
    color.addEventListener("input", paintPreview);
    paintPreview();

    const ops = h("div", "ops");
    const count = h("span", "pill", `${row.product_count} 件商品`);
    const rename = h("button", "", "保存");
    rename.addEventListener("click", () => {
      const name = input.value.trim();
      if (!name || (name === row.name && color.value === row.color)) return;
      save(row, { name, color: color.value }, "标签已更新");
    });
    const up = h("button", "", "上移");
    up.disabled = index === 0;
    up.addEventListener("click", () => move(index, -1));
    const down = h("button", "", "下移");
    down.disabled = index === rows.length - 1;
    down.addEventListener("click", () => move(index, 1));
    const remove = h("button", "danger", "删除");
    remove.addEventListener("click", async () => {
      const ok = await confirmAction(`删掉标签「${row.name}」？`, `挂过它的 ${row.product_count} 件商品会一起摘掉这个角标。`);
      if (!ok) return;
      try {
        await api(`/api/v1/b/tags/${row.id}`, { method: "DELETE" });
        toast("已删除，挂过它的商品也一起摘掉了", "ok");
        render();
      } catch (error) {
        toast(error.message, "bad");
      }
    });
    ops.append(count, rename, up, down, remove);
    item.append(input, color, preview, ops);
    list.append(item);
  });

  const panel = h("form", "panel stack");
  panel.append(h("h2", "panel-title", "新增标签"));
  panel.append(h("p", "muted", "两个字的短词最合适，比如「促销」「爆款」「新上线」"));
  const grid = h("div", "form-grid");
  grid.append(field("标签名", "name", ""));
  const colorWrap = h("label", "field");
  colorWrap.append(h("span", "", "底色"));
  const newColor = document.createElement("input");
  newColor.type = "color";
  newColor.name = "color";
  newColor.value = "#ff5000";
  colorWrap.append(newColor);
  grid.append(colorWrap);
  panel.append(grid);

  const error = h("p", "muted", "");
  const submit = h("button", "btn", "添加标签");
  submit.type = "submit";
  panel.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await api("/api/v1/b/tags", {
        method: "POST",
        body: JSON.stringify({ name: val(panel, "name"), color: newColor.value }),
      });
      toast("标签已添加", "ok");
      render();
    } catch (err) {
      error.textContent = err.message;
    }
  });
  panel.append(error, submit);

  box.append(list, panel);
  return box;
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
  addProduct.addEventListener("click", () => go("#/products/new"));
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
  const status = select("商品状态", [["", "全部状态"], ["on", "在售"], ["off", "下架"], ["banned", "禁售"]], productFilters.status);
  const category = select("商品类目", [["", "全部类目"], ...[...new Set(products.map(p => p.category).filter(Boolean))].map(name => [name, name])], productFilters.category);
  const stockFilter = select("库存筛选", [["", "全部库存"], ["low", "库存预警（≤5）"], ["zero", "已售罄"]], productFilters.stock);
  const sort = select("商品排序", [["default", "默认排序"], ["sales", "销量从高到低"], ["stock", "库存从低到高"], ["price", "价格从低到高"]], productFilters.sort);
  const reset = h("button", "btn-ghost", "重置");
  const add = h("button", "btn push", "＋ 发布商品");
  add.addEventListener("click", () => go("#/products/new"));
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
    [["全部商品", products.length, ""], ["在售商品", products.filter(p => p.status === "on").length, "on"], ["已下架", products.filter(p => p.status === "off").length, "off"], ["库存预警", products.filter(low).length, "low"]].forEach(([label, count, filter]) => {
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
    opsRow.append(edit);

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

async function productEditor(id) {
  const creating = id === "new";
  const box = h("div");
  box.append(h("h1", "page-title", creating ? "发布商品" : "编辑商品"));
  box.append(h("p", "page-sub", creating ? "新商品默认下架，确认好再上架" : "改动会立刻生效到买家端"));
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
  if (creating) {
    panel.append(h("h2", "panel-title", "首个规格"));
    const skuGrid = h("div", "form-grid");
    skuGrid.append(field("规格名", "spec", "默认"), field("价格", "price", "39"), field("库存", "stock", "10"));
    panel.append(skuGrid);
  }

  const error = h("p", "muted", "");
  const submit = h("button", "btn", creating ? "创建并保存" : "保存修改");
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
      };
      if (creating) {
        payload.skus = [
          { spec: val(panel, "spec"), price_yuan: Number(val(panel, "price")), stock: Number(val(panel, "stock")) },
        ];
        payload.status = "off";
        await api("/api/v1/b/products", { method: "POST", body: JSON.stringify(payload) });
        toast("商品已创建，记得上架", "ok");
      } else {
        await api(`/api/v1/b/products/${product.id}`, { method: "PATCH", body: JSON.stringify(payload) });
        toast("已保存", "ok");
      }
      go("#/products");
    } catch (err) {
      error.textContent = err.message;
    } finally {
      submit.disabled = false;
      submit.textContent = creating ? "创建并保存" : "保存修改";
    }
  });
  panel.append(error, submit);
  box.append(panel);

  if (!creating) {
    box.append(renderSkuPanel(product));
  }
  return box;
}

function renderSkuPanel(product, reload = render) {
  const panel = h("div", "panel");
  panel.append(h("h2", "panel-title", `规格与库存（${product.skus.length}）`));
  panel.append(h("p", "muted", "给规格单独配一张图，买家在详情页切规格（或点缩略图）时主图就换成这张"));
  const wrap = h("div", "table-wrap");
  const table = h("table", "table sku-table");
  const head = document.createElement("thead");
  const headRow = document.createElement("tr");
  ["规格", "规格图", "划线价", "售价", "库存", "状态", "操作"].forEach((text) => headRow.append(h("th", "", text)));
  head.append(headRow);
  const tbody = document.createElement("tbody");
  product.skus.forEach((sku) => {
    const tr = document.createElement("tr");
    const specCell = document.createElement("td");
    const specInput = document.createElement("input");
    specInput.className = "stock-input spec-input";
    specInput.value = sku.spec;
    specInput.maxLength = 40;
    specInput.setAttribute("aria-label", `${sku.spec} 规格名`);
    specCell.append(specInput);

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
        if (marketInput.value) payload.market_price_yuan = Number(marketInput.value);
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
    tbody.append(tr);
  });
  table.append(head, tbody);
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
  panel.append(addRow);
  return panel;
}

/** 规格表单的本地校验，先拦一次，省得拿英文的接口报错去给商家看。 */
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
  panel.append(h("p", "muted", `商品 ${money(order.goods_yuan)} · 运费 ${money(order.freight_yuan)}`), h("div", "order-detail-total", `订单金额 ${money(order.total_yuan)}`));
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
    statusField(shop.status),
    field("店铺 Logo 地址", "logo_url", shop.logo_url),
    field("主题色", "theme_color", shop.theme_color, false, "color"),
    field("店铺公告", "notice", shop.notice, true, "textarea")
  );
  panel.append(grid);
  const hint = h("p", "muted", "主题色会直接用在买家端的按钮、价格和标签上，改完刷新买家端就能看到");
  panel.append(hint);
  const error = h("p", "muted", "");
  const submit = h("button", "btn", "保存设置");
  submit.type = "submit";
  panel.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      shopInfo = await api("/api/v1/b/shop", {
        method: "PATCH",
        body: JSON.stringify({
          name: val(panel, "name"),
          notice: val(panel, "notice"),
          status: val(panel, "status") || "open",
          logo_url: val(panel, "logo_url"),
          theme_color: val(panel, "theme_color"),
        }),
      });
      toast("店铺设置已保存", "ok");
      render();
    } catch (err) {
      error.textContent = err.message;
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

  box.append(panel, share);
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
