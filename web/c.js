const code = new URLSearchParams(location.search).get("code") || "nanzhi";
const api = createApi("token_c");

let shop = null;
let cats = null;
let keyword = "";
let category = "";
let sort = "default";
let sessionId = "";
let chatLines = [];
let chatOpen = false;
let addressId = null;
let cartCount = 0;
let cartPick = null;
let renderGen = 0;

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

function cover(url) {
  return url || "/covers/pillow.svg";
}

async function render() {
  const gen = ++renderGen;
  const root = document.querySelector("#app");
  if (!shop) {
    try {
      shop = await api(`/api/v1/c/shops/${code}`);
    } catch (error) {
      root.replaceChildren(h("p", "muted", error.message));
      return;
    }
  }
  if (!cats) {
    try {
      cats = await api(`/api/v1/c/shops/${code}/categories`);
    } catch {
      cats = [];
    }
  }
  if (loggedIn()) {
    try {
      const cart = await api(`/api/v1/c/shops/${code}/cart`);
      cartCount = cart.items.reduce((sum, item) => sum + item.quantity, 0);
    } catch {
      cartCount = 0;
    }
  } else {
    cartCount = 0;
  }
  let view;
  let navbar;
  try {
    [view, navbar] = await Promise.all([renderView(), renderNavbar()]);
  } catch (error) {
    view = h("div", "panel", error.message);
    navbar = h("nav", "navbar");
  }
  if (gen !== renderGen) return;
  const page = h("main", "wrap");
  page.append(view);
  root.replaceChildren(renderStrip(), renderHeader(), navbar, page, renderFooter(), renderChatToggle());
  if (chatOpen) root.append(renderChat());
}

/* ---------------- 顶部通栏 ---------------- */
function renderStrip() {
  const bar = h("div", "strip");
  const inner = h("div", "wrap");
  const left = h("div", "row");
  if (loggedIn()) {
    const who = h("span", "who");
    who.append(document.createTextNode("亲，欢迎回来　"));
    const out = h("button", "", "退出");
    out.addEventListener("click", () => {
      sessionStorage.removeItem("token_c");
      toast("已退出登录");
      render();
    });
    left.append(who, out);
  } else {
    const login = h("button", "", "亲，请登录");
    login.addEventListener("click", loginModal);
    const reg = h("span", "muted", "免费注册");
    left.append(login, reg);
  }
  const nav = h("nav");
  const orders = h("a", "", "我的订单");
  orders.href = "#/orders";
  const cart = h("a", "", "购物车");
  cart.href = "#/cart";
  const fav = h("a", "", "收藏本店");
  fav.href = "javascript:void(0)";
  fav.addEventListener("click", () => toast("已收藏本店", "ok"));
  const help = h("a", "", "联系店主");
  help.href = "javascript:void(0)";
  help.addEventListener("click", () => {
    chatOpen = true;
    render();
  });
  nav.append(orders, cart, fav, help);
  inner.append(left, nav);
  bar.append(inner);
  return bar;
}

/* ---------------- 页头 ---------------- */
function renderHeader() {
  const bar = h("header", "header");
  const inner = h("div", "wrap");
  const brand = h("a", "brand");
  brand.href = "#/";
  const mark = h("div", "mark", shop.name.slice(0, 1));
  const words = h("div");
  words.append(h("div", "name", shop.name), h("div", "sub", "HANDMADE STORE"));
  brand.append(mark, words);

  const box = h("div", "searchbox");
  const form = h("form", "search");
  const input = document.createElement("input");
  input.placeholder = "搜索本店商品";
  input.value = keyword;
  form.append(input, h("button", "", "搜索"));
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    keyword = input.value.trim();
    category = "";
    go("#/");
  });
  const hot = h("div", "hotwords");
  hot.append(h("span", "", "热门："));
  (cats || []).slice(0, 5).forEach((item) => {
    const button = h("button", "", item);
    button.addEventListener("click", () => {
      keyword = item;
      category = "";
      go("#/");
    });
    hot.append(button);
  });
  box.append(form, hot);

  const actions = h("div", "header-actions");
  const cart = h("button", "cart-btn");
  cart.append(h("span", "", "🛒 购物车"));
  if (cartCount) cart.append(h("b", "", String(cartCount)));
  cart.addEventListener("click", () => go("#/cart"));
  const account = h("button", "btn-ghost", loggedIn() ? "退出" : "登录");
  account.addEventListener("click", () => {
    if (loggedIn()) {
      sessionStorage.removeItem("token_c");
      toast("已退出登录");
      render();
    } else loginModal();
  });
  actions.append(account, cart);
  inner.append(brand, box, actions);
  bar.append(inner);
  return bar;
}

