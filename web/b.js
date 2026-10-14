const api = createApi("token_b");
let me = null;

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
  return url || "/covers/pillow.svg";
}

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
  const frame = h("div", "admin");
  frame.append(sidebar());
  const main = h("main", "main");
  try {
    main.append(await mainView());
  } catch (error) {
    main.append(h("div", "panel", error.message));
  }
  frame.append(main);
  root.append(frame);
}

function loginView() {
  const panel = h("form", "panel stack");
  panel.style.maxWidth = "400px";
  panel.style.margin = "72px auto";
  panel.append(h("h1", "", "商家后台"));
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
        body: JSON.stringify({ username: panel.username.value, password: panel.password.value }),
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
  const brand = h("div", "side-brand", "南枝手作");
  brand.append(h("small", "", "MERCHANT"));
  side.append(brand);
  [["dashboard", "经营概览"], ["products", "商品管理"], ["orders", "订单管理"], ["shop", "店铺设置"]].forEach(([name, label]) => {
    const link = h("a", route().name === name ? "on" : "", label);
    link.href = `#/${name}`;
    side.append(link);
  });
  side.append(h("div", "spacer"));
  const user = h("div", "side-user");
  user.append(h("div", "", me ? `${me.nickname}（${me.username}）` : ""));
  const logout = h("button", "side-item", "退出登录");
  logout.addEventListener("click", () => {
    sessionStorage.removeItem("token_b");
    me = null;
    render();
  });
  user.append(logout);
  side.append(user);
  return side;
}

async function mainView() {
  const current = route();
  if (current.name === "products") {
    return current.id ? productEditor(current.id) : productList();
  }
  if (current.name === "orders") return orderList(current.id);
  if (current.name === "shop") return shopForm();
  return dashboard();
}

async function dashboard() {
  const box = h("div");
  box.append(h("h1", "page-title", "经营概览"));
  box.append(h("p", "page-sub", "库存和订单状态一变，这里和买家端同时更新"));
  const data = await api("/api/v1/b/dashboard");
  const stats = h("div", "stats");
  const cards = [
    ["在售商品", data.on_sale, false],
    ["成交额", money(data.sales_yuan), true],
    ["待发货", data.pending_ship, false],
    ["待支付", data.pending_pay, false],
    ["已发货", data.shipped, false],
    ["下架商品", data.off_shelf, false],
    ["禁售商品", data.banned, false],
    ["商品总数", data.product_total, false],
  ];
  cards.forEach(([label, value, accent]) => {
    const card = h("div", accent ? "stat accent" : "stat");
    card.append(h("div", "k", label), h("div", "v", String(value)));
    stats.append(card);
  });
  box.append(stats);

  const quick = h("div", "panel");
  quick.append(h("h2", "panel-title", "常用操作"));
  const row = h("div", "row");
  const addProduct = h("button", "btn", "发布商品");
  addProduct.addEventListener("click", () => go("#/products/new"));
  const toOrders = h("button", "btn-ghost", "处理待发货订单");
  toOrders.addEventListener("click", () => go("#/orders/paid"));
  const toShop = h("button", "btn-ghost", "修改店铺公告");
  toShop.addEventListener("click", () => go("#/shop"));
  row.append(addProduct, toOrders, toShop);
  quick.append(row);
  box.append(quick);
  return box;
}

