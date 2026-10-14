const api = createApi("token_b");
let me = null;
let shopInfo = null;

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

const MENU = [
  ["dashboard", "📊 经营概览"],
  ["products", "📦 商品管理"],
  ["categories", "🏷️ 分类标签"],
  ["orders", "🧾 订单管理"],
  ["home", "🎨 首页装修"],
  ["shop", "🏪 店铺设置"],
];

async function render() {
  const root = document.querySelector("#app");
  root.replaceChildren();
  if (!loggedIn()) {
    root.append(loginView());
    return;
  }
  if (!me) {
    try {
      me = await api("/api/v1/auth/me");
    } catch {
      sessionStorage.removeItem("token_b");
      root.append(loginView());
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
  const frame = h("div", "admin");
  frame.append(topBar());
  const body = h("div", "admin-body");
  body.append(sidebar());
  const main = h("main", "main");
  try {
    main.append(await mainView());
  } catch (error) {
    main.append(h("div", "panel", error.message));
  }
  body.append(main);
  frame.append(body);
  root.append(frame);
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
  panel.append(h("p", "muted", "演示账号 merchant / merchant123"));
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
  if (current.name === "products") return current.id ? productEditor(current.id) : productList();
  if (current.name === "categories") return categoriesAdmin();
  if (current.name === "orders") return orderList(current.id);
  if (current.name === "home") return homeAdmin(current.id);
  if (current.name === "shop") return shopForm();
  return dashboard();
}

/** 商家自己传图，成功返回可直接用的路径。 */
async function uploadImage(file) {
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
  wrap.append(h("span", "", label));
  const row = h("div", "row");
  const input = document.createElement("input");
  input.name = name;
  input.value = value || "";
  input.placeholder = "/covers/xxx.jpg";
  input.style.flex = "1";
  const pick = document.createElement("button", "btn-ghost btn-mini", "上传图片");
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
    preview.src = input.value || "/covers/hero.jpg";
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
  [["banners", "轮播图"], ["sections", "商品栏目"], ["testimonials", "用户评价"]].forEach(([value, label]) => {
    const button = h("button", value === current ? "on" : "", label);
    button.addEventListener("click", () => go(`#/home/${value}`));
    tabs.append(button);
  });
  box.append(tabs);

  if (current === "sections") box.append(await sectionsAdmin());
  else if (current === "testimonials") box.append(await testimonialsAdmin());
  else box.append(await bannersAdmin());
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
  const move = async (delta) => {
    const other = banners[index + delta];
    if (!other) return;
    // 和相邻的一张交换顺序，避免两张用同一个顺序值
    const mine = banner.sort_order;
    const theirs = other.sort_order;
    await api(`/api/v1/b/banners/${other.id}`, { method: "PATCH", body: JSON.stringify({ sort_order: mine }) });
    await api(`/api/v1/b/banners/${banner.id}`, { method: "PATCH", body: JSON.stringify({ sort_order: theirs }) });
    render();
  };
  const up = h("button", "", "上移");
  up.disabled = index === 0;
  up.addEventListener("click", () => move(-1));
  const down = h("button", "", "下移");
  down.disabled = index === banners.length - 1;
  down.addEventListener("click", () => move(1));
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
    await api(`/api/v1/b/banners/${banner.id}`, { method: "DELETE" });
    toast("已删除", "ok");
    render();
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
  sections.forEach((section) => list.append(sectionRow(section, onSale)));
  box.append(list, sectionForm(onSale));
  return box;
}

function sectionRow(section, products) {
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
    await api(`/api/v1/b/sections/${section.id}`, { method: "DELETE" });
    toast("栏目已删除", "ok");
    render();
  });
  ops.append(state, toggle, edit, remove);
  row.append(words, ops);
  return row;
}