/* ---------------- 导航 ---------------- */
async function renderNavbar() {
  const bar = h("nav", "navbar");
  const inner = h("div", "wrap");
  const all = h("button", "all", "☰ 全部商品分类");
  all.addEventListener("click", () => {
    keyword = "";
    category = "";
    go("#/");
  });
  inner.append(all);
  const home = h("button", !keyword && !category && route().name === "home" ? "on" : "", "首页");
  home.addEventListener("click", () => {
    keyword = "";
    category = "";
    go("#/");
  });
  const shopAll = h("button", "", "全部商品");
  shopAll.addEventListener("click", () => {
    keyword = "";
    category = "";
    go("#/");
  });
  const orders = h("a", route().name === "orders" ? "on" : "", "订单中心");
  orders.href = "#/orders";
  inner.append(home, shopAll, orders);
  bar.append(inner);
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

/* ---------------- 首页 ---------------- */
async function renderHome() {
  const box = h("div");
  const query = new URLSearchParams({ keyword, category, sort });
  const [filtered, all] = await Promise.all([
    api(`/api/v1/c/shops/${code}/products?${query}`),
    api(`/api/v1/c/shops/${code}/products?keyword=&category=&sort=default`),
  ]);
  const counts = all.reduce((acc, item) => {
    acc[item.category] = (acc[item.category] || 0) + 1;
    return acc;
  }, {});

  const layout = h("div", "home");
  layout.append(renderCategorySide(all.length, counts), renderHomeMain(filtered, all));
  box.append(layout);
  return box;
}

function renderCategorySide(total, counts) {
  const side = h("aside", "cat-side");
  const title = h("h3");
  title.append(document.createTextNode("全部商品分类"), h("small", "", `${total} 件`));
  side.append(title);
  const all = h("button", category ? "" : "on");
  all.append(h("span", "", "全部商品"), h("i", "", String(total)));
  all.addEventListener("click", () => {
    category = "";
    go("#/");
  });
  side.append(all);
  (cats || []).forEach((item) => {
    const button = h("button", category === item ? "on" : "");
    button.append(h("span", "", item), h("i", "", String(counts[item] || 0)));
    button.addEventListener("click", () => {
      category = category === item ? "" : item;
      keyword = "";
      go("#/");
    });
    side.append(button);
  });
  return side;
}

function renderHomeMain(filtered, all) {
  const main = h("div");
  main.append(renderBanner(all));

  const bar = h("div", "toolbar");
  const parts = [`共 ${filtered.length} 件商品`];
  if (keyword) parts.push(`关键词「${keyword}」`);
  if (category) parts.push(`类目「${category}」`);
  const info = h("div", "row");
  info.append(h("span", "muted", parts.join(" · ")));
  if (keyword || category) {
    const clear = h("button", "btn-ghost btn-mini", "清除筛选");
    clear.addEventListener("click", () => {
      keyword = "";
      category = "";
      render();
    });
    info.append(clear);
  }
  const sorts = h("div", "sorts");
  [["default", "综合"], ["sales", "销量"], ["price_asc", "价格 ↑"], ["price_desc", "价格 ↓"]].forEach(([value, text]) => {
    const button = h("button", value === sort ? "on" : "", text);
    button.addEventListener("click", () => {
      sort = value;
      render();
    });
    sorts.append(button);
  });
  bar.append(info, sorts);
  main.append(bar);

  if (!filtered.length) {
    const empty = h("div", "empty");
    empty.append(h("div", "icon", "🔍"));
    empty.append(h("h3", "", "没有找到相关商品"));
    empty.append(h("p", "", keyword || category ? "换个关键词或类目试试" : "店主还没有上架商品"));
    const reset = h("button", "btn", "看看全部商品");
    reset.addEventListener("click", () => {
      keyword = "";
      category = "";
      render();
    });
    empty.append(reset);
    main.append(empty);
    return main;
  }

  const grid = h("div", "grid");
  filtered.forEach((product) => grid.append(productCard(product)));
  main.append(grid);
  return main;
}

function renderBanner(all) {
  const featured = [...all].sort((a, b) => b.sales_count - a.sales_count)[0];
  const banner = h("section", "banner");
  const left = h("div");
  left.append(h("h2", "", `${shop.name} · 手作日常`));
  left.append(h("p", "", shop.notice || "店主还没有写公告。这里的每一件都是小批量做的，有需要可以直接问店内助手。"));
  const tags = h("div", "row");
  tags.style.marginTop = "16px";
  if (featured) {
    const go_ = h("button", "btn", `看看 ${featured.name}`);
    go_.addEventListener("click", () => go(`#/product/${featured.id}`));
    tags.append(go_);
  }
  const ask = h("button", "btn-ghost", "问问助手");
  ask.addEventListener("click", () => {
    chatOpen = true;
    render();
  });
  tags.append(ask);
  left.append(tags);

  const share = h("div", "share");
  share.append(document.createTextNode("本店分享码"));
  share.append(h("b", "", shop.share_code));
  const copy = h("button", "", "复制分享链接");
  copy.addEventListener("click", () => {
    navigator.clipboard?.writeText(`${location.origin}/c.html?code=${shop.share_code}`);
    toast("分享链接已复制", "ok");
  });
  share.append(copy);
  banner.append(left, share);
  return banner;
}

function productCard(product) {
  const card = h("article", "pcard");
  const thumb = h("a", "thumb");
  thumb.href = `#/product/${product.id}`;
  const image = document.createElement("img");
  image.src = cover(product.image_url);
  image.alt = product.name;
  image.loading = "lazy";
  thumb.append(image);
  if (product.sales_count >= 10) thumb.append(h("span", "tag", "热销"));
  const quick = h("button", "quick", "加入购物车");
  quick.addEventListener("click", async (event) => {
    event.preventDefault();
    if (!requireLogin()) return;
    const sku = (product.skus || []).find((item) => item.purchasable) || product.skus[0];
    if (!sku) return;
    try {
      const cart = await api(`/api/v1/c/shops/${code}/cart`, {
        method: "POST",
        body: JSON.stringify({ sku_id: sku.id, quantity: 1 }),
      });
      cartCount = cart.items.reduce((sum, item) => sum + item.quantity, 0);
      toast("已加入购物车", "ok");
      render();
    } catch (error) {
      toast(error.message, "bad");
    }
  });
  thumb.append(quick);

  const body = h("div", "body");
  const title = h("a", "title", product.name);
  title.href = `#/product/${product.id}`;
  body.append(title);
  const meta = h("div", "meta");
  meta.append(h("span", "", product.category), h("span", "", `已售 ${product.sales_count}`));
  body.append(meta);
  const foot = h("div", "foot");
  const price = h("div", "price");
  price.append(h("i", "", "¥"), h("b", "", Number(product.price_from || 0).toFixed(2)));
  foot.append(price, h("span", "ship-tag", "包邮"));
  body.append(foot);
  card.append(thumb, body);
  return card;
}

/* ---------------- 商品详情 ---------------- */
async function renderProduct(id) {
  let product;
  try {
    product = await api(`/api/v1/c/shops/${code}/products/${id}`);
  } catch (error) {
    return h("div", "panel", error.message);
  }
  const box = h("div");
  const crumb = h("div", "crumb");
  const home = h("a", "", "全部商品");
  home.href = "#/";
  crumb.append(home, h("span", "", " / "), h("span", "", `${product.category} / ${product.name}`));
  box.append(crumb);

  const layout = h("div", "detail");
  layout.append(renderGallery(product));
  layout.append(renderProductInfo(product));
  box.append(layout);
  box.append(renderProductSection(product));
  return box;
}

function renderGallery(product) {
  const gallery = h("div", "gallery");
  const main = h("div", "main");
  const image = document.createElement("img");
  image.src = cover(product.image_url);
  image.alt = product.name;
  main.append(image);
  const thumbs = h("div", "thumbs");
  [["", "主图"], ["zoom-tl", "细节"], ["zoom-br", "局部"]].forEach(([cls, label], index) => {
    const button = h("button", index === 0 ? "on" : "");
    button.title = label;
    const thumb = document.createElement("img");
    thumb.src = cover(product.image_url);
    thumb.alt = `${product.name} ${label}`;
    thumb.className = cls;
    button.append(thumb);
    button.addEventListener("click", () => {
      image.className = cls;
      [...thumbs.children].forEach((item) => item.classList.remove("on"));
      button.classList.add("on");
    });
    thumbs.append(button);
  });
  gallery.append(main, thumbs);
  return gallery;
}

function renderProductInfo(product) {
  const info = h("div");
  info.append(h("h1", "", product.name));
  info.append(h("div", "sub-title", "私域独立店铺 · 店主直发 · 支持 7 天无理由退货"));

  let current = product.skus.find((sku) => sku.purchasable) || product.skus[0];
  const pricebox = h("div", "pricebox");
  const big = h("span", "big");
  const stockNote = h("span", "muted");
  const save = h("span", "save", "满 99 元包邮");
  pricebox.append(big, save, h("br"), stockNote);

  const promotions = h("div", "promotions");
  const promo = h("span");
  promo.append(document.createTextNode("优惠　"));
  promo.append(h("b", "", "满 99 包邮"));
  promo.append(document.createTextNode("　·　"));
  promo.append(h("b", "", "7 天无理由"));
  promotions.append(promo);

  function paint() {
    big.replaceChildren(document.createTextNode(money(current ? current.price_yuan : 0).slice(1)));
    big.prepend(h("i", "", "¥"));
    if (!current) {
      big.replaceChildren(document.createTextNode("暂无规格"));
      stockNote.textContent = "";
      return;
    }
    stockNote.textContent = current.purchasable
      ? `库存 ${current.stock} 件　·　${product.sales_count} 人已买`
      : "该规格暂时缺货，可以问问店主";
  }

  info.append(pricebox, promotions);
  info.append(h("div", "field-label", "选择规格"));
  const specs = h("div", "sku-list");
  product.skus.forEach((sku) => {
    const button = h("button", sku.id === current.id ? "on" : "", sku.spec);
    if (!sku.purchasable) button.classList.add("dead");
    button.addEventListener("click", () => {
      current = sku;
      [...specs.children].forEach((item) => item.classList.remove("on"));
      button.classList.add("on");
      paint();
    });
    specs.append(button);
  });
  info.append(specs);

  info.append(h("div", "field-label", "购买数量"));
  const qtyInput = document.createElement("input");
  qtyInput.value = "1";
  qtyInput.inputMode = "numeric";
  const qty = h("div", "qty");
  const minus = h("button", "", "−");
  const plus = h("button", "", "+");
  const clamp = () => {
    const value = Math.min(20, Math.max(1, Number(qtyInput.value) || 1));
    qtyInput.value = String(value);
    return value;
  };
  minus.addEventListener("click", () => {
    qtyInput.value = String(Math.max(1, Number(qtyInput.value) - 1));
  });
  plus.addEventListener("click", () => {
    qtyInput.value = String(Math.min(20, Number(qtyInput.value) + 1));
  });
  qtyInput.addEventListener("change", clamp);
  qty.append(minus, qtyInput, plus);
  info.append(qty);

  const actions = h("div", "actions");
  const add = h("button", "btn-cart btn-big", "加入购物车");
  const buy = h("button", "btn-buy btn-big", "立即购买");
  add.disabled = !current || !current.purchasable;
  buy.disabled = !current || !current.purchasable;
  add.addEventListener("click", async () => {
    if (!requireLogin()) return;
    try {
      const cart = await api(`/api/v1/c/shops/${code}/cart`, {
        method: "POST",
        body: JSON.stringify({ sku_id: current.id, quantity: clamp() }),
      });
      cartCount = cart.items.reduce((sum, item) => sum + item.quantity, 0);
      toast("已加入购物车", "ok");
      render();
    } catch (error) {
      toast(error.message, "bad");
    }
  });
  buy.addEventListener("click", () => {
    if (!requireLogin()) return;
    sessionStorage.setItem(
      "buy_now",
      JSON.stringify({
        sku_id: current.id,
        quantity: clamp(),
        name: product.name,
        spec: current.spec,
        price_yuan: current.price_yuan,
      })
    );
    go("#/checkout");
  });
  actions.append(add, buy);
  info.append(actions);

  const services = h("div", "services");
  ["正品保障", "7 天无理由退货", "满 99 元包邮", "48 小时内发货"].forEach((text) => services.append(h("span", "", text)));
  info.append(services);
  paint();
  return info;
}

function renderProductSection(product) {
  const section = h("section", "section");
  const head = h("div", "section-head");
  const one = h("span", "on", "商品详情");
  const two = h("span", "", "规格参数");
  head.append(one, two);

  const detail = h("div", "section-body");
  detail.append(h("p", "", product.description || "店主还没有补充说明。"));
  detail.append(
    h(
      "p",
      "muted",
      "小批量手作，尺寸和颜色会有轻微差异。收货后如有问题可以直接问店内助手，或者点右下角联系店主。"
    )
  );

  const params = h("div", "section-body");
  params.hidden = true;
  const table = h("table", "spec-table");
  const rows = [
    ["商品名称", product.name],
    ["所属类目", product.category],
    ["规格数量", `${product.skus.length} 个`],
    ["累计销量", `${product.sales_count} 件`],
    ["发货时效", "付款后 48 小时内"],
    ["运费说明", "订单满 99 元包邮，未满收 8 元"],
  ];
  rows.forEach(([k, v]) => {
    const tr = document.createElement("tr");
    tr.append(h("th", "", k), h("td", "", v));
    table.append(tr);
  });
  const skuTable = h("table", "spec-table");
  const skuHead = document.createElement("tr");
  ["规格", "价格", "库存"].forEach((text) => skuHead.append(h("th", "", text)));
  skuTable.append(skuHead);
  product.skus.forEach((sku) => {
    const tr = document.createElement("tr");
    tr.append(h("td", "", sku.spec), h("td", "", money(sku.price_yuan)), h("td", "", String(sku.stock)));
    skuTable.append(tr);
  });
  params.append(table, h("h4", "", "可选规格"));
  params.lastChild.style.margin = "20px 0 0";
  params.append(skuTable);

  one.addEventListener("click", () => {
    one.classList.add("on");
    two.classList.remove("on");
    detail.hidden = false;
    params.hidden = true;
  });
  two.addEventListener("click", () => {
    two.classList.add("on");
    one.classList.remove("on");
    detail.hidden = true;
    params.hidden = false;
  });

  section.append(head, detail, params);
  return section;
}

/* ---------------- 购物车 ---------------- */
async function renderCart() {
  if (!requireLogin()) {
    return emptyPanel("请先登录买家账号", "登录后可以看到购物车", "立即登录", loginModal);
  }
  const cart = await api(`/api/v1/c/shops/${code}/cart`);
  if (!cart.items.length) {
    return emptyPanel("购物车还是空的", "挑几件喜欢的吧", "去逛逛", () => go("#/"));
  }
  if (!cartPick) cartPick = new Set(cart.items.filter((item) => item.available).map((item) => item.id));

  const box = h("div");
  const panel = h("div", "cart-panel");
  const head = h("div", "cart-head");
  const allBox = document.createElement("input");
  allBox.type = "checkbox";
  allBox.className = "check";
  const selectable = cart.items.filter((item) => item.available);
  allBox.checked = selectable.length > 0 && selectable.every((item) => cartPick.has(item.id));
  allBox.addEventListener("change", () => {
    cartPick = allBox.checked ? new Set(selectable.map((item) => item.id)) : new Set();
    render();
  });
  head.append(allBox, h("div", "", "商品信息"), h("div", "", ""), h("div", "", "单价"), h("div", "", "数量"), h("div", "", "小计"), h("div", "", "操作"));
  panel.append(head);

  cart.items.forEach((item) => {
    const row = h("div", "cart-row");
    const box1 = document.createElement("input");
    box1.type = "checkbox";
    box1.className = "check";
    box1.checked = cartPick.has(item.id);
    box1.disabled = !item.available;
    box1.addEventListener("change", () => {
      if (box1.checked) cartPick.add(item.id);
      else cartPick.delete(item.id);
      render();
    });
    const image = document.createElement("img");
    image.src = cover(item.image_url);
    image.alt = item.product_name;
    const name = h("div");
    const title = h("a", "", item.product_name);
    title.href = `#/product/${item.product_id}`;
    title.className = "link";
    name.append(title, h("div", "muted", `规格：${item.spec}`));
    if (!item.available) name.append(h("div", "pill banned", item.reason));
    const price = h("div", "", money(item.price_yuan));
    const qty = h("div", "qty");
    const minus = h("button", "", "−");
    const value = document.createElement("input");
    value.value = String(item.quantity);
    value.readOnly = true;
    const plus = h("button", "", "+");
    const change = async (delta) => {
      try {
        await api(`/api/v1/c/cart/${item.id}`, {
          method: "PATCH",
          body: JSON.stringify({ quantity: item.quantity + delta }),
        });
        render();
      } catch (error) {
        toast(error.message, "bad");
      }
    };
    minus.addEventListener("click", () => item.quantity > 1 && change(-1));
    plus.addEventListener("click", () => item.quantity < 20 && change(1));
    qty.append(minus, value, plus);
    const subtotal = h("div", "price", money(item.price_yuan * item.quantity));
    const ops = h("div");
    const remove = h("button", "link", "删除");
    remove.addEventListener("click", async () => {
      await api(`/api/v1/c/cart/${item.id}`, { method: "DELETE" });
      cartPick.delete(item.id);
      toast("已移出购物车");
      render();
    });
    ops.append(remove);
    row.append(box1, image, name, price, qty, subtotal, ops);
    panel.append(row);
  });
  box.append(panel);

  const picked = cart.items.filter((item) => cartPick.has(item.id) && item.available);
  const goods = picked.reduce((sum, item) => sum + item.price_yuan * item.quantity, 0);
  const freight = goods > 0 && goods < 99 ? 8 : 0;
  const bar = h("div", "cart-bar");
  const left = h("div", "left");
  const allLabel = h("label", "row");
  const allBox2 = document.createElement("input");
  allBox2.type = "checkbox";
  allBox2.className = "check";
  allBox2.checked = allBox.checked;
  allBox2.addEventListener("change", () => {
    cartPick = allBox2.checked ? new Set(selectable.map((item) => item.id)) : new Set();
    render();
  });
  allLabel.append(allBox2, h("span", "", "全选"));
  const bulk = h("button", "link", "删除选中");
  bulk.addEventListener("click", async () => {
    if (!cartPick.size) return toast("先选几件吧");
    for (const id of [...cartPick]) await api(`/api/v1/c/cart/${id}`, { method: "DELETE" });
    cartPick = new Set();
    toast("已删除选中商品", "ok");
    render();
  });
  left.append(allLabel, bulk);
  const right = h("div", "row");
  const sum = h("div", "sum");
  sum.append(document.createTextNode(`已选 ${picked.reduce((n, item) => n + item.quantity, 0)} 件　商品 ${money(goods)}　运费 ${money(freight)}　合计 `));
  sum.append(h("b", "", money(goods + freight)));
  const checkout = h("button", "btn-buy btn-big", "去结算");
  checkout.disabled = !picked.length;
  checkout.addEventListener("click", () => {
    sessionStorage.removeItem("buy_now");
    go("#/checkout");
  });
  right.append(sum, checkout);
  bar.append(left, right);
  box.append(bar);
  return box;
}

/* ---------------- 结算 ---------------- */
async function renderCheckout() {
  if (!requireLogin()) {
    return emptyPanel("请先登录买家账号", "登录后可以下单", "立即登录", loginModal);
  }
  const addresses = await api("/api/v1/c/addresses");
  const buyNow = JSON.parse(sessionStorage.getItem("buy_now") || "null");
  const cart = buyNow ? null : await api(`/api/v1/c/shops/${code}/cart`);
  const picked = cart ? cart.items.filter((item) => cartPick?.has(item.id) && item.available) : [];
  if (!buyNow && !picked.length) {
    return emptyPanel("没有可结算的商品", "回购物车选几件", "回到购物车", () => go("#/cart"));
  }
  const selected =
    addresses.find((item) => item.id === addressId) || addresses.find((item) => item.is_default) || addresses[0];
  if (selected) addressId = selected.id;

  const box = h("div");
  const crumb = h("div", "crumb");
  const cartLink = h("a", "", "购物车");
  cartLink.href = "#/cart";
  crumb.append(cartLink, h("span", "", " / 确认订单"));
  box.append(crumb);

  const grid = h("div", "checkout");
  const left = h("div");

  const addrPanel = h("div", "panel");
  addrPanel.append(h("h2", "panel-title", "收货信息"));
  const addrGrid = h("div", "addr-grid");
  addresses.forEach((item) => {
    const button = h("button", item.id === addressId ? "addr on" : "addr");
    button.type = "button";
    button.append(h("b", "", `${item.receiver}　${item.phone}`));
    button.append(h("span", "muted", `${item.region}${item.detail}`));
    button.addEventListener("click", () => {
      addressId = item.id;
      render();
    });
    addrGrid.append(button);
  });
  if (!addresses.length) addrGrid.append(h("p", "muted", "还没有收货地址，直接填下面的表单就行"));
  addrPanel.append(addrGrid);

  const form = h("form");
  form.id = "checkout-form";
  form.style.marginTop = "18px";
  const fields = h("div", "form-grid");
  fields.append(
    labeled("收货人", "receiver", selected ? selected.receiver : "小满"),
    labeled("手机号", "phone", selected ? selected.phone : "13800001111"),
    labeled("收货地址", "address", selected ? `${selected.region}${selected.detail}` : "长沙市岳麓区示范路 1 号", true)
  );
  form.append(fields);
  left.append(addrPanel, form);

  const goodsPanel = h("div", "panel");
  goodsPanel.append(h("h2", "panel-title", "商品清单"));
  const lines = buyNow
    ? [{ name: buyNow.name, spec: buyNow.spec, price_yuan: buyNow.price_yuan, quantity: buyNow.quantity, image_url: "" }]
    : picked;
  lines.forEach((item) => {
    const line = h("div", "order-line");
    const image = document.createElement("img");
    image.src = cover(item.image_url);
    image.alt = item.name || item.product_name;
    const info = h("div");
    info.style.flex = "1";
    info.append(h("div", "", item.name || item.product_name));
    info.append(h("div", "muted", `规格 ${item.spec}`));
    line.append(image, info, h("span", "", money(item.price_yuan)), h("span", "muted", `x${item.quantity}`));
    goodsPanel.append(line);
  });
  left.append(goodsPanel);

  const aside = h("div", "panel");
  aside.append(h("h2", "panel-title", "订单结算"));
  const goods = lines.reduce((sum, item) => sum + item.price_yuan * item.quantity, 0);
  const freight = goods < 99 ? 8 : 0;
  [["商品金额", money(goods)], ["运费", freight ? money(freight) : "包邮"]].forEach(([label, value]) => {
    const line = h("div", "aside-total");
    line.append(h("span", "muted", label), h("span", "", value));
    aside.append(line);
  });
  const final = h("div", "aside-total final");
  final.append(h("span", "", "应付总额"), h("b", "", money(goods + freight)));
  aside.append(final);

  const error = h("p", "muted", "");
  const submit = h("button", "btn-buy btn-big", "提交订单");
  submit.type = "submit";
  submit.setAttribute("form", "checkout-form");
  submit.style.width = "100%";
  submit.style.marginTop = "16px";
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    submit.disabled = true;
    error.textContent = "";
    const payload = { receiver: val(form, "receiver"), phone: val(form, "phone"), address: val(form, "address") };
    try {
      const order = buyNow
        ? await api(`/api/v1/c/shops/${code}/orders`, {
            method: "POST",
            body: JSON.stringify({ ...payload, sku_id: buyNow.sku_id, quantity: buyNow.quantity }),
          })
        : await api(`/api/v1/c/shops/${code}/cart/checkout`, {
            method: "POST",
            body: JSON.stringify({ ...payload, cart_item_ids: [...(cartPick || [])] }),
          });
      sessionStorage.removeItem("buy_now");
      cartPick = null;
      toast(`下单成功 ${order.order_no}，合计 ${money(order.total_yuan)}`, "ok");
      go("#/orders");
    } catch (err) {
      error.textContent = err.message;
      submit.disabled = false;
    }
  });
  aside.append(submit, error);

  grid.append(left, aside);
  box.append(grid);
  return box;
}

