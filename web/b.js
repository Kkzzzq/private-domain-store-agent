const api = createApi("token_b");

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

async function render() {
  const root = document.querySelector("#app");
  root.replaceChildren();
  if (!loggedIn()) {
    root.append(loginView());
    return;
  }
  const frame = h("div", "admin");
  frame.append(sidebar(), await mainView());
  root.append(frame);
}

function loginView() {
  const form = h("form", "panel");
  form.style.maxWidth = "420px";
  form.style.margin = "48px auto";
  form.append(h("h1", "", "商家后台"), field("账号", "username", "merchant"), field("密码", "password", "merchant123"));
  const error = h("p", "error", "");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const data = await api("/api/v1/auth/login", { method: "POST", body: JSON.stringify({ username: form.username.value, password: form.password.value }) });
      if (data.user.role !== "merchant") throw new Error("请使用商家账号");
      sessionStorage.setItem("token_b", data.access_token);
      render();
    } catch (err) { error.textContent = err.message; }
  });
  form.append(error, h("button", "btn", "进入后台"));
  return form;
}

function sidebar() {
  const side = h("aside", "side");
  side.append(h("div", "logo", "南枝手作"));
  [["dashboard", "概览"], ["products", "商品"], ["orders", "订单"], ["shop", "店铺"]].forEach(([name, label]) => {
    const link = h("a", route().name === name ? "on" : "", label);
    link.href = `#/${name}`;
    side.append(link);
  });
  const logout = h("button", "", "退出");
  logout.addEventListener("click", () => { sessionStorage.removeItem("token_b"); render(); });
  side.append(logout);
  return side;
}

async function mainView() {
  const main = h("main", "main");
  const current = route();
  try {
    if (current.name === "products" && current.id) main.append(await productEditor(current.id));
    else if (current.name === "products") main.append(await productList());
    else if (current.name === "orders") main.append(await orderList(current.id));
    else if (current.name === "shop") main.append(await shopForm());
    else main.append(await dashboard());
  } catch (error) {
    main.append(h("p", "error", error.message));
  }
  return main;
}

async function dashboard() {
  const data = await api("/api/v1/b/dashboard");
  const box = h("div");
  box.append(h("h2", "", "店铺概览"));
  const stats = h("div", "stats");
  [["在售", data.on_sale], ["下架", data.off_shelf], ["禁售", data.banned], ["待发货", data.pending_ship], ["待支付", data.pending_pay], ["已发货", data.shipped], ["成交额", money(data.sales_yuan)]].forEach(([label, value]) => {
    const card = h("div", "stat");
    card.append(h("span", "muted", label), h("b", "", String(value)));
    stats.append(card);
  });
  box.append(stats);
  return box;
}

async function productList() {
  const box = h("div");
  const form = h("form", "row");
  const keyword = document.createElement("input");
  keyword.placeholder = "商品名";
  const status = document.createElement("select");
  [["", "全部状态"], ["on", "在售"], ["off", "下架"], ["banned", "禁售"]].forEach(([value, label]) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    status.append(option);
  });
  form.append(keyword, status, h("button", "btn", "筛选"));
  const tableHost = h("div");
  async function load() {
    const products = await api(`/api/v1/b/products?keyword=${encodeURIComponent(keyword.value)}&status=${status.value}`);
    tableHost.replaceChildren(productTable(products));
  }
  form.addEventListener("submit", (event) => { event.preventDefault(); load(); });
  const create = h("a", "btn", "发布商品");
  create.href = "#/products/new";
  box.append(h("h2", "", "商品管理"), form, create, tableHost);
  await load();
  return box;
}

function productTable(products) {
  const table = h("table", "table");
  const head = document.createElement("tr");
  ["商品", "类目", "价格", "状态", "销量", "操作"].forEach((text) => head.append(h("th", "", text)));
  table.append(head);
  products.forEach((product) => {
    const tr = document.createElement("tr");
    const name = document.createElement("td");
    name.textContent = product.name;
    const category = document.createElement("td");
    category.textContent = product.category;
    const price = document.createElement("td");
    price.textContent = product.price_from == null ? "-" : money(product.price_from);
    const state = document.createElement("td");
    state.textContent = { on: "在售", off: "下架", banned: "禁售" }[product.status] || product.status;
    const sales = document.createElement("td");
    sales.textContent = String(product.sales_count);
    const ops = document.createElement("td");
    const edit = h("a", "", "编辑");
    edit.href = `#/products/${product.id}`;
    ops.append(edit);
    statusActions(product.status).forEach(([action, label]) => {
      const button = h("button", "btn-ghost", label);
      button.addEventListener("click", async () => {
        await api(`/api/v1/b/products/${product.id}/status`, { method: "POST", body: JSON.stringify({ action }) });
        render();
      });
      ops.append(button);
    });
    tr.append(name, category, price, state, sales, ops);
    table.append(tr);
  });
  return table;
}