async function productList() {
  const box = h("div");
  box.append(h("h1", "page-title", "商品管理"));
  box.append(h("p", "page-sub", "上下架、禁售和价格库存都会立刻反映到买家端"));

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
  const add = h("button", "btn", "发布商品");
  add.addEventListener("click", () => go("#/products/new"));
  bar.append(keyword, status, search, add);
  box.append(bar);

  const host = h("div");
  box.append(host);

  async function load() {
    const products = await api(`/api/v1/b/products?keyword=${encodeURIComponent(keyword.value)}&status=${status.value}`);
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
  const table = h("table", "table");
  const head = document.createElement("thead");
  const headRow = document.createElement("tr");
  ["商品", "类目", "价格", "库存", "状态", "销量", "操作"].forEach((text) => headRow.append(h("th", "", text)));
  head.append(headRow);
  const body = document.createElement("tbody");
  products.forEach((product) => {
    const tr = document.createElement("tr");
    const info = document.createElement("td");
    const wrap = h("div", "row");
    const image = document.createElement("img");
    image.className = "thumb";
    image.src = cover(product.image_url);
    image.alt = product.name;
    const words = h("div");
    words.append(h("div", "", product.name));
    words.append(h("div", "muted", `${product.skus.length} 个规格`));
    wrap.append(image, words);
    info.append(wrap);

    const category = document.createElement("td");
    category.textContent = product.category || "-";
    const price = document.createElement("td");
    price.textContent = product.price_from == null ? "-" : money(product.price_from);
    const stock = document.createElement("td");
    stock.textContent = String(product.skus.reduce((sum, sku) => sum + sku.stock, 0));
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
          await api(`/api/v1/b/products/${product.id}/status`, { method: "POST", body: JSON.stringify({ action: act }) });
          toast(`${product.name} 已${label}`, "ok");
          render();
        } catch (error) {
          toast(error.message, "bad");
        }
      });
      opsRow.append(button);
    });
    ops.append(opsRow);

    tr.append(info, category, price, stock, state, sales, ops);
    body.append(tr);
  });
  table.append(head, body);
  return table;
}