function val(form, name) {
  const node = form.elements.namedItem(name);
  return node ? String(node.value).trim() : "";
}

/* ---------------- 订单 ---------------- */
async function renderOrders(status) {
  if (!requireLogin()) {
    return emptyPanel("请先登录买家账号", "登录后可以查看订单", "立即登录", loginModal);
  }
  const box = h("div");
  const tabs = h("div", "tabs");
  [["", "全部订单"], ["pending", "待支付"], ["paid", "待发货"], ["shipped", "待收货"], ["completed", "已完成"]].forEach(
    ([value, label]) => {
      const button = h("button", value === status ? "on" : "", label);
      button.addEventListener("click", () => go(value ? `#/orders/${value}` : "#/orders"));
      tabs.append(button);
    }
  );
  box.append(tabs);
  const orders = await api(`/api/v1/c/orders?share_code=${code}&status=${status}`);
  if (!orders.length) {
    return box.append(emptyPanel("这里还没有订单", "去店里挑几件", "去逛逛", () => go("#/"))), box;
  }
  orders.forEach((order) => box.append(orderCard(order)));
  return box;
}

function orderCard(order) {
  const card = h("article", "order");
  const head = h("div", "order-head");
  head.append(h("span", "no", `订单号 ${order.order_no}`));
  head.append(h("span", "", order.shop_name));
  head.append(h("span", "muted", order.status_label));
  const amount = h("span", "right");
  amount.append(document.createTextNode("实付 "));
  const price = h("span", "price");
  price.append(h("b", "", Number(order.total_yuan).toFixed(2)));
  price.style.fontSize = "16px";
  amount.append(price);
  head.append(amount);
  card.append(head);

  order.items.forEach((item) => {
    const line = h("div", "order-line");
    const info = h("div");
    info.style.flex = "1";
    info.append(h("div", "", item.product_name));
    info.append(h("div", "muted", `规格 ${item.sku_spec}`));
    line.append(info, h("span", "", money(item.price_yuan)), h("span", "muted", `x${item.quantity}`));
    card.append(line);
  });

  const foot = h("div", "order-foot");
  const pill = h("span", `pill ${order.status}`, order.status_label);
  foot.append(pill);
  foot.append(h("span", "muted", `${order.receiver} ${order.phone} ${order.address}`));
  foot.append(h("span", "muted", `含运费 ${money(order.freight_yuan)}`));
  if (order.status === "pending") {
    foot.append(action("取消订单", "btn-ghost", () => api(`/api/v1/c/orders/${order.order_no}/cancel`, { method: "POST" })));
    foot.append(action("立即支付", "btn-buy", () => api(`/api/v1/c/orders/${order.order_no}/pay`, { method: "POST" })));
  }
  if (order.status === "shipped") {
    foot.append(action("确认收货", "btn", () => api(`/api/v1/c/orders/${order.order_no}/confirm`, { method: "POST" })));
  }
  card.append(foot);
  return card;
}