async function productEditor(id) {
  const creating = id === "new";
  const products = creating ? [] : await api("/api/v1/b/products");
  const product = creating ? { name: "", category: "家居", description: "", image_url: "", skus: [] } : products.find((item) => String(item.id) === id);
  if (!product) return h("p", "error", "没有找到这个商品");
  const box = h("form", "panel");
  box.append(h("h2", "", creating ? "发布商品" : `编辑 ${product.name}`));
  box.append(field("名称", "name", product.name), field("类目", "category", product.category), field("说明", "description", product.description), field("图片地址", "image_url", product.image_url));
  const error = h("p", "error", "");
  if (creating) {
    box.append(field("规格", "spec", "默认"), field("价格", "price", "39"), field("库存", "stock", "10"));
    box.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        await api("/api/v1/b/products", {
          method: "POST",
          body: JSON.stringify({
            name: box.name.value,
            category: box.category.value,
            description: box.description.value,
            image_url: box.image_url.value,
            skus: [{ spec: box.spec.value, price_yuan: Number(box.price.value), stock: Number(box.stock.value) }],
          }),
        });
        go("#/products");
      } catch (err) { error.textContent = err.message; }
    });
  } else {
    const skus = h("div");
    product.skus.forEach((sku) => skus.append(skuRow(product.id, sku)));
    const spec = document.createElement("input");
    spec.placeholder = "新规格";
    const price = document.createElement("input");
    price.placeholder = "价格";
    const stock = document.createElement("input");
    stock.placeholder = "库存";
    const add = h("button", "btn-ghost", "添加规格");
    add.type = "button";
    add.addEventListener("click", async () => {
      await api(`/api/v1/b/products/${product.id}/skus`, { method: "POST", body: JSON.stringify({ spec: spec.value, price_yuan: Number(price.value), stock: Number(stock.value) }) });
      render();
    });
    box.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        await api(`/api/v1/b/products/${product.id}`, {
          method: "PATCH",
          body: JSON.stringify({ name: box.name.value, category: box.category.value, description: box.description.value, image_url: box.image_url.value }),
        });
        go("#/products");
      } catch (err) { error.textContent = err.message; }
    });
    box.append(h("h3", "", "规格"), skus, h("div", "row"));
    box.lastChild.append(spec, price, stock, add);
  }
  box.append(error, h("button", "btn", "保存"));
  return box;
}

function skuRow(productId, sku) {
  const row = h("div", "row");
  const price = document.createElement("input");
  price.value = sku.price_yuan;
  const stock = document.createElement("input");
  stock.value = sku.stock;
  const save = h("button", "btn-ghost", "保存价格库存");
  save.type = "button";
  save.addEventListener("click", async () => {
    await api(`/api/v1/b/skus/${sku.id}`, { method: "PATCH", body: JSON.stringify({ price_yuan: Number(price.value), stock: Number(stock.value) }) });
    render();
  });
  row.append(h("span", "", `${sku.spec} · ${{ on: "在售", off: "下架", banned: "禁售" }[sku.status]}`), price, stock, save);
  statusActions(sku.status).forEach(([action, label]) => {
    const button = h("button", "btn-ghost", label);
    button.type = "button";
    button.addEventListener("click", async () => {
      await api(`/api/v1/b/skus/${sku.id}/status`, { method: "POST", body: JSON.stringify({ action }) });
      render();
    });
    row.append(button);
  });
  return row;
}

async function orderList(status) {
  const box = h("div");
  const tabs = h("div", "tabs");
  [["", "全部"], ["pending", "待支付"], ["paid", "待发货"], ["shipped", "已发货"], ["completed", "已完成"], ["cancelled", "已取消"]].forEach(([value, label]) => {
    const button = h("button", value === status ? "on" : "", label);
    button.addEventListener("click", () => go(value ? `#/orders/${value}` : "#/orders"));
    tabs.append(button);
  });
  const orders = await api(`/api/v1/b/orders?status=${status}`);
  const table = h("table", "table");
  orders.forEach((order) => {
    const tr = document.createElement("tr");
    [order.order_no, order.buyer_nickname, order.status_label, money(order.total_yuan), order.items.map((item) => `${item.product_name} ${item.sku_spec} x${item.quantity}`).join("，"), order.address].forEach((text) => {
      const td = document.createElement("td");
      td.textContent = text;
      tr.append(td);
    });
    const ops = document.createElement("td");
    if (order.status === "paid") {
      const button = h("button", "btn", "发货");
      button.addEventListener("click", async () => {
        await api(`/api/v1/b/orders/${order.order_no}/ship`, { method: "POST" });
        render();
      });
      ops.append(button);
    }
    tr.append(ops);
    table.append(tr);
  });
  box.append(h("h2", "", "订单"), tabs, table);
  return box;
}

async function shopForm() {
  const shop = await api("/api/v1/b/shop");
  const form = h("form", "panel");
  form.append(h("h2", "", "店铺设置"), field("店名", "name", shop.name), field("公告", "notice", shop.notice));
  const status = document.createElement("select");
  status.name = "status";
  [["open", "营业中"], ["closed", "停业"]].forEach(([value, label]) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    if (shop.status === value) option.selected = true;
    status.append(option);
  });
  const statusField = h("label", "field", "营业状态");
  statusField.append(status);
  const link = h("p", "", "");
  const anchor = h("a", "", shop.share_path);
  anchor.href = shop.share_path;
  link.append("买家入口：", anchor);
  const error = h("p", "error", "");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await api("/api/v1/b/shop", { method: "PATCH", body: JSON.stringify({ name: form.name.value, notice: form.notice.value, status: status.value }) });
      error.textContent = "已保存，买家端会读到同一份公告和营业状态";
    } catch (err) { error.textContent = err.message; }
  });
  form.append(statusField, link, error, h("button", "btn", "保存"));
  return form;
}

function field(label, name, value) {
  const wrap = h("label", "field", label);
  const input = name === "description" || name === "notice" ? document.createElement("textarea") : document.createElement("input");
  input.name = name;
  input.value = value || "";
  if (name === "password") input.type = "password";
  wrap.append(input);
  return wrap;
}

window.addEventListener("hashchange", render);
render();
