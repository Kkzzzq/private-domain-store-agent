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
let pendingDeadlines = {};
let tickTimer = null;

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
  return url || "/covers/pillow.jpg";
}

/** 折扣按实付 / 划线价算，没有划线价就返回 null。 */
function discountOf(price, market) {
  if (!market || market <= price) return null;
  const value = (price / market) * 10;
  return `${value.toFixed(1)}折`;
}

function discountLabel(text) {
  return text ? `省 ${text}` : "";
}

async function render() {
  const gen = ++renderGen;
  const root = document.querySelector("#app");
  if (!shop) {
    try {
      shop = await api(`/api/v1/c/shops/${code}`);
      applyTheme(shop.theme_color);
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
  watchCountdowns();
}

/* ---------------- 顶部通栏 ---------------- */
function renderStrip() {
  const bar = h("div", "strip");
  const inner = h("div", "wrap");
  const left = h("div", "row");
  if (loggedIn()) {
    left.append(h("span", "who", "亲，欢迎回来"));
    const out = h("button", "", "退出");
    out.addEventListener("click", () => {
      sessionStorage.removeItem("token_c");
      pendingDeadlines = {};
      toast("已退出登录");
      render();
    });
    left.append(out);
  } else {
    const login = h("button", "", "亲，请登录");
    login.addEventListener("click", loginModal);
    left.append(login, h("span", "muted", "免费注册"));
  }
  const nav = h("nav");
  [["#/orders", "我的订单"], ["#/reviews", "待评价"], ["#/favorites", "我的收藏"], ["#/history", "浏览记录"], ["#/cart", "购物车"]].forEach(
    ([href, label]) => {
      const link = h("a", "", label);
      link.href = href;
      nav.append(link);
    }
  );
  const help = h("button", "", "联系店主");
  help.addEventListener("click", () => {
    chatOpen = true;
    render();
  });
  nav.append(help);
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
  let mark;
  if (shop.logo_url) {
    mark = document.createElement("img");
    mark.className = "mark";
    mark.src = shop.logo_url;
    mark.alt = shop.name;
    mark.style.objectFit = "cover";
    mark.style.background = "none";
    mark.style.padding = "0";
  } else {
    mark = h("div", "mark", shop.name.slice(0, 1));
  }
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
      pendingDeadlines = {};
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
  const favs = h("a", route().name === "favorites" ? "on" : "", "我的收藏");
  favs.href = "#/favorites";
  const history = h("a", route().name === "history" ? "on" : "", "浏览记录");
  history.href = "#/history";
  inner.append(home, shopAll, orders, favs, history);
  bar.append(inner);
  return bar;
}

async function renderView() {
  const current = route();
  if (current.name === "product") return renderProduct(current.id);
  if (current.name === "cart") return renderCart();
  if (current.name === "checkout") return renderCheckout();
  if (current.name === "orders") return renderOrders(current.id);
  if (current.name === "favorites") return renderFavorites();
  if (current.name === "history") return renderHistory();
  if (current.name === "reviews") return renderPendingReviews();
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
  box.append(layout, renderPromises());
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
  const bg = h("div", "bg");
  const image = document.createElement("img");
  image.src = "/covers/hero.jpg";
  image.alt = "";
  bg.append(image);
  banner.append(bg, h("div", "veil"));

  const inner = h("div", "inner");
  const left = h("div");
  left.append(h("div", "eyebrow", "HANDMADE · SMALL BATCH"));
  left.append(h("h2", "", shop.name));
  left.append(
    h("p", "", shop.notice || "小批量手作，每一件都会有一点手工的痕迹。有需要可以直接问店内助手。")
  );
  const actions = h("div", "actions");
  if (featured) {
    const go_ = h("button", "btn-buy btn-big", `看看热销的${featured.name}`);
    go_.addEventListener("click", () => go(`#/product/${featured.id}`));
    actions.append(go_);
  }
  const ask = h("button", "btn-ghost btn-big", "问问助手");
  ask.style.background = "rgba(255,255,255,0.14)";
  ask.style.color = "#fff";
  ask.style.borderColor = "rgba(255,255,255,0.3)";
  ask.addEventListener("click", () => {
    chatOpen = true;
    render();
  });
  actions.append(ask);
  left.append(actions);

  const share = h("div", "share");
  share.append(document.createTextNode("本店分享码"));
  share.append(h("b", "", shop.share_code));
  const copy = h("button", "", "复制分享链接");
  copy.addEventListener("click", () => {
    navigator.clipboard?.writeText(`${location.origin}/c.html?code=${shop.share_code}`);
    toast("分享链接已复制", "ok");
  });
  share.append(copy);
  inner.append(left, share);
  banner.append(inner);
  return banner;
}

function renderPromises() {
  const box = h("div", "promises");
  [
    ["正品保障", "店主直发，假一赔十"],
    ["7 天无理由", "定制品和已使用商品除外"],
    ["满 99 包邮", "未满收 8 元运费"],
    ["48 小时发货", "付款后按顺序发出"],
  ].forEach(([title, sub]) => {
    const cell = h("div");
    cell.append(h("b", "", title), h("span", "muted", sub));
    box.append(cell);
  });
  return box;
}

async function toggleFavorite(product, button) {
  if (!requireLogin()) return;
  try {
    const result = await api(`/api/v1/c/shops/${code}/favorites/${product.id}`, { method: "POST" });
    toast(result.detail, "ok");
    // 只改按钮状态，不整页重渲染，避免和登录后的刷新撞车。
    if (button) {
      button.classList.toggle("on", result.favorited);
      button.textContent = button.classList.contains("fav")
        ? result.favorited
          ? "♥"
          : "♡"
        : result.favorited
          ? "♥ 已收藏"
          : "♡ 收藏";
    }
  } catch (error) {
    toast(error.message, "bad");
  }
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
  const off = discountOf(product.price_from, product.market_from);
  if (off) thumb.append(h("span", "tag", off));
  else if (product.sales_count >= 50) thumb.append(h("span", "tag", "热销"));

  const fav = h("button", product.favorited ? "fav on" : "fav", product.favorited ? "♥" : "♡");
  fav.title = product.favorited ? "取消收藏" : "加入收藏";
  fav.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    toggleFavorite(product, fav);
  });
  thumb.append(fav);

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
  const rating = h("span", "stars");
  rating.append(ratingStars(product.rating_avg || 0), document.createTextNode(ratingText(product.rating_avg, product.review_count)));
  meta.append(rating, h("span", "", `已售 ${product.sales_count}`));
  body.append(meta);

  const foot = h("div", "foot");
  const price = h("div", "price");
  price.append(h("i", "", "¥"), h("b", "", Number(product.price_from || 0).toFixed(2)));
  if (product.market_from) price.append(h("span", "price-was", `¥${Number(product.market_from).toFixed(2)}`));
  const tags = h("div", "row");
  tags.style.gap = "4px";
  if (product.limit_per_user) tags.append(h("span", "ship-tag", `限购${product.limit_per_user}`));
  tags.append(h("span", "ship-tag", "包邮"));
  foot.append(price, tags);
  body.append(foot);

  const sold = Math.min(100, Math.round((product.sales_count / 140) * 100));
  const bar = h("div", "sales-bar");
  const fill = document.createElement("span");
  fill.style.width = `${Math.max(6, sold)}%`;
  bar.append(fill);
  body.append(bar);

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
  const [reviews, all] = await Promise.all([
    api(`/api/v1/c/shops/${code}/products/${id}/reviews`),
    api(`/api/v1/c/shops/${code}/products?keyword=&category=&sort=sales`),
  ]);
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
  box.append(renderProductSection(product, reviews));
  box.append(renderRelated(product, all));
  return box;
}