function action(label, className, run) {
  const button = h("button", className, label);
  button.addEventListener("click", async () => {
    try {
      await run();
      toast(`${label}成功`, "ok");
      render();
    } catch (error) {
      toast(error.message, "bad");
    }
  });
  return button;
}

function labeled(label, name, value, full = false) {
  const field = h("label", full ? "field full" : "field");
  field.append(h("span", "", label));
  const input = document.createElement("input");
  input.name = name;
  input.value = value;
  field.append(input);
  return field;
}

function emptyPanel(title, sub, actionLabel, onAction) {
  const panel = h("div", "empty");
  panel.append(h("div", "icon", "🛍"), h("h3", "", title), h("p", "", sub));
  if (actionLabel) {
    const button = h("button", "btn", actionLabel);
    button.addEventListener("click", onAction);
    panel.append(button);
  }
  return panel;
}

function requireLogin() {
  if (loggedIn()) return true;
  loginModal();
  return false;
}

function loginModal() {
  const mask = h("div", "modal");
  const panel = h("form", "panel stack");
  panel.append(h("h2", "", "买家登录"), h("p", "muted", "演示账号 alice / alice123"));
  const fields = h("div", "stack");
  fields.append(labeled("账号", "username", "alice"), labeled("密码", "password", "alice123"));
  panel.append(fields);
  const error = h("p", "muted", "");
  const submit = h("button", "btn-buy", "登录");
  submit.type = "submit";
  const close = h("button", "btn-ghost", "取消");
  close.type = "button";
  close.addEventListener("click", () => mask.remove());
  const row = h("div", "row");
  row.append(submit, close);
  panel.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const data = await api("/api/v1/auth/login", {
        method: "POST",
        body: JSON.stringify({ username: val(panel, "username"), password: val(panel, "password") }),
      });
      if (data.user.role !== "customer") throw new Error("请使用买家账号，例如 alice / alice123");
      sessionStorage.setItem("token_c", data.access_token);
      mask.remove();
      toast(`欢迎回来，${data.user.nickname}`, "ok");
      render();
    } catch (err) {
      error.textContent = err.message;
    }
  });
  panel.append(error, row);
  mask.append(panel);
  document.body.append(mask);
}

