const code = new URLSearchParams(location.search).get("code") || "nanzhi";
const api = createApi("token_c");
let shop = null;
let keyword = "";
let category = "";
let sort = "default";
let sessionId = "";
let chatLines = [];

function h(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

function route() {
  const parts = (location.hash || "#/").slice(1).split("/").filter(Boolean);
  return { name: parts[0] || "home", id: parts[1] || "" };
}

function go(hash) {
  if (location.hash === hash) render();
  else location.hash = hash;
}

function loggedIn() {
  return Boolean(sessionStorage.getItem("token_c"));
}

async function render() {
  const root = document.querySelector("#app");
  root.replaceChildren();
  if (!shop) {
    try {
      shop = await api(`/api/v1/c/shops/${code}`);
    } catch (error) {
      root.append(h("p", "error", error.message));
      return;
    }
  }
  root.append(renderHeader());
  const page = h("main", "wrap");
  page.append(await renderView());
  root.append(page, renderChat());
}

function renderHeader() {
  const bar = h("header", "topbar");
  const logo = h("a", "logo", shop.name);
  logo.href = "#/";
  const form = h("form", "search");
  const input = document.createElement("input");
  input.placeholder = "搜索本店商品";
  input.value = keyword;
  const button = h("button", "", "搜索");
  form.append(input, button);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    keyword = input.value.trim();
    go("#/");
  });
  const links = h("nav", "nav-links");
  const orders = h("a", "", "我的订单");
  orders.href = "#/orders";
  const cart = h("a", "", "购物车");
  cart.href = "#/cart";
  links.append(orders, cart);
  const account = h("button", "btn-ghost", loggedIn() ? "退出" : "买家登录");
  account.addEventListener("click", () => {
    if (loggedIn()) {
      sessionStorage.removeItem("token_c");
      render();
    } else loginModal();
  });
  bar.append(logo, form, links, account);
  return bar;
}

async function renderView() {
  const current = route();
  if (current.name === "product") return renderProduct(current.id);
  if (current.name === "cart") return renderCart();
  if (current.name === "checkout") return renderCheckout();
  if (current.name === "orders") return renderOrders(current.id);
  return renderHome();
}

async function renderHome() {
  const box = h("div");
  if (shop.notice) box.append(h("div", "notice", shop.notice));
  if (shop.status === "closed") box.append(h("div", "notice", "店铺已停业，暂时不能购买。"));
  const categories = await api(`/api/v1/c/shops/${code}/categories`);
  const chips = h("div", "cats");
  [["", "全部"], ...categories.map((item) => [item, item])].forEach(([value, label]) => {
    const button = h("button", value === category ? "on" : "", label);
    button.addEventListener("click", () => {
      category = value;
      render();
    });
    chips.append(button);
  });
  const sorts = h("div", "cats");
  [["default", "综合"], ["sales", "销量"], ["price_asc", "价格升序"], ["price_desc", "价格降序"]].forEach(([value, label]) => {
    const button = h("button", value === sort ? "on" : "", label);
    button.addEventListener("click", () => {
      sort = value;
      render();
    });
    sorts.append(button);
  });
  const query = new URLSearchParams({ keyword, category, sort });
  const products = await api(`/api/v1/c/shops/${code}/products?${query}`);
  const grid = h("div", "grid");
  products.forEach((product) => grid.append(productCard(product)));
  if (!products.length) grid.append(h("p", "muted", "没有找到商品"));
  box.append(chips, sorts, grid);
  return box;
}

function productCard(product) {
  const card = h("a", "card");
  card.href = `#/product/${product.id}`;
  const image = document.createElement("img");
  image.src = product.image_url || "/covers/pillow.svg";
  image.alt = product.name;
  const title = h("h3", "", product.name);
  const price = h("div", "price");
  price.append(h("small", "", "¥"), document.createTextNode(Number(product.price_from || 0).toFixed(2)));
  card.append(image, title, price, h("div", "muted", `已售 ${product.sales_count}`));
  return card;
}

