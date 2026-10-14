const params = new URLSearchParams(location.search);
let code = params.get("code") || "nanzhi";
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
  const name = parts[0] || "home";
  const rest = parts.slice(1);
  // 详情页支持 #/product/<id> 和 #/product/<店铺码>/<id> 两种写法，
  // 带着店铺码才能从收藏里跳到别家店的商品。
  const shop = rest.length > 1 ? rest[0] : "";
  const id = rest.length > 1 ? rest[1] : rest[0] || "";
  return { name, shop, id };
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
  // 进了别家店的商品，把整个页面的上下文切过去
  const current = route();
  if (current.name === "product" && current.shop && current.shop !== code) {
    code = current.shop;
    shop = null;
    cats = null;
  }
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
  try {
    view = await renderView();
  } catch (error) {
    view = h("div", "panel", error.message);
  }
  if (gen !== renderGen) return;
  const page = h("main", "wrap");
  page.append(view);
  root.replaceChildren(renderStrip(), page, renderFooter(), renderChatToggle());
  if (chatOpen) root.append(renderChat());
  watchCountdowns();
}

/* ---------------- 顶部一行：店铺名 + 购物车 / 订单 / 收藏 / 浏览记录 ---------------- */
function renderStrip() {
  const bar = h("div", "strip");
  const inner = h("div", "wrap");

  const left = h("div", "row");
  const brand = h("a", "strip-shop");
  brand.href = "#/";
  if (shop.logo_url) {
    const mark = document.createElement("img");
    mark.className = "strip-mark";
    mark.src = shop.logo_url;
    mark.alt = shop.name;
    brand.append(mark);
  } else {
    brand.append(h("span", "strip-mark", shop.name.slice(0, 1)));
  }
  brand.append(h("span", "strip-name", shop.name));
  left.append(brand);
  if (!loggedIn()) {
    const login = h("button", "strip-login", "亲，请登录");
    login.addEventListener("click", loginModal);
    left.append(login);
  }

  const nav = h("nav");
  const cart = h("a", "hvr-grow", cartCount ? `购物车（${cartCount}）` : "购物车");
  cart.href = "#/cart";
  const orders = h("a", "hvr-grow", "订单中心");
  orders.href = "#/orders";
  const favs = h("a", "hvr-grow", "我的收藏");
  favs.href = "#/favorites";
  const history = h("a", "hvr-grow", "浏览记录");
  history.href = "#/history";
  nav.append(cart, orders, favs, history);

  inner.append(left, nav);
  bar.append(inner);
  return bar;
}

/* ---------------- 顶部一行：店铺名 + 购物车 / 订单 / 收藏 / 浏览记录 ---------------- */
function renderStrip() {
  const bar = h("div", "strip");
  const inner = h("div", "wrap");

  const left = h("div", "row");
  const brand = h("a", "strip-shop");
  brand.href = "#/";
  if (shop.logo_url) {
    const mark = document.createElement("img");
    mark.className = "strip-mark";
    mark.src = shop.logo_url;
    mark.alt = shop.name;
    brand.append(mark);
  } else {
    brand.append(h("span", "strip-mark", shop.name.slice(0, 1)));
  }
  brand.append(h("span", "strip-name", shop.name));
  left.append(brand);
  if (!loggedIn()) {
    const login = h("button", "strip-login", "亲，请登录");
    login.addEventListener("click", loginModal);
    left.append(login);
  }

  const nav = h("nav");
  const cart = h("a", "hvr-grow", cartCount ? `购物车（${cartCount}）` : "购物车");
  cart.href = "#/cart";
  const orders = h("a", "hvr-grow", "订单中心");
  orders.href = "#/orders";
  const favs = h("a", "hvr-grow", "我的收藏");
  favs.href = "#/favorites";
  const history = h("a", "hvr-grow", "浏览记录");
  history.href = "#/history";
  nav.append(cart, orders, favs, history);

  inner.append(left, nav);
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
  // 有搜索或类目筛选时走列表页，其余情况是编辑好的首页
  if (keyword || category) return renderFiltered();

  const home = await api(`/api/v1/c/shops/${code}/home`);
  const box = h("div");
  box.append(heroCarousel(home.banners));
  home.sections.forEach((section) => box.append(productRow(section)));
  box.append(allProductsBlock());
  if (home.testimonials.length) box.append(reviewWall(home.testimonials));
  box.append(renderPromises());
  return box;
}