function sectionEditor(section, products) {
  const dialog = h("div", "modal");
  const panel = h("form", "panel stack");
  panel.append(h("h2", "panel-title", `编辑「${section.title}」`));
  const picked = new Set(section.product_ids);
  const list = h("div", "pick-list");
  products.forEach((product) => {
    const label = h("label", "pick-item");
    const check = document.createElement("input");
    check.type = "checkbox";
    check.className = "check";
    check.checked = picked.has(product.id);
    check.addEventListener("change", () => {
      if (check.checked) picked.add(product.id);
      else picked.delete(product.id);
    });
    const thumb = document.createElement("img");
    thumb.src = cover(product.image_url);
    thumb.alt = product.name;
    const name = h("span", "", product.name);
    label.append(check, thumb, name);
    list.append(label);
  });

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
  panel.append(list, error, row);
  dialog.append(panel);
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.remove();
  });
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
  const list = h("div", "pick-list");
  products.forEach((product) => {
    const label = h("label", "pick-item");
    const check = document.createElement("input");
    check.type = "checkbox";
    check.className = "check";
    check.addEventListener("change", () => {
      if (check.checked) picked.add(product.id);
      else picked.delete(product.id);
    });
    const thumb = document.createElement("img");
    thumb.src = cover(product.image_url);
    thumb.alt = product.name;
    label.append(check, thumb, h("span", "", product.name));
    list.append(label);
  });
  const hint = h("p", "muted", "手工栏目最多选 6 件，超出只取前 6");
  panel.append(h("div", "field-label", "手选商品"), list, hint);

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
  rows.forEach((row) => {
    const item = h("div", "quote-row");
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
      await api(`/api/v1/b/testimonials/${row.id}`, { method: "DELETE" });
      toast("已删除", "ok");
      render();
    });
    ops.append(state, toggle, remove);
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
    const target = index + delta;
    if (target < 0 || target >= rows.length) return;
    const next = rows.slice();
    const [moved] = next.splice(index, 1);
    next.splice(target, 0, moved);
    // 整批写回顺序，避免只换两个导致序号打架
    for (let order = 0; order < next.length; order += 1) {
      if (next[order].sort_order === order + 1) continue;
      await api(`/api/v1/b/categories/${next[order].id}`, {
        method: "PATCH",
        body: JSON.stringify({ sort_order: order + 1 }),
      });
    }
    toast("顺序已更新", "ok");
    render();
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
  const box = h("div");
  box.append(h("h1", "page-title", "商品管理"));
  box.append(h("p", "page-sub", "上下架、禁售、价格和库存的改动会立刻同步到买家端"));

  const bar = h("div", "toolbar-inline");
  const keyword = document.createElement("input");
  keyword.placeholder = "搜索商品名";
  const status = document.createElement("select");
  [["", "全部状态"], ["on", "在售"], ["off", "下架"], ["banned", "禁售"]].forEach(([value, label]) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    status.append(option);
  });
  const search = h("button", "btn-ghost", "筛选");
  const add = h("button", "btn push", "＋ 发布商品");
  add.addEventListener("click", () => go("#/products/new"));
  bar.append(keyword, status, search, add);
  box.append(bar);

  const host = h("div");
  box.append(host);

  async function load() {
    const products = await api(
      `/api/v1/b/products?keyword=${encodeURIComponent(keyword.value)}&status=${status.value}`
    );
    host.replaceChildren(products.length ? productTable(products) : h("div", "panel empty", "没有匹配的商品"));
  }
  search.addEventListener("click", load);
  keyword.addEventListener("keydown", (event) => {
    if (event.key === "Enter") load();
  });
  await load();
  return box;
}