/** 同类的其他商品，没有同类就退回家居类。 */
function renderRelated(product, all) {
  const others = all.filter((item) => item.id !== product.id);
  const same = others.filter((item) => item.category === product.category);
  const picks = [...same, ...others].slice(0, 4);
  if (!picks.length) return h("div");
  const box = h("section", "section");
  const head = h("div", "section-head");
  head.append(h("span", "on", same.length ? `同类手作 · ${product.category}` : "看了还看"));
  box.append(head);
  const body = h("div", "section-body");
  const grid = h("div", "grid");
  grid.style.padding = "0";
  picks.forEach((item) => grid.append(productCard(item)));
  body.append(grid);
  box.append(body);
  return box;
}

function renderGallery(product) {
  const gallery = h("div", "gallery");
  const thumbs = h("div", "thumbs");
  const main = h("div", "main");
  const image = document.createElement("img");
  image.src = cover(product.image_url);
  image.alt = product.name;
  main.append(image);
  [["", "整体"], ["zoom-tl", "细节"], ["zoom-br", "局部"]].forEach(([cls, label], index) => {
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
  gallery.append(thumbs, main);
  return gallery;
}

/** 详情页底部悬浮购买栏，滚过主按钮才出现。 */
function renderBuyBar(product, ctx) {
  const bar = h("div", "buy-bar");
  const inner = h("div", "wrap");
  const image = document.createElement("img");
  image.className = "thumb";
  image.src = cover(product.image_url);
  image.alt = product.name;
  const words = h("div");
  words.append(h("div", "", product.name));
  const meta = h("div", "muted", "");
  words.append(meta);
  const spacer = h("div", "spacer");
  const price = h("div", "p", "");
  const fav = h("button", product.favorited ? "fav-btn on" : "fav-btn", product.favorited ? "♥ 已收藏" : "♡ 收藏");
  fav.addEventListener("click", () => toggleFavorite(product, fav));
  const add = h("button", "btn-cart btn-big", "加入购物车");
  const buy = h("button", "btn-buy btn-big", "立即购买");
  add.addEventListener("click", ctx.addToCart);
  buy.addEventListener("click", ctx.buyNow);
  inner.append(image, words, spacer, price, fav, add, buy);
  bar.append(inner);

  const refresh = () => {
    const value = ctx.price();
    price.textContent = value == null ? "" : money(value);
    meta.textContent = ctx.spec() ? `已选 ${ctx.spec()}` : "请选择规格";
  };
  refresh();
  const timer = setInterval(() => {
    if (!document.body.contains(bar)) return clearInterval(timer);
    refresh();
  }, 400);

  // 主按钮滚出视野后再浮出来，避免和主按钮重复
  requestAnimationFrame(() => {
    const anchor = document.querySelector(".detail .actions");
    if (anchor && "IntersectionObserver" in window) {
      const observer = new IntersectionObserver(
        ([entry]) => bar.classList.toggle("show", !entry.isIntersecting),
        { threshold: 0 }
      );
      observer.observe(anchor);
    } else {
      bar.classList.add("show");
    }
  });
  return bar;
}

function renderProductInfo(product) {
  const info = h("div");
  info.append(h("h1", "", product.name));
  info.append(h("div", "sub-title", "店主直发 · 支持 7 天无理由退货 · 满 99 元包邮"));

  const ratingRow = h("div", "rating-line");
  ratingRow.append(
    ratingStars(product.rating_avg || 0, { size: "m" }),
    h("span", "muted", ratingText(product.rating_avg, product.review_count)),
    h("a", "link", `已售 ${product.sales_count} 件`)
  );
  const jump = ratingRow.lastChild;
  jump.href = "#reviews";
  info.append(ratingRow);

  let current = product.skus.find((sku) => sku.purchasable) || product.skus[0];
  const pricebox = h("div", "pricebox");
  const priceLine = h("div", "line");
  const big = h("span", "big");
  const was = h("span", "old", "");
  const offTag = h("span", "off", "");
  priceLine.append(big, was, offTag);
  const stockNote = h("div", "stock");
  pricebox.append(priceLine, stockNote);

  const promotions = h("div", "promotions");
  const promo = h("span");
  promo.append(document.createTextNode("优惠　"));
  promo.append(h("b", "", "满 99 包邮"));
  promo.append(document.createTextNode("　·　"));
  promo.append(h("b", "", "7 天无理由"));
  if (product.limit_per_user) {
    promo.append(document.createTextNode("　·　"));
    promo.append(h("b", "", `每人限购 ${product.limit_per_user} 件`));
  }
  promotions.append(promo);

  function paint() {
    if (!current) {
      big.replaceChildren(document.createTextNode("暂无规格"));
      was.textContent = "";
      offTag.textContent = "";
      stockNote.textContent = "";
      return;
    }
    big.replaceChildren(h("i", "", "¥"), document.createTextNode(Number(current.price_yuan).toFixed(2)));
    const off = discountOf(current.price_yuan, current.market_price_yuan);
    was.textContent = current.market_price_yuan ? `¥${Number(current.market_price_yuan).toFixed(2)}` : "";
    offTag.textContent = off || "";
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
    const max = product.limit_per_user || 20;
    const value = Math.min(Math.min(20, max), Math.max(1, Number(qtyInput.value) || 1));
    qtyInput.value = String(value);
    return value;
  };
  minus.addEventListener("click", () => {
    qtyInput.value = String(Math.max(1, Number(qtyInput.value) - 1));
  });
  plus.addEventListener("click", () => {
    const max = Math.min(20, product.limit_per_user || 20);
    qtyInput.value = String(Math.min(max, Number(qtyInput.value) + 1));
  });
  qtyInput.addEventListener("change", clamp);
  qty.append(minus, qtyInput, plus);
  info.append(qty);
  if (product.limit_per_user) {
    const note = h("div", "muted");
    note.textContent = `这件商品每人最多买 ${product.limit_per_user} 件`;
    info.append(note);
  }

  const actions = h("div", "actions");
  const add = h("button", "btn-cart btn-big", "加入购物车");
  const buy = h("button", "btn-buy btn-big", "立即购买");
  const fav = h("button", product.favorited ? "fav-btn on" : "fav-btn", product.favorited ? "♥ 已收藏" : "♡ 收藏");
  add.disabled = !current || !current.purchasable;
  buy.disabled = !current || !current.purchasable;
  const addToCart = async () => {
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
  };
  const buyNow = () => {
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
  };
  add.addEventListener("click", addToCart);
  buy.addEventListener("click", buyNow);
  fav.addEventListener("click", () => toggleFavorite(product, fav));
  actions.append(add, buy, fav);
  info.append(actions);
  info.append(
    renderBuyBar(product, { addToCart, buyNow, price: () => current?.price_yuan, spec: () => current?.spec })
  );

  const services = h("div", "services");
  ["正品保障", "7 天无理由退货", "满 99 元包邮", "48 小时内发货"].forEach((text) => services.append(h("span", "", text)));
  info.append(services);
  paint();
  return info;
}

function renderProductSection(product, reviews) {
  const section = h("section", "section");
  const head = h("div", "section-head");
  const one = h("span", "on", "商品详情");
  const two = h("span", "", "规格参数");
  const three = h("span", "", `用户评价（${reviews.length}）`);
  head.append(one, two, three);

  const detail = h("div", "section-body");
  detail.append(h("p", "", product.description || "店主还没有补充说明。"));
  const blocks = [
    ["关于这件手作", "每一件都是小批量做出来的，尺寸、颜色和纹理会有轻微差别，这正是手作的特点。收到的实物可能和照片有一点色差，介意的话可以先问问店主。"],
    ["使用与打理", "日常用干布擦拭即可。可水洗的材质建议冷水轻柔手洗，不要漂白，展开阴干，避免长时间暴晒和高温熨烫。"],
    ["发货与包装", "付款后 48 小时内按顺序发出，默认用可回收的纸盒和牛皮纸缓冲，不额外加塑料填充。需要送礼可以备注，店主会换成礼盒包装。"],
  ];
  blocks.forEach(([title, text]) => {
    const block = h("div");
    block.style.marginTop = "22px";
    const heading = h("h4", "", title);
    const para = h("p", "", text);
    para.style.marginTop = "6px";
    block.append(heading, para);
    detail.append(block);
  });

  const params = h("div", "section-body");
  params.hidden = true;
  const table = h("table", "spec-table");
  const rows = [
    ["商品名称", product.name],
    ["所属类目", product.category],
    ["规格数量", `${product.skus.length} 个`],
    ["累计销量", `${product.sales_count} 件`],
    ["限购规则", product.limit_per_user ? `每人最多 ${product.limit_per_user} 件` : "不限购"],
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
  params.append(table);
  const skuTitle = h("h4", "", "可选规格");
  skuTitle.style.margin = "20px 0 0";
  params.append(skuTitle, skuTable);

  const reviewBox = h("div", "section-body");
  reviewBox.id = "reviews";
  reviewBox.hidden = true;
  if (!reviews.length) {
    reviewBox.append(h("p", "muted", "还没有人评价这件商品。"));
  } else {
    reviews.forEach((review) => {
      const item = h("div", "review");
      const who = h("div", "who");
      who.append(h("span", "avatar", maskName(review.nickname).slice(0, 1)));
      who.append(h("span", "", maskName(review.nickname)));
      who.append(ratingStars(review.rating));
      who.append(h("span", "muted", review.created_at));
      item.append(who, h("p", "", review.content || "买家没有留下文字"));
      reviewBox.append(item);
    });
  }

  const tabs = [
    [one, detail],
    [two, params],
    [three, reviewBox],
  ];
  tabs.forEach(([button, panel]) => {
    button.addEventListener("click", () => {
      tabs.forEach(([item]) => item.classList.remove("on"));
      button.classList.add("on");
      tabs.forEach(([, node]) => (node.hidden = true));
      panel.hidden = false;
      if (panel === reviewBox) reviewBox.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  });

  section.append(head, detail, params, reviewBox);
  return section;
}

/* ---------------- 收藏 / 浏览记录 ---------------- */
async function renderFavorites() {
  if (!requireLogin()) {
    return emptyPanel("请先登录买家账号", "登录后可以看到收藏的商品", "立即登录", loginModal);
  }
  const products = await api(`/api/v1/c/shops/${code}/favorites`);
  const box = h("div");
  const panel = h("div", "panel");
  panel.append(h("h2", "panel-title", `我的收藏（${products.length}）`));
  if (!products.length) {
    box.append(panel, emptyPanel("还没有收藏任何商品", "点商品图右上角的心形就能收藏", "去逛逛", () => go("#/")));
    return box;
  }
  const grid = h("div", "grid");
  grid.style.padding = "0";
  products.forEach((product) => grid.append(productCard(product)));
  panel.append(grid);
  box.append(panel);
  return box;
}

async function renderHistory() {
  if (!requireLogin()) {
    return emptyPanel("请先登录买家账号", "登录后可以看到浏览记录", "立即登录", loginModal);
  }
  const products = await api(`/api/v1/c/shops/${code}/history`);
  const box = h("div");
  const panel = h("div", "panel");
  const title = h("h2", "panel-title", `浏览记录（${products.length}）`);
  if (products.length) {
    const wipe = h("button", "btn-ghost btn-mini", "清空");
    wipe.style.marginLeft = "auto";
    wipe.addEventListener("click", async () => {
      await api(`/api/v1/c/shops/${code}/history`, { method: "DELETE" });
      toast("浏览记录已清空", "ok");
      render();
    });
    title.append(wipe);
  }
  panel.append(title);
  if (!products.length) {
    panel.append(h("p", "muted", "最近没有浏览过商品。"));
    box.append(panel);
    return box;
  }
  const grid = h("div", "grid");
  grid.style.padding = "0";
  products.forEach((product) => grid.append(productCard(product)));
  panel.append(grid);
  box.append(panel);
  return box;
}

/* ---------------- 待评价 ---------------- */
async function renderPendingReviews() {
  if (!requireLogin()) {
    return emptyPanel("请先登录买家账号", "登录后可以评价买过的商品", "立即登录", loginModal);
  }
  const pending = await api("/api/v1/c/reviews/pending");
  const box = h("div");
  const panel = h("div", "panel");
  panel.append(h("h2", "panel-title", `待评价（${pending.length}）`));
  if (!pending.length) {
    panel.append(h("p", "muted", "没有待评价的商品。确认收货之后就能评价了。"));
    const to = h("button", "btn", "查看我的订单");
    to.style.marginTop = "14px";
    to.addEventListener("click", () => go("#/orders"));
    panel.append(to);
    box.append(panel);
    return box;
  }
  pending.forEach((item) => {
    const row = h("div", "pick");
    const words = h("div");
    words.append(h("div", "", item.product_name));
    words.append(h("div", "muted", `规格 ${item.sku_spec} · 订单 ${item.order_no}`));
    const button = h("button", "btn-line", "去评价");
    button.addEventListener("click", () => reviewDialog(item));
    row.append(words, button);
    panel.append(row);
  });
  box.append(panel);
  return box;
}

function reviewDialog(item) {
  const dialog = document.createElement("wa-dialog");
  dialog.setAttribute("label", `评价 ${item.product_name}`);
  dialog.setAttribute("light-dismiss", "");
  dialog.style.setProperty("--width", "420px");

  const form = h("div", "review-form");
  const stars = ratingStars(5, { readonly: false, size: "l", label: "打分" });
  stars.removeAttribute("readonly");
  const starRow = h("div", "row");
  starRow.append(h("span", "", "打分"), stars);
  const textarea = document.createElement("textarea");
  textarea.placeholder = "说说这件商品怎么样，可以帮到其他人";
  const error = h("p", "muted", "");
  const submit = h("button", "btn-buy", "提交评价");
  submit.type = "button";
  submit.addEventListener("click", async () => {
    submit.disabled = true;
    try {
      await api("/api/v1/c/reviews", {
        method: "POST",
        body: JSON.stringify({
          order_item_id: item.order_item_id,
          rating: Number(stars.value || stars.getAttribute("value") || 5),
          content: textarea.value.trim(),
        }),
      });
      toast("评价已提交", "ok");
      dialog.open = false;
      go("#/reviews");
    } catch (err) {
      error.textContent = err.message;
      submit.disabled = false;
    }
  });
  form.append(starRow, textarea, error, submit);
  dialog.append(form);
  dialog.addEventListener("wa-after-hide", () => dialog.remove());
  document.body.append(dialog);
  dialog.open = true;
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
      toast(`下单成功 ${order.order_no}，请在 30 分钟内付款`, "ok");
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
    box.append(emptyPanel("这里还没有订单", "去店里挑几件", "去逛逛", () => go("#/")));
    return box;
  }
  orders.forEach((order) => box.append(orderCard(order)));
  return box;
}

function orderCard(order) {
  const card = h("article", "order");
  const head = h("div", "order-head");
  head.append(h("span", "no", `订单号 ${order.order_no}`));
  head.append(h("span", "", order.shop_name));
  const stateCell = h("span");
  stateCell.append(h("span", `pill ${order.status}`, order.status_label));
  head.append(stateCell);
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
  if (order.status === "pending" && order.expires_in_seconds != null) {
    const clock = h("span", "countdown");
    clock.append(document.createTextNode("剩余支付时间 "));
    const value = h("b", "", remainText(order.expires_in_seconds));
    clock.append(value);
    clock.dataset.orderNo = order.order_no;
    foot.append(clock);
    pendingDeadlines[order.order_no] = Date.now() + order.expires_in_seconds * 1000;
  }
  foot.append(h("span", "muted", `${order.receiver} ${order.phone} ${order.address}`));
  foot.append(h("span", "muted", `含运费 ${money(order.freight_yuan)}`));
  if (order.status === "pending") {
    foot.append(action("取消订单", "btn-ghost", () => api(`/api/v1/c/orders/${order.order_no}/cancel`, { method: "POST" })));
    foot.append(action("立即支付", "btn-buy", () => api(`/api/v1/c/orders/${order.order_no}/pay`, { method: "POST" })));
  }
  if (order.status === "shipped") {
    foot.append(action("确认收货", "btn", () => api(`/api/v1/c/orders/${order.order_no}/confirm`, { method: "POST" })));
  }
  if (order.status === "completed") {
    const review = h("button", "btn-line", "去评价");
    review.addEventListener("click", () => go("#/reviews"));
    foot.append(review);
  }
  card.append(foot);
  return card;
}

/** 待支付订单每秒刷新倒计时，到点重新拉一次让状态变成已取消。 */
function watchCountdowns() {
  if (tickTimer) {
    clearInterval(tickTimer);
    tickTimer = null;
  }
  const nodes = [...document.querySelectorAll(".countdown b")];
  if (!nodes.length) return;
  tickTimer = setInterval(() => {
    let expired = false;
    nodes.forEach((node) => {
      const orderNo = node.closest(".countdown")?.dataset.orderNo;
      const deadline = pendingDeadlines[orderNo];
      if (!deadline) return;
      const left = Math.round((deadline - Date.now()) / 1000);
      if (left <= 0) {
        expired = true;
        return;
      }
      node.textContent = remainText(left);
    });
    if (expired) {
      clearInterval(tickTimer);
      tickTimer = null;
      toast("有订单超过支付时间，已自动取消", "bad");
      render();
    }
  }, 1000);
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

/* ---------------- 登录弹层（Web Awesome dialog） ---------------- */
function loginModal() {
  const dialog = document.createElement("wa-dialog");
  dialog.setAttribute("label", "买家登录");
  dialog.setAttribute("light-dismiss", "");
  dialog.style.setProperty("--width", "380px");

  const form = h("div", "stack");
  form.append(h("p", "muted", "演示账号 alice / alice123"));
  const fields = h("div", "stack");
  fields.append(labeled("账号", "username", "alice"), labeled("密码", "password", "alice123"));
  const error = h("p", "muted", "");
  const submit = h("button", "btn-buy", "登录");
  submit.type = "button";
  const close = h("button", "btn-ghost", "取消");
  close.type = "button";
  close.addEventListener("click", () => (dialog.open = false));
  const row = h("div", "row");
  row.append(submit, close);
  form.append(fields, error, row);

  const read = (name) => {
    const node = fields.querySelector(`input[name="${name}"]`);
    return node ? node.value.trim() : "";
  };
  const doLogin = async () => {
    try {
      const data = await api("/api/v1/auth/login", {
        method: "POST",
        body: JSON.stringify({ username: read("username"), password: read("password") }),
      });
      if (data.user.role !== "customer") throw new Error("请使用买家账号，例如 alice / alice123");
      sessionStorage.setItem("token_c", data.access_token);
      dialog.open = false;
      toast(`欢迎回来，${data.user.nickname}`, "ok");
      render();
    } catch (err) {
      error.textContent = err.message;
    }
  };
  submit.addEventListener("click", doLogin);
  fields.addEventListener("keydown", (event) => {
    if (event.key === "Enter") doLogin();
  });

  dialog.append(form);
  dialog.addEventListener("wa-after-hide", () => dialog.remove());
  document.body.append(dialog);
  dialog.open = true;
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