/* 轮播主视觉：整张图可点，左右箭头浮在图片两侧 */
function heroCarousel(banners) {
  if (!banners.length) return renderFallbackHero();
  const hero = h("section", "hero");

  let index = 0;
  const slides = banners.map((banner) => {
    const slide = h("div", "slide");
    const image = document.createElement("img");
    image.src = banner.image_url;
    image.alt = banner.title || shop.name;
    slide.append(image, h("div", "veil"));
    const caption = h("div", "caption");
    caption.append(h("h1", "", banner.title || shop.name));
    caption.append(h("p", "", banner.subtitle || shop.notice || "小批量手作，每一件都会有一点手工的痕迹。"));
    slide.append(caption);

    // 点图直接去商品详情；跳栏目的就滚到那一行
    const jump = {
      product: () => banner.link_value && go(`#/product/${code}/${banner.link_value}`),
      section: () =>
        document.getElementById(`sec-${banner.link_value}`)?.scrollIntoView({ behavior: "smooth", block: "start" }),
      none: () => document.querySelector(".all-sec")?.scrollIntoView({ behavior: "smooth", block: "start" }),
    }[banner.link_type] || (() => {});
    slide.addEventListener("click", (event) => {
      if (event.target.closest(".nav")) return;
      jump();
    });
    hero.append(slide);
    return slide;
  });

  const dots = h("div", "dots");
  const dotButtons = banners.map((banner, i) => {
    const dot = h("button", "", "");
    dot.title = banner.title || `第 ${i + 1} 张`;
    dot.addEventListener("click", (event) => {
      event.stopPropagation();
      show(i);
    });
    dots.append(dot);
    return dot;
  });

  function show(next) {
    index = (next + banners.length) % banners.length;
    slides.forEach((slide, i) => slide.classList.toggle("on", i === index));
    dotButtons.forEach((dot, i) => dot.classList.toggle("on", i === index));
  }

  const prev = h("button", "nav prev", "‹");
  const next = h("button", "nav next", "›");
  prev.addEventListener("click", (event) => {
    event.stopPropagation();
    show(index - 1);
    restart();
  });
  next.addEventListener("click", (event) => {
    event.stopPropagation();
    show(index + 1);
    restart();
  });
  hero.append(prev, next, dots);

  // 没人操作时自动往下走，鼠标停在图上就停
  let timer = null;
  const start = () => {
    if (banners.length < 2) return;
    timer = setInterval(() => show(index + 1), 9000);
  };
  const restart = () => {
    if (timer) clearInterval(timer);
    start();
  };
  hero.addEventListener("mouseenter", () => timer && clearInterval(timer));
  hero.addEventListener("mouseleave", restart);
  show(0);
  requestAnimationFrame(start);
  return hero;
}

function renderFallbackHero() {
  const hero = h("section", "hero");
  const slide = h("div", "slide on");
  const image = document.createElement("img");
  image.src = "/covers/hero.jpg";
  image.alt = "";
  slide.append(image, h("div", "veil"));
  const caption = h("div", "caption");
  caption.append(h("h1", "", shop.name));
  caption.append(h("p", "", shop.notice || "小批量手作，每一件都会有一点手工的痕迹。"));
  slide.append(caption);
  slide.addEventListener("click", () => {
    document.querySelector(".all-sec")?.scrollIntoView({ behavior: "smooth", block: "start" });
  });
  hero.append(slide);
  return hero;
}