function productTable(products) {
  const wrap = h("div", "table-wrap");
  const table = h("table", "table");
  const head = document.createElement("thead");
  const headRow = document.createElement("tr");
  ["商品", "类目", "价格", "库存", "状态", "销量", "操作"].forEach((text) => headRow.append(h("th", "", text)));
  head.append(headRow);
  const body = document.createElement("tbody");
  products.forEach((product) => {
    const tr = document.createElement("tr");
    const info = document.createElement("td");
    const row = h("div", "row");
    const image = document.createElement("img");
    image.className = "thumb";
    image.src = cover(product.image_url);
    image.alt = product.name;
    const words = h("div");
    words.append(h("div", "name", product.name));
    words.append(h("div", "muted", `${product.skus.length} 个规格`));
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
    statusActions(product.status).forEach(([act, label]) => {
      const button = h("button", act === "ban" ? "danger" : "", label);
      button.addEventListener("click", async () => {
        try {
          await api(`/api/v1/b/products/${product.id}/status`, {
            method: "POST",
            body: JSON.stringify({ action: act }),
          });
          toast(`${product.name} 已${label}`, "ok");
          render();
        } catch (error) {
          toast(error.message, "bad");
        }
      });
      opsRow.append(button);
    });
    ops.append(opsRow);

    tr.append(info, category, price, stockCell, state, sales, ops);
    body.append(tr);
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
  try {
    catNames = (await api("/api/v1/b/categories")).map((item) => item.name);
  } catch {
    catNames = [];
  }

  panel.append(h("h2", "panel-title", "基本信息"));
  const grid = h("div", "form-grid");
  grid.append(
    field("商品名称", "name", product.name),
    categoryField(catNames, product.category),
    field("图片地址", "image_url", product.image_url, true),
    field("每人限购（0 表示不限）", "limit_per_user", String(product.limit_per_user ?? 0)),    field("商品说明", "description", product.description, true, "textarea")
  );
  panel.append(grid);
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
    try {
      const payload = {
        name: val(panel, "name"),
        category: val(panel, "category"),
        description: val(panel, "description"),
        image_url: val(panel, "image_url"),
        limit_per_user: Number(val(panel, "limit_per_user") || 0),
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
    }
  });
  panel.append(error, submit);
  box.append(panel);

  if (!creating) {
    box.append(renderSkuPanel(product));
  }
  return box;
}

function renderSkuPanel(product) {
  const panel = h("div", "panel");
  panel.append(h("h2", "panel-title", `规格与库存（${product.skus.length}）`));
  const wrap = h("div", "table-wrap");
  const table = h("table", "table");
  const head = document.createElement("thead");
  const headRow = document.createElement("tr");
  ["规格", "划线价", "售价", "库存", "状态", "操作"].forEach((text) => headRow.append(h("th", "", text)));
  head.append(headRow);
  const tbody = document.createElement("tbody");
  product.skus.forEach((sku) => {
    const tr = document.createElement("tr");
    tr.append(h("td", "", sku.spec));

    const marketCell = document.createElement("td");
    const marketInput = document.createElement("input");
    marketInput.className = "stock-input";
    marketInput.value = sku.market_price_yuan ?? "";
    marketInput.placeholder = "不设";
    marketCell.append(marketInput);

    const priceCell = document.createElement("td");
    const priceInput = document.createElement("input");
    priceInput.className = "stock-input";
    priceInput.value = sku.price_yuan;
    priceCell.append(priceInput);

    const stockCell = document.createElement("td");
    const stockInput = document.createElement("input");
    stockInput.className = "stock-input";
    stockInput.value = sku.stock;
    if (sku.status === "on" && sku.stock <= 5) stockInput.classList.add("low");
    stockCell.append(stockInput);

    const state = document.createElement("td");
    state.append(h("span", `pill ${sku.status}`, STATUS[sku.status] || sku.status));
    const ops = h("td");
    const opsRow = h("div", "ops");
    const save = h("button", "", "保存");
    save.addEventListener("click", async () => {
      try {
        const payload = { price_yuan: Number(priceInput.value), stock: Number(stockInput.value) };
        if (marketInput.value) payload.market_price_yuan = Number(marketInput.value);
        await api(`/api/v1/b/skus/${sku.id}`, { method: "PATCH", body: JSON.stringify(payload) });
        toast(`${sku.spec} 已更新`, "ok");
        render();
      } catch (error) {
        toast(error.message, "bad");
      }
    });
    opsRow.append(save);
    statusActions(sku.status).forEach(([act, label]) => {
      const button = h("button", act === "ban" ? "danger" : "", label);
      button.addEventListener("click", async () => {
        try {
          await api(`/api/v1/b/skus/${sku.id}/status`, { method: "POST", body: JSON.stringify({ action: act }) });
          toast(`${sku.spec} 已${label}`, "ok");
          render();
        } catch (error) {
          toast(error.message, "bad");
        }
      });
      opsRow.append(button);
    });
    ops.append(opsRow);
    tr.append(marketCell, priceCell, stockCell, state, ops);
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
    try {
      await api(`/api/v1/b/products/${product.id}/skus`, {
        method: "POST",
        body: JSON.stringify({ spec: spec.value, price_yuan: Number(price.value), stock: Number(stock.value) }),
      });
      toast("规格已添加", "ok");
      render();
    } catch (error) {
      toast(error.message, "bad");
    }
  });
  addRow.append(spec, price, stock, add);
  panel.append(addRow);
  return panel;
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
  const wrap = h("div", "table-wrap");
  const table = h("table", "table");
  const head = document.createElement("thead");
  const headRow = document.createElement("tr");
  const headCheck = h("th");
  const allCheck = document.createElement("input");
  allCheck.type = "checkbox";
  allCheck.className = "check";
  const shippable = orders.filter((order) => order.status === "paid").map((order) => order.order_no);
  headCheck.append(allCheck);
  headRow.append(headCheck);
  ["订单号", "买家", "商品", "收货信息", "金额", "状态", "操作"].forEach((text) => headRow.append(h("th", "", text)));
  head.append(headRow);

  const tbody = h("tbody");
  orders.forEach((order) => {
    const tr = document.createElement("tr");
    const checkCell = h("td");
    if (order.status === "paid") {
      const check = document.createElement("input");
      check.type = "checkbox";
      check.className = "check";
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
    if (order.status === "paid") {
      const ship = h("button", "", "发货");
      ship.addEventListener("click", async () => {
        try {
          await api(`/api/v1/b/orders/${order.order_no}/ship`, { method: "POST" });
          toast(`${order.order_no} 已发货`, "ok");
          render();
        } catch (error) {
          toast(error.message, "bad");
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
    }
  });
  const syncBatch = () => {
    batchButton.disabled = picked.size === 0;
    batchButton.textContent = picked.size ? `批量发货（${picked.size}）` : "批量发货";
  };
  allCheck.addEventListener("change", () => {
    picked.clear();
    if (allCheck.checked) shippable.forEach((orderNo) => picked.add(orderNo));
    tbody.querySelectorAll("input[type=checkbox]").forEach((node) => {
      if (!node.disabled) node.checked = allCheck.checked;
    });
    syncBatch();
  });
  batchBar.append(batchButton, batchHint);
  box.append(wrap, batchBar);
  return box;
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
      await api("/api/v1/b/shop", {
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