function renderFooter() {
  const footer = h("footer", "footer");
  const inner = h("div", "wrap");
  const about = h("div");
  about.append(h("b", "", shop.name));
  about.append(h("div", "muted", "私域独立店铺 · 分享码进店"));
  about.append(h("div", "muted", `分享码 ${shop.share_code} · ${STATUS[shop.status] || ""}`));
  const help = h("div");
  help.append(h("b", "", "购物说明"));
  help.append(h("div", "muted", "满 99 元包邮，未满收 8 元运费"));
  help.append(h("div", "muted", "7 天无理由退货，定制品和已使用商品除外"));
  const service = h("div");
  service.append(h("b", "", "售后服务"));
  service.append(h("div", "muted", "有问题点右下角问店内助手"));
  service.append(h("div", "muted", "助手只能看到你自己在这家店的订单"));
  inner.append(about, help, service);
  footer.append(inner);
  return footer;
}

function renderChatToggle() {
  const button = h("button", "chat-fab", chatOpen ? "×" : "💬");
  button.title = "店内助手";
  button.addEventListener("click", () => {
    chatOpen = !chatOpen;
    render();
  });
  return button;
}

function renderChat() {
  const box = h("aside", "chat");
  const head = document.createElement("header");
  const title = h("div");
  title.append(h("b", "", "店内助手"), h("small", "", "商品 · 库存 · 订单 · 售后"));
  const close = h("button", "close", "×");
  close.addEventListener("click", () => {
    chatOpen = false;
    render();
  });
  head.append(title, close);
  const log = h("div", "log");
  if (!chatLines.length) {
    log.append(h("div", "bubble", "你好，我是南枝手作的店内助手。可以帮你查在售商品、库存、你自己的订单，也能回答退货和养护问题。"));
  }
  chatLines.forEach((line) => log.append(h("div", line.me ? "bubble me" : "bubble", line.text)));
  const tips = h("div", "tips");
  ["抱枕还有货吗", "我的订单到哪了", "定制品能退吗"].forEach((text) => {
    const chip = h("button", "", text);
    chip.addEventListener("click", () => {
      input.value = text;
      input.focus();
    });
    tips.append(chip);
  });
  const form = document.createElement("form");
  const input = document.createElement("input");
  input.placeholder = "输入问题…";
  form.append(input, h("button", "", "发送"));
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!requireLogin()) return;
    const message = input.value.trim();
    if (!message) return;
    chatLines.push({ me: true, text: message });
    input.value = "";
    log.append(h("div", "bubble me", message));
    const pending = h("div", "bubble", "正在查…");
    log.append(pending);
    log.scrollTop = log.scrollHeight;
    try {
      const data = await api(`/api/v1/c/shops/${code}/chat`, {
        method: "POST",
        body: JSON.stringify({ message, session_id: sessionId || undefined }),
      });
      sessionId = data.session_id;
      pending.textContent = data.answer;
      chatLines.push({ me: false, text: data.answer });
    } catch (error) {
      pending.textContent = error.message;
      chatLines.push({ me: false, text: error.message });
    }
    log.scrollTop = log.scrollHeight;
  });
  box.append(head, log, tips, form);
  return box;
}

window.addEventListener("hashchange", render);
render();