/* 一行商品位：桌面显示三个，左右箭头浮在图片两侧、垂直居中 */
function productRow(section) {
  const sec = h("section", "row-sec");
  sec.id = `sec-${section.id}`;
  const head = h("div", "row-head");
  head.append(h("h2", "", section.title));
  if (section.subtitle) head.append(h("span", "sub", section.subtitle));
  sec.append(head);

  const rail = h("div", "rail");
  const track = h("div", "track");
  section.products.forEach((product) => track.append(productCard(product)));

  const prev = h("button", "rail-nav prev", "‹");
  const next = h("button", "rail-nav next", "›");
  rail.append(prev, track, next);
  sec.append(rail);

  const step = () => {
    const card = track.firstElementChild;
    return card ? card.getBoundingClientRect().width + 14 : track.clientWidth;
  };
  const sync = () => {
    const max = track.scrollWidth - track.clientWidth - 2;
    prev.disabled = track.scrollLeft <= 2;
    next.disabled = track.scrollLeft >= max || max <= 0;
  };
  prev.addEventListener("click", () => {
    track.scrollBy({ left: -step(), behavior: "smooth" });
    setTimeout(sync, 400);
  });
  next.addEventListener("click", () => {
    track.scrollBy({ left: step(), behavior: "smooth" });
    setTimeout(sync, 400);
  });
  track.addEventListener("scroll", sync);
  requestAnimationFrame(sync);
  return sec;
}

/* 全部商品：先给三行，点展开再给三行 */
function allProductsBlock() {
  const PAGE = 12;
  const sec = h("section", "all-sec");
  const head = h("div", "row-head");
  head.append(h("h2", "", "全部商品"));
  head.append(h("div", "spacer"));
  // 搜索放在「全部商品」这一行的右侧
  const form = h("form", "search all-search");
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
  head.append(form);
  sec.append(head);

  const grid = h("div", "grid");
  const foot = h("div", "all-foot");
  const expand = h("button", "expand", "展开更多");
  foot.append(expand);
  sec.append(grid, foot);

  let offset = 0;
  let busy = false;
  const load = async () => {
    busy = true;
    expand.disabled = true;
    expand.textContent = "加载中…";
    try {
      const rows = await api(`/api/v1/c/shops/${code}/products?offset=${offset}&limit=${PAGE}`);
      rows.forEach((product) => grid.append(productCard(product)));
      offset += rows.length;
      if (rows.length < PAGE) {
        expand.textContent = "已经到底啦";
        expand.disabled = true;
      } else {
        expand.textContent = "展开更多";
        expand.disabled = false;
      }
    } catch (error) {
      toast(error.message, "bad");
      expand.textContent = "展开更多";
      expand.disabled = false;
    }
    busy = false;
  };
  expand.addEventListener("click", () => {
    if (!busy) load();
  });
  requestAnimationFrame(() => load());
  return sec;
}

/* 用户评价流动展示，两排反向滚 */
function reviewWall(rows) {
  const wall = h("section", "wall");
  const head = h("div", "wall-head");
  head.append(h("h2", "", "他们怎么说"), h("p", "", "来自这家店买家的真实反馈，店主可以在后台维护"));
  wall.append(head);

  const quote = (row) => {
    const card = h("div", "quote");
    const who = h("div", "who");
    who.append(h("span", "avatar", row.nickname.slice(0, 1)));
    const name = h("div", "name");
    name.append(h("div", "", maskName(row.nickname)), ratingStars(row.rating));
    who.append(name);
    card.append(who, h("p", "", row.content));
    return card;
  };
  const half = Math.ceil(rows.length / 2);
  [rows.slice(0, half), rows.slice(half)].forEach((group, i) => {
    if (!group.length) return;
    const marquee = h("div", i === 1 ? "marquee rev" : "marquee");
    const strip = h("div", "strip2");
    // 复制一份首尾相接，滚动才不会有断点
    [...group, ...group].forEach((row) => strip.append(quote(row)));
    marquee.append(strip);
    wall.append(marquee);
  });
  return wall;
}