async function renderProduct(id) {
  const box = h("div", "detail");
  let product;
  try {
    product = await api(`/api/v1/c/shops/${code}/products/${id}`);
  } catch (error) {
    return h("p", "error", error.message);
  }
  const image = document.createElement("img");
  image.className = "cover";
  image.src = product.image_url || "/covers/pillow.svg";
  image.alt = product.name;
  const info = h("div");
  info.append(h("h2", "", product.name), h("p", "muted", product.description));
  const price = h("div", "price");
  let current = product.skus[0];
  const priceText = h("span", "", "");
  const stockText = h("p", "muted", "");
  function paint() {
    priceText.textContent = current ? money(current.price_yuan) : "暂无规格";
    stockText.textContent = current ? `库存 ${current.stock} · ${current.purchasable ? "可购买" : "暂时不能买"}` : "";
  }
  price.append(priceText);
  const specs = h("div", "sku-list");
  product.skus.forEach((sku) => {
    const button = h("button", sku === current ? "on" : "", sku.spec);
    button.addEventListener("click", () => {
      current = sku;
      specs.querySelectorAll("button").forEach((item) => item.classList.remove("on"));
      button.classList.add("on");
      paint();
    });
    specs.append(button);
  });
  const qtyInput = document.createElement("input");
  qtyInput.value = "1";
  const qty = h("div", "qty");
  const minus = h("button", "", "-");
  const plus = h("button", "", "+");
  minus.addEventListener("click", () => { qtyInput.value = String(Math.max(1, Number(qtyInput.value) - 1)); });
  plus.addEventListener("click", () => { qtyInput.value = String(Math.min(20, Number(qtyInput.value) + 1)); });
  qty.append(minus, qtyInput, plus);
  const actions = h("div", "actions");
  const add = h("button", "btn-line", "加入购物车");
  const buy = h("button", "btn-price", "立即购买");
  const error = h("p", "error", "");
  add.addEventListener("click", async () => {
    error.textContent = "";
    if (!requireLogin()) return;
    try {
      await api(`/api/v1/c/shops/${code}/cart`, { method: "POST", body: JSON.stringify({ sku_id: current.id, quantity: Number(qtyInput.value) }) });
      error.textContent = "已加入购物车";
    } catch (err) { error.textContent = err.message; }
  });
  buy.addEventListener("click", () => {
    if (!requireLogin()) return;
    sessionStorage.setItem("buy_now", JSON.stringify({ sku_id: current.id, quantity: Number(qtyInput.value), name: product.name, spec: current.spec, price_yuan: current.price_yuan }));
    go("#/checkout");
  });
  actions.append(add, buy);
  info.append(price, h("p", "", "规格"), specs, h("p", "", "数量"), qty, stockText, actions, error);
  paint();
  box.append(image, info);
  return box;
}

async function renderCart() {
  if (!requireLogin()) return h("p", "", "请先买家登录");
  const cart = await api(`/api/v1/c/shops/${code}/cart`);
  const box = h("div");
  box.append(h("h2", "", "购物车"));
  if (!cart.items.length) {
    box.append(h("p", "muted", "购物车是空的"));
    return box;
  }
  const table = h("table", "table");
  cart.items.forEach((item) => {
    const tr = document.createElement("tr");
    const name = document.createElement("td");
    name.textContent = `${item.product_name} / ${item.spec}${item.available ? "" : "（" + item.reason + "）"}`;
    const price = document.createElement("td");
    price.textContent = money(item.price_yuan);
    const qty = document.createElement("td");
    qty.textContent = `x${item.quantity}`;
    const ops = document.createElement("td");
    const remove = h("button", "btn-ghost", "删除");
    remove.addEventListener("click", async () => {
      await api(`/api/v1/c/cart/${item.id}`, { method: "DELETE" });
      render();
    });
    ops.append(remove);
    tr.append(name, price, qty, ops);
    table.append(tr);
  });
  const summary = h("p", "", `商品 ${money(cart.goods_yuan)}，运费 ${money(cart.freight_yuan)}，合计 ${money(cart.total_yuan)}。满 99 元包邮。`);
  const checkout = h("button", "btn", "去结算");
  checkout.addEventListener("click", () => {
    sessionStorage.removeItem("buy_now");
    go("#/checkout");
  });
  box.append(table, summary, checkout);
  return box;
}

async function renderCheckout() {
  if (!requireLogin()) return h("p", "", "请先买家登录");
  const addresses = await api("/api/v1/c/addresses");
  const buyNow = JSON.parse(sessionStorage.getItem("buy_now") || "null");
  const box = h("div", "panel");
  box.append(h("h2", "", "确认订单"));
  const addressBox = h("div", "stack");
  let selected = addresses.find((item) => item.is_default) || addresses[0];
  addresses.forEach((item) => {
    const button = h("button", "btn-ghost", `${item.receiver} ${item.phone} ${item.region}${item.detail}`);
    if (selected && item.id === selected.id) button.classList.add("on");
    button.addEventListener("click", () => { selected = item; render(); });
    addressBox.append(button);
  });
  const form = h("form");
  form.append(
    labeled("收货人", "receiver", selected ? selected.receiver : "小满"),
    labeled("手机", "phone", selected ? selected.phone : "13800001111"),
    labeled("地址", "address", selected ? `${selected.region}${selected.detail}` : "长沙市岳麓区示范路 1 号"),
  );
  const line = h("p", "", buyNow ? `${buyNow.name} ${buyNow.spec} x${buyNow.quantity}` : "将结算购物车里当前可购买的商品");
  const error = h("p", "error", "");
  const submit = h("button", "btn-price", "提交订单");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    error.textContent = "";
    const payload = {
      receiver: form.receiver.value,
      phone: form.phone.value,
      address: form.address.value,
    };
    try {
      const order = buyNow
        ? await api(`/api/v1/c/shops/${code}/orders`, { method: "POST", body: JSON.stringify({ ...payload, sku_id: buyNow.sku_id, quantity: buyNow.quantity }) })
        : await api(`/api/v1/c/shops/${code}/cart/checkout`, { method: "POST", body: JSON.stringify(payload) });
      sessionStorage.removeItem("buy_now");
      go("#/orders");
      alert(`订单 ${order.order_no} 已提交，合计 ${money(order.total_yuan)}`);
    } catch (err) { error.textContent = err.message; }
  });
  form.append(line, submit, error);
  box.append(h("h3", "", "收货地址"), addressBox, form);
  return box;
}