async function productEditor(id) {
  const creating = id === "new";
  const box = h("div");
  box.append(h("h1", "page-title", creating ? "发布商品" : "编辑商品"));
  box.append(h("p", "page-sub", creating ? "新商品默认是下架状态，确认无误再上架" : "改动会立即生效到买家端"));
  const back = h("button", "btn-ghost", "← 返回商品列表");
  back.addEventListener("click", () => go("#/products"));
  box.append(back);

  const panel = h("form", "panel stack");
  panel.style.marginTop = "16px";
  let product = { name: "", category: "家居", description: "", image_url: "", skus: [] };
  if (!creating) {
    const products = await api("/api/v1/b/products");
    product = products.find((item) => String(item.id) === id);
    if (!product) return h("div", "panel", "没有找到这个商品");
  }

  panel.append(h("h2", "panel-title", "基本信息"));
  const grid = h("div", "form-grid");
  grid.append(
    field("商品名称", "name", product.name),
    field("类目", "category", product.category),
    field("图片地址", "image_url", product.image_url, true),
    field("商品说明", "description", product.description, true, "textarea")
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
      };
      if (creating) {
        payload.skus = [
          { spec: val(panel, "spec"), price_yuan: Number(val(panel, "price")), stock: Number(val(panel, "stock")) },
        ];
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

  if (!creating) {
    const skuPanel = h("div", "panel");
    skuPanel.append(h("h2", "panel-title", "规格与库存"));
    const table = h("table", "table");
    const head = document.createElement("thead");
    const headRow = document.createElement("tr");
    ["规格", "价格", "库存", "状态", "操作"].forEach((text) => headRow.append(h("th", "", text)));
    head.append(headRow);
    const tbody = document.createElement("tbody");
    product.skus.forEach((sku) => {
      const tr = document.createElement("tr");
      const priceCell = document.createElement("td");
      const priceInput = document.createElement("input");
      priceInput.value = sku.price_yuan;
      priceInput.style.width = "90px";
      priceInput.style.border = "1px solid var(--line)";
      priceInput.style.borderRadius = "6px";
      priceInput.style.padding = "6px 8px";
      priceCell.append(priceInput);
      const stockCell = document.createElement("td");
      const stockInput = document.createElement("input");
      stockInput.value = sku.stock;
      stockInput.style.width = "80px";
      stockInput.style.border = "1px solid var(--line)";
      stockInput.style.borderRadius = "6px";
      stockInput.style.padding = "6px 8px";
      stockCell.append(stockInput);
      const state = document.createElement("td");
      state.append(h("span", `pill ${sku.status}`, STATUS[sku.status] || sku.status));
      const ops = h("td");
      const opsRow = h("div", "ops");
      const save = h("button", "", "保存");
      save.addEventListener("click", async () => {
        try {
          await api(`/api/v1/b/skus/${sku.id}`, {
            method: "PATCH",
            body: JSON.stringify({ price_yuan: Number(priceInput.value), stock: Number(stockInput.value) }),
          });
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
      tr.append(h("td", "", sku.spec), priceCell, stockCell, state, ops);
      tbody.append(tr);
    });
    table.append(head, tbody);
    skuPanel.append(table);

    const addRow = h("div", "toolbar-inline");
    addRow.style.marginTop = "16px";
    const spec = document.createElement("input");
    spec.placeholder = "新规格名";
    const price = document.createElement("input");
    price.placeholder = "价格";
    const stock = document.createElement("input");
    stock.placeholder = "库存";
    const add = h("button", "btn-ghost", "添加规格");
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
    skuPanel.append(addRow);
    box.append(panel, skuPanel);
  } else {
    box.append(panel);
  }
  return box;
}

async function orderList(status) {
  const box = h("div");
  box.append(h("h1", "page-title", "订单管理"));
  box.append(h("p", "page-sub", "买家下单后这里能看到，付款后即可发货"));
  const tabs = h("div", "tabs");
  [["", "全部"], ["pending", "待支付"], ["paid", "待发货"], ["shipped", "已发货"], ["completed", "已完成"], ["cancelled", "已取消"]].forEach(([value, label]) => {
    const button = h("button", value === status ? "on" : "", label);
    button.addEventListener("click", () => go(value ? `#/orders/${value}` : "#/orders"));
    tabs.append(button);
  });
  box.append(tabs);

  const orders = await api(`/api/v1/b/orders?status=${status}`);
  if (!orders.length) {
    box.append(h("div", "panel empty", "这里还没有订单"));
    return box;
  }
  const table = h("table", "table");
  const head = document.createElement("thead");
  const headRow = document.createElement("tr");
  ["订单号", "买家", "商品", "地址", "金额", "状态", "操作"].forEach((text) => headRow.append(h("th", "", text)));
  head.append(headRow);
  const body = document.createElement("tbody");
  orders.forEach((order) => {
    const tr = document.createElement("tr");
    tr.append(h("td", "", order.order_no));
    tr.append(h("td", "", order.buyer_nickname || "-"));
    const goods = h("td");
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
    body.append(tr);
  });
  table.append(head, body);
  box.append(table);
  return box;
}

async function shopForm() {
  const shop = await api("/api/v1/b/shop");
  const box = h("div");
  box.append(h("h1", "page-title", "店铺设置"));
  box.append(h("p", "page-sub", "店铺信息和公告会显示在买家端的店头上"));
  const panel = h("form", "panel stack");
  panel.append(h("h2", "panel-title", "店铺信息"));
  const grid = h("div", "form-grid");
  grid.append(field("店铺名称", "name", shop.name), statusField(shop.status), field("店铺公告", "notice", shop.notice, true, "textarea"));
  panel.append(grid);

  const share = h("div", "panel");
  share.append(h("h2", "panel-title", "买家入口"));
  const link = h("a", "link", shop.share_path);
  link.href = shop.share_path;
  share.append(h("p", "muted", "买家从这条链接进店，只能看到你这家店"));
  share.append(link);

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
        }),
      });
      toast("店铺设置已保存", "ok");
      render();
    } catch (err) {
      error.textContent = err.message;
    }
  });
  panel.append(error, submit);
  box.append(panel, share);
  return box;
}

function statusField(value) {
  const wrap = h("label", "field");
  wrap.append(h("span", "", "营业状态"));
  const select = document.createElement("select");
  select.name = "status";
  [["open", "营业中"], ["closed", "停业"]].forEach(([val, label]) => {
    const option = document.createElement("option");
    option.value = val;
    option.textContent = label;
    if (val === value) option.selected = true;
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
  input.name = name;
  input.value = value || "";
  wrap.append(input);
  return wrap;
}

// 表单上的 name / status 等属性和 DOM 自带属性重名，统一从 elements 里取。
function val(form, name) {
  const node = form.elements.namedItem(name);
  return node ? String(node.value).trim() : "";
}

window.addEventListener("hashchange", render);
render();