/* 带筛选的列表页 */
async function renderFiltered() {
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
  layout.append(renderCategorySide(all.length, counts), renderFilteredMain(filtered));
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
    // 回到首页，关键词和类目一起清掉
    category = "";
    keyword = "";
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

function renderFilteredMain(filtered) {
  const main = h("div");
  const bar = h("div", "toolbar");
  const parts = [`共 ${filtered.length} 件商品`];
  if (keyword) parts.push(`关键词「${keyword}」`);
  if (category) parts.push(`类目「${category}」`);
  const info = h("div", "row");
  info.append(h("span", "muted", parts.join(" · ")));
  const clear = h("button", "btn-ghost btn-mini", "回到首页");
  clear.addEventListener("click", () => {
    keyword = "";
    category = "";
    render();
  });
  info.append(clear);
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
    empty.append(h("p", "", "换个关键词或类目试试"));
    const reset = h("button", "btn", "看全部商品");
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
    const result = await api(`/api/v1/c/favorites/${product.id}`, { method: "POST" });
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
  thumb.href = `#/product/${code}/${product.id}`;
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

  // 图片左下角一个小购物车，点了在当前页面弹小窗选规格
  const cart = h("button", "thumb-cart", "🛒");
  cart.title = "加入购物车 / 直接购买";
  cart.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    quickBuy(product);
  });
  thumb.append(cart);

  // 图片右下角放最低价
  const badge = h("div", "thumb-price");
  badge.append(h("i", "", "¥"), h("b", "", Number(product.price_from || 0).toFixed(2)));
  if (product.market_from) badge.append(h("span", "price-was", `¥${Number(product.market_from).toFixed(2)}`));
  thumb.append(badge);

  const body = h("div", "body");
  const title = h("a", "title", product.name);
  title.href = `#/product/${code}/${product.id}`;
  body.append(title);

  const meta = h("div", "meta");
  const rating = h("span", "stars");
  rating.append(
    ratingStars(product.rating_avg || 0),
    document.createTextNode(ratingText(product.rating_avg, product.review_count))
  );
  meta.append(rating, h("span", "", `已售 ${product.sales_count}`));
  if (product.limit_per_user) meta.append(h("span", "ship-tag", `限购${product.limit_per_user}`));
  body.append(meta);

  card.append(thumb, body);
  return card;
}