async function renderOrders(status) {
  if (!requireLogin()) return h("p", "", "请先买家登录");
  const box = h("div");
  const tabs = h("div", "tabs");
  [["", "全部"], ["pending", "待支付"], ["paid", "待发货"], ["shipped", "待收货"], ["completed", "已完成"]].forEach(([value, label]) => {
    const button = h("button", value === status ? "on" : "", label);
    button.addEventListener("click", () => go(value ? `#/orders/${value}` : "#/orders"));
    tabs.append(button);
  });
  const orders = await api(`/api/v1/c/orders?share_code=${code}&status=${status}`);
  const list = h("div");
  if (!orders.length) list.append(h("p", "muted panel", "没有订单"));
  orders.forEach((order) => list.append(orderCard(order)));
  box.append(tabs, list);
  return box;
}

function orderCard(order) {
  const card = h("article", "panel");
  card.append(h("strong", "", `${order.order_no} · ${order.status_label}`));
  card.append(h("p", "", order.items.map((item) => `${item.product_name} ${item.sku_spec} x${item.quantity}`).join("，")));
  card.append(h("p", "price", `合计 ${money(order.total_yuan)}（含运费 ${money(order.freight_yuan)}）`));
  card.append(h("p", "muted", `${order.receiver} ${order.phone} ${order.address}`));
  const ops = h("div", "row");
  if (order.status === "pending") {
    ops.append(action("支付", () => api(`/api/v1/c/orders/${order.order_no}/pay`, { method: "POST" })));
    ops.append(action("取消", () => api(`/api/v1/c/orders/${order.order_no}/cancel`, { method: "POST" })));
  }
  if (order.status === "shipped") ops.append(action("确认收货", () => api(`/api/v1/c/orders/${order.order_no}/confirm`, { method: "POST" })));
  card.append(ops);
  return card;
}

function action(label, run) {
  const button = h("button", "btn", label);
  button.addEventListener("click", async () => {
    try { await run(); render(); } catch (error) { alert(error.message); }
  });
  return button;
}

function labeled(label, name, value) {
  const field = h("label", "field", label);
  const input = document.createElement("input");
  input.name = name;
  input.value = value;
  field.append(input);
  return field;
}

function requireLogin() {
  if (loggedIn()) return true;
  loginModal();
  return false;
}

function loginModal() {
  const mask = h("div", "modal");
  const panel = h("form", "panel");
  panel.append(h("h2", "", "买家登录"), labeled("账号", "username", "alice"), labeled("密码", "password", "alice123"));
  const error = h("p", "error", "");
  const submit = h("button", "btn", "登录");
  const close = h("button", "btn-ghost", "关闭");
  close.type = "button";
  close.addEventListener("click", () => mask.remove());
  panel.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const data = await api("/api/v1/auth/login", { method: "POST", body: JSON.stringify({ username: panel.username.value, password: panel.password.value }) });
      sessionStorage.setItem("token_c", data.access_token);
      mask.remove();
      render();
    } catch (err) { error.textContent = err.message; }
  });
  panel.append(error, h("div", "row"));
  panel.lastChild.append(submit, close);
  mask.append(panel);
  document.body.append(mask);
}

function renderChat() {
  const box = h("aside", "chat");
  const head = document.createElement("header");
  head.append(h("span", "", "店内助手"), h("span", "", "问商品 / 订单 / 售后"));
  const log = h("div", "log");
  chatLines.forEach((line) => log.append(h("div", line.me ? "bubble me" : "bubble", line.text)));
  const form = document.createElement("form");
  const input = document.createElement("input");
  input.placeholder = "例如：抱枕还有货吗";
  form.append(input, h("button", "", "发送"));
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!requireLogin()) return;
    const message = input.value.trim();
    if (!message) return;
    chatLines.push({ me: true, text: message });
    input.value = "";
    render();
    try {
      const data = await api(`/api/v1/c/shops/${code}/chat`, { method: "POST", body: JSON.stringify({ message, session_id: sessionId || undefined }) });
      sessionId = data.session_id;
      chatLines.push({ me: false, text: data.answer });
    } catch (error) {
      chatLines.push({ me: false, text: error.message });
    }
    render();
  });
  box.append(head, log, form);
  return box;
}

window.addEventListener("hashchange", render);
render();