/** 卡片上的小购物车：在当前页面弹小窗，选规格后加购或直接买。 */
function quickBuy(product) {
  if (!requireLogin()) return;
  const mask = h("div", "modal quick-mask");
  const panel = h("div", "panel quick-panel");

  const close = h("button", "quick-close", "×");
  close.addEventListener("click", () => mask.remove());
  mask.addEventListener("click", (event) => {
    if (event.target === mask) mask.remove();
  });

  const top = h("div", "quick-top");
  const image = document.createElement("img");
  image.src = cover(product.image_url);
  image.alt = product.name;
  const info = h("div", "quick-info");
  info.append(h("h3", "", product.name));
  const skuCount = (product.skus || []).length;
  info.append(h("div", "muted", `${product.category} · ${skuCount} 个规格可选`));
  const priceRow = h("div", "quick-price");
  const priceText = h("b", "", "");
  const wasText = h("span", "price-was", "");
  priceRow.append(h("i", "", "¥"), priceText, wasText);
  info.append(priceRow);
  top.append(image, info);
  panel.append(close, top);

  // 规格
  let current = (product.skus || []).find((sku) => sku.purchasable) || product.skus?.[0] || null;
  panel.append(h("div", "field-label", "选择规格"));
  const specs = h("div", "sku-list");
  (product.skus || []).forEach((sku) => {
    const button = h("button", sku.id === current?.id ? "on" : "", sku.spec);
    if (!sku.purchasable) button.classList.add("dead");
    button.addEventListener("click", () => {
      current = sku;
      [...specs.children].forEach((item) => item.classList.remove("on"));
      button.classList.add("on");
      paint();
    });
    specs.append(button);
  });
  panel.append(specs);

  // 数量
  panel.append(h("div", "field-label", "购买数量"));
  const qtyInput = document.createElement("input");
  qtyInput.value = "1";
  qtyInput.inputMode = "numeric";
  const qty = h("div", "qty");
  const minus = h("button", "", "−");
  const plus = h("button", "", "+");
  const clamp = () => {
    const cap = Math.min(20, product.limit_per_user || 20, current ? Math.max(1, current.stock) : 20);
    const value = Math.max(1, Math.min(cap, Number(qtyInput.value) || 1));
    qtyInput.value = String(value);
    return value;
  };
  minus.addEventListener("click", () => {
    qtyInput.value = String(Math.max(1, Number(qtyInput.value) - 1));
  });
  plus.addEventListener("click", () => {
    qtyInput.value = String(Number(qtyInput.value) + 1);
    clamp();
  });
  qtyInput.addEventListener("change", clamp);
  qty.append(minus, qtyInput, plus);
  panel.append(qty);

  const stockNote = h("p", "muted", "");
  panel.append(stockNote);

  function paint() {
    if (!current) {
      priceText.textContent = "暂无规格";
      wasText.textContent = "";
      stockNote.textContent = "";
      return;
    }
    priceText.textContent = Number(current.price_yuan).toFixed(2);
    wasText.textContent = current.market_price_yuan ? `¥${Number(current.market_price_yuan).toFixed(2)}` : "";
    stockNote.textContent = current.purchasable
      ? `库存 ${current.stock} 件${product.limit_per_user ? ` · 每人限购 ${product.limit_per_user} 件` : ""}`
      : "该规格暂时缺货";
  }

  const actions = h("div", "quick-actions");
  const add = h("button", "btn-cart btn-big", "加入购物车");
  const buy = h("button", "btn-buy btn-big", "立即购买");
  const disabled = !current || !current.purchasable;
  add.disabled = disabled;
  buy.disabled = disabled;
  add.addEventListener("click", async () => {
    if (!current) return;
    try {
      const cart = await api(`/api/v1/c/shops/${code}/cart`, {
        method: "POST",
        body: JSON.stringify({ sku_id: current.id, quantity: clamp() }),
      });
      cartCount = cart.items.reduce((sum, item) => sum + item.quantity, 0);
      mask.remove();
      toast("已加入购物车", "ok");
      render();
    } catch (error) {
      toast(error.message, "bad");
    }
  });
  buy.addEventListener("click", () => {
    if (!current) return;
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
    code = product.shop_share_code || code;
    mask.remove();
    go("#/checkout");
  });
  actions.append(add, buy);
  panel.append(actions);
  paint();

  mask.append(panel);
  document.body.append(mask);
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

/** 详情页下方的推荐位，同类优先，最多 6 个，一样是一行三个可以翻页。 */
function renderRelated(product, all) {
  const others = all.filter((item) => item.id !== product.id);
  const same = others.filter((item) => item.category === product.category);
  const picks = [...same, ...others].slice(0, 6);
  if (!picks.length) return h("div");
  return productRow({
    id: "related",
    title: same.length ? `同类手作 · ${product.category}` : "看了还看",
    subtitle: "换一件也合适",
    products: picks,
  });
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

/* ---------------- 收藏 / 浏览记录（跨店铺，下架的也保留） ---------------- */
/** 这两个页面里的卡片要带店铺名和上下架标注，所以单独做一套。 */
function savedCard(item, { showRemove = false } = {}) {
  const card = h("article", item.available ? "pcard" : "pcard dim");
  const thumb = h("div", "thumb");
  const image = document.createElement("img");
  image.src = cover(item.image_url);
  image.alt = item.name;
  image.loading = "lazy";
  thumb.append(image);
  const off = discountOf(item.price_from, item.market_from);
  if (off) thumb.append(h("span", "tag", off));
  if (!item.available) thumb.append(h("span", "shelf-flag", item.shelf_label));
  card.append(thumb);

  const body = h("div", "body");
  const title = h("a", "title", item.name);
  const detailHref = `#/product/${item.shop_share_code}/${item.id}`;
  if (item.available) {
    title.href = detailHref;
  } else {
    // 下架或禁售的商品没有详情页，点了给个说明
    title.href = "javascript:void(0)";
    title.addEventListener("click", () => toast(`该商品${item.shelf_label}，暂时看不了详情`));
  }
  body.append(title);

  const meta = h("div", "meta");
  const shopLink = h("a", "link hvr-underline-from-center", item.shop_name || "本店");
  shopLink.href = item.available ? detailHref : "javascript:void(0)";
  const stars = h("span", "stars");
  stars.append(ratingStars(item.rating_avg || 0), document.createTextNode(ratingText(item.rating_avg, item.review_count)));
  meta.append(shopLink, stars);
  body.append(meta);

  const foot = h("div", "foot");
  const price = h("div", "price");
  price.append(h("i", "", "¥"), h("b", "", Number(item.price_from || 0).toFixed(2)));
  if (item.market_from) price.append(h("span", "price-was", `¥${Number(item.market_from).toFixed(2)}`));
  foot.append(price);
  if (!item.available) foot.append(h("span", "ship-tag off", item.shelf_label));
  else foot.append(h("span", "ship-tag", "包邮"));
  body.append(foot);

  const actions = h("div", "saved-actions");
  if (item.available) {
    const add = h("button", "btn-cart btn-mini", "加入购物车");
    add.addEventListener("click", async () => {
      const sku = (item.skus || []).find((row) => row.purchasable);
      if (!sku) return toast("这件商品暂时缺货", "bad");
      try {
        const cart = await api(`/api/v1/c/shops/${item.shop_share_code}/cart`, {
          method: "POST",
          body: JSON.stringify({ sku_id: sku.id, quantity: 1 }),
        });
        cartCount = cart.items.reduce((sum, row) => sum + row.quantity, 0);
        toast("已加入购物车", "ok");
        render();
      } catch (error) {
        toast(error.message, "bad");
      }
    });
    actions.append(add);
  } else {
    const gone = h("button", "btn-ghost btn-mini", "已不可购买");
    gone.disabled = true;
    actions.append(gone);
  }
  if (showRemove) {
    const remove = h("button", "btn-ghost btn-mini", "取消收藏");
    remove.addEventListener("click", async () => {
      await api(`/api/v1/c/favorites/${item.id}`, { method: "POST" });
      toast("已取消收藏", "ok");
      render();
    });
    actions.append(remove);
  }
  body.append(actions);
  card.append(body);
  return card;
}

function savedPanel(title, items, { showRemove = false, onClear = null, note = "" } = {}) {
  const box = h("div");
  const panel = h("div", "panel");
  const head = h("h2", "panel-title", `${title}（${items.length}）`);
  if (onClear && items.length) {
    const clear = h("button", "btn-ghost btn-mini", "清空记录");
    clear.style.marginLeft = "auto";
    clear.addEventListener("click", onClear);
    head.append(clear);
  }
  panel.append(head);
  if (note) panel.append(h("p", "muted", note));
  if (!items.length) {
    panel.append(h("p", "muted", "这里还是空的。"));
    box.append(panel);
    return box;
  }
  const grid = h("div", "grid");
  grid.style.padding = "0";
  items.forEach((item) => grid.append(savedCard(item, { showRemove })));
  panel.append(grid);
  box.append(panel);
  return box;
}

async function renderFavorites() {
  if (!requireLogin()) {
    return emptyPanel("请先登录买家账号", "登录后可以看到收藏的商品", "立即登录", loginModal);
  }
  const items = await api("/api/v1/c/favorites");
  const offline = items.filter((item) => !item.available).length;
  return savedPanel("我的收藏", items, {
    showRemove: true,
    note: `不同店铺的商品可以收在一起。${offline ? `其中 ${offline} 件已经下架或禁售，仍然留在这里。` : ""}`,
  });
}

async function renderHistory() {
  if (!requireLogin()) {
    return emptyPanel("请先登录买家账号", "登录后可以看到浏览记录", "立即登录", loginModal);
  }
  const items = await api("/api/v1/c/history");
  return savedPanel("浏览记录", items, {
    note: "只保留最近 7 天看过的商品，不分店铺。",
    onClear: async () => {
      await api("/api/v1/c/history", { method: "DELETE" });
      toast("浏览记录已清空", "ok");
      render();
    },
  });
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
    title.href = `#/product/${code}/${item.product_id}`;
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
