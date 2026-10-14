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
let lastRoute = "";
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
  // 带着店铺码才能从浏览记录里跳到别家店的商品。
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
  // 只要换了页面，就把滚动位置拉回顶部。否则从很长的首页点进详情页会停在底部。
  const here = [current.name, current.shop, current.id].join("/");
  const moved = here !== lastRoute;
  lastRoute = here;
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
  // 顶部那层浅色过线的渐变画在 body 背景上，内容永远不会被它盖住
  document.body.classList.toggle("tinted", shop.strip_tint !== false);
  if (chatOpen) root.append(renderChat());
  // 换页才回顶，同页内的筛选、加购刷新不动滚动位置
  if (moved) window.scrollTo({ top: 0, left: 0 });
  watchCountdowns();
}

/* ---------------- 顶部一行：店铺名 + 购物车 / 订单 / 浏览记录 ---------------- */
function renderStrip() {
  const bar = h("div", shop.strip_tint === false ? "strip" : "strip tinted");
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
  const history = h("a", "hvr-grow", "浏览记录");
  history.href = "#/history";
  nav.append(cart, orders, history);

  inner.append(left, nav);
  bar.append(inner);
  return bar;
}

async function renderView() {
  const current = route();
  if (current.name === "product") return renderProduct(current.id);
  if (current.name === "collection") return renderCollection(current.id || "all");
  if (current.name === "cart") return renderCart();
  if (current.name === "checkout") return renderCheckout();
  if (current.name === "orders") return renderOrders(current.id);
  if (current.name === "history") return renderHistory();
  if (current.name === "reviews") return renderPendingReviews();
  return renderHome();
}

/* ---------------- 首页 ---------------- */
async function renderHome() {
  // 有搜索或类目筛选时也走合集页
  if (keyword || category) return renderCollection("all");

  const home = await api(`/api/v1/c/shops/${code}/home`);
  const box = h("div");
  box.append(heroCarousel(home.banners));
  home.sections.forEach((section) => box.append(productRow(section)));
  // 评价墙放在全部商品上面，先让买家看到别人怎么说
  if (home.testimonials.length) box.append(reviewWall(home.testimonials));
  box.append(allProductsBlock());
  box.append(renderPromises(shop.promises));
  return box;
}

/* ---------------- 合集页：左侧筛选，右侧商品 ---------------- */
async function renderCollection(key) {
  const query = new URLSearchParams({ keyword, category, sort });
  let data;
  try {
    data = await api(`/api/v1/c/shops/${code}/collections/${key}?${query}`);
  } catch (error) {
    return h("div", "panel", error.message);
  }

  const box = h("div");
  const crumb = h("div", "crumb");
  const home = h("a", "", "首页");
  home.href = "#/";
  crumb.append(home, h("span", "", " / "), h("span", "", data.title));
  box.append(crumb);

  const layout = h("div", "collection");
  layout.append(collectionSide(data), collectionMain(data));
  box.append(layout);
  return box;
}

/** 左侧：先按类目筛，再排序。 */
function collectionSide(data) {
  const side = h("aside", "cat-side");
  const title = h("h3");
  title.append(document.createTextNode("商品分类"), h("small", "", `${data.total} 件`));
  side.append(title);

  const all = h("button", category ? "" : "on");
  all.append(h("span", "", "全部"), h("i", "", String(data.total)));
  all.addEventListener("click", () => {
    category = "";
    keyword = "";
    render();
  });
  side.append(all);
  data.categories.forEach((item) => {
    const button = h("button", category === item ? "on" : "");
    button.append(h("span", "", item), h("i", "", String(data.category_counts?.[item] ?? "")));
    button.addEventListener("click", () => {
      category = category === item ? "" : item;
      keyword = "";
      render();
    });
    side.append(button);
  });

  const sortBlock = h("div", "cat-sort");
  sortBlock.append(h("div", "cat-sort-title", "排序"));
  [
    ["default", "综合"],
    ["sales", "销量"],
    ["price_asc", "价格从低到高"],
    ["price_desc", "价格从高到低"],
  ].forEach(([value, label]) => {
    const button = h("button", sort === value ? "on" : "");
    button.append(h("span", "", label), h("i", "", ""));
    button.addEventListener("click", () => {
      sort = value;
      render();
    });
    sortBlock.append(button);
  });
  side.append(sortBlock);
  return side;
}

/** 右侧：上面一个搜索框，下面商品。 */
function collectionMain(data) {
  const main = h("div", "collection-main");

  const head = h("div", "collection-head");
  const words = h("div");
  words.append(h("h2", "", data.title));
  const parts = [`共 ${data.products.length} 件`];
  if (keyword) parts.push(`关键词「${keyword}」`);
  if (category) parts.push(`类目「${category}」`);
  words.append(h("div", "muted", parts.join(" · ")));
  head.append(words);

  const form = h("form", "search collection-search");
  const input = document.createElement("input");
  input.placeholder = `在${data.title}里搜索`;
  input.value = keyword;
  form.append(input, h("button", "", "搜索"));
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    keyword = input.value.trim();
    render();
  });
  head.append(form);
  main.append(head);

  if (!data.products.length) {
    const empty = h("div", "empty");
    empty.append(h("div", "icon", "🔍"));
    empty.append(h("h3", "", "没有找到相关商品"));
    empty.append(h("p", "", "换个关键词或类目试试"));
    const reset = h("button", "btn", "清除筛选");
    reset.addEventListener("click", () => {
      keyword = "";
      category = "";
      sort = "default";
      render();
    });
    empty.append(reset);
    main.append(empty);
    return main;
  }

  const grid = h("div", "grid");
  data.products.forEach((product) => grid.append(productCard(product)));
  main.append(grid);
  return main;
}

/* 轮播主视觉：整张图可点，左右箭头浮在图片两侧。
   图片后面垫一层同一张图的模糊放大版，两侧做渐变，让图片看着往外扩出去。 */
function heroCarousel(banners) {
  if (!banners.length) return renderFallbackHero();
  const hero = h("section", "hero");
  hero.style.setProperty("--hero-h", `${shop.hero_height || 640}px`);

  let index = 0;
  const slides = banners.map((banner) => {
    const slide = h("div", "slide");
    // 模糊底：和主图同一张，放大后糊掉，左右两边透出来就是“渐变”
    const blur = h("div", "blur");
    blur.style.backgroundImage = `url("${banner.image_url}")`;
    const image = document.createElement("img");
    image.src = banner.image_url;
    image.alt = banner.title || shop.name;
    slide.append(blur, image, h("div", "veil"));
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
  hero.style.setProperty("--hero-h", `${shop.hero_height || 640}px`);
  const slide = h("div", "slide on");
  const blur = h("div", "blur");
  blur.style.backgroundImage = 'url("/covers/hero.jpg")';
  const image = document.createElement("img");
  image.src = "/covers/hero.jpg";
  image.alt = "";
  slide.append(blur, image, h("div", "veil"));
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
  const href = section.href === undefined ? `#/collection/${section.id}` : section.href;
  sec.append(rowHead(section.title, section.subtitle, href));

  const rail = h("div", "rail");
  const track = h("div", "track");
  section.products.forEach((product) => track.append(productCard(product)));

  const prev = h("button", "rail-nav prev", "‹");
  const next = h("button", "rail-nav next", "›");
  rail.append(prev, track, next);
  sec.append(rail);

  const step = () => {
    const card = track.firstElementChild;
    return card ? card.getBoundingClientRect().width + 17 : track.clientWidth;
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

/** 每行的标题栏：标题 + 副标题 + 右侧「查看全部」，点了进对应的合集页。 */
function rowHead(title, subtitle, href, extra = null) {
  const head = h("div", "row-head");
  head.append(h("h2", "", title));
  if (subtitle) head.append(h("span", "sub", subtitle));
  if (extra) head.append(extra);
  head.append(h("div", "spacer"));
  if (href) {
    const more = h("a", "see-all hvr-underline-from-center", "查看全部 ›");
    more.href = href;
    head.append(more);
  }
  return head;
}

/* 全部商品：默认两行（8 件），点展开继续往下给；到底后按钮变「收回」 */
function allProductsBlock() {
  const PAGE = 8;
  const sec = h("section", "all-sec");

  const form = h("form", "search all-search");
  const input = document.createElement("input");
  input.placeholder = "搜索本店商品";
  input.value = keyword;
  form.append(input, h("button", "", "搜索"));
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    keyword = input.value.trim();
    category = "";
    go("#/collection/all");
  });

  sec.append(rowHead("全部商品", "店里所有在售的东西", "#/collection/all", form));

  const grid = h("div", "grid");
  const foot = h("div", "all-foot");
  const expand = h("button", "expand", "展开更多");
  foot.append(expand);
  sec.append(grid, foot);

  let items = []; // 已经拉到的商品
  let hasMore = true; // 服务端还有没有下一批
  let expanded = false; // 是否处于展开状态
  let busy = false;

  const paint = () => {
    const shown = expanded ? items : items.slice(0, PAGE);
    grid.replaceChildren(...shown.map(productCard));
    // 商品本来就不到两行、也没得再展开时，按钮就没必要出现了
    if (!expanded && !hasMore && items.length <= PAGE) {
      foot.hidden = true;
      return;
    }
    foot.hidden = false;
    expand.disabled = busy;
    if (busy) expand.textContent = "加载中…";
    else if (expanded && !hasMore) expand.textContent = "收回";
    else expand.textContent = "展开更多";
  };

  const load = async () => {
    if (busy || !hasMore) return;
    busy = true;
    paint();
    try {
      const rows = await api(`/api/v1/c/shops/${code}/products?offset=${items.length}&limit=${PAGE}`);
      items = items.concat(rows);
      if (rows.length < PAGE) hasMore = false;
    } catch (error) {
      toast(error.message, "bad");
    }
    busy = false;
    paint();
  };

  expand.addEventListener("click", async () => {
    if (busy) return;
    // 已经展开且到底了：点一下收回成两行
    if (expanded && !hasMore) {
      expanded = false;
      paint();
      sec.scrollIntoView({ block: "start", behavior: "smooth" });
      return;
    }
    if (!expanded) expanded = true;
    await load();
    paint();
  });

  requestAnimationFrame(load);
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

function renderPromises(rows) {
  const box = h("div", "promises");
  (rows && rows.length ? rows : []).forEach((row) => {
    const cell = h("div");
    cell.append(h("b", "", row.title), h("span", "muted", row.sub));
    box.append(cell);
  });
  return box;
}

/* 卡片左上角的角标：优先用商家自定义的标签，没挂标签时退回折扣 / 热销。
   标签底色和字色都由商家配的那个颜色推出来（浅底 + 同色字），不用白字。 */
function tagBadge(product) {
  const custom = (product.tags || [])[0];
  const node = custom
    ? h("span", "tag", custom.name)
    : (() => {
        const off = discountOf(product.price_from, product.market_from);
        if (off) return h("span", "tag", off);
        if (product.sales_count >= 50) return h("span", "tag", "热销");
        return null;
      })();
  if (!node) return null;
  node.classList.add("soft");
  if (custom && custom.color) node.style.setProperty("--tag", custom.color);
  return node;
}

/**
 * 商品卡：首页、合集页、浏览记录共用同一套。
 * 卡片上只有图片 + 左上角标签 + 左下角小购物车，名称和价格在悬停浮层里。
 * opts.shopCode 用来指向商品所属店铺（浏览记录是跨店的）；
 * opts.extra 打开后，浮层里会多一行店铺名，下架商品也按标注处理。
 */
function productCard(product, { shopCode = code, extra = false } = {}) {
  const available = product.available !== false;
  const card = h("article", available ? "pcard" : "pcard dim");
  const href = `#/product/${shopCode}/${product.id}`;

  const thumb = h("a", "thumb");
  thumb.href = available ? href : "javascript:void(0)";
  thumb.title = `${product.name} · ¥${Number(product.price_from || 0).toFixed(2)}`;
  if (!available) {
    // 下架或禁售的商品没有详情页，点了给个说明
    thumb.addEventListener("click", (event) => {
      event.preventDefault();
      toast(`该商品${product.shelf_label}，暂时看不了详情`);
    });
  }
  const image = document.createElement("img");
  image.src = cover(product.image_url);
  image.alt = product.name;
  image.loading = "lazy";
  thumb.append(image);

  // 悬停时在图片顶部浮出名称和价格，平时只有图
  const hover = h("div", "thumb-name");
  hover.append(h("span", "hover-title", product.name));
  if (extra && product.shop_name) hover.append(h("span", "hover-shop", product.shop_name));
  const hoverPrice = h("span", "hover-price");
  hoverPrice.append(h("i", "", "¥"), h("b", "", Number(product.price_from || 0).toFixed(2)));
  if (product.market_from) {
    hoverPrice.append(h("span", "price-was", `¥${Number(product.market_from).toFixed(2)}`));
  }
  hover.append(hoverPrice);
  thumb.append(hover);

  const badge = tagBadge(product);
  if (badge) thumb.append(badge);
  if (!available) thumb.append(h("span", "shelf-flag", product.shelf_label));

  // 图片左下角一个小购物车，点了在当前页面弹小窗选规格
  const cart = h("button", "thumb-cart", "🛒");
  cart.title = available ? "加入购物车 / 直接购买" : `该商品${product.shelf_label}`;
  cart.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    if (!available) return toast(`该商品${product.shelf_label}，暂时不能加购`);
    quickBuy(product, shopCode);
  });
  thumb.append(cart);

  card.append(thumb);
  return card;
}

/** 卡片上的小购物车：在当前页面弹小窗，选规格后加购或直接买。
    shopCode 是商品所属的店铺，浏览记录里跨店加购要靠它。 */
function quickBuy(product, shopCode = code) {
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
      const cart = await api(`/api/v1/c/shops/${shopCode}/cart`, {
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
    // 结算页要按商品所属的店来算运费，跨店加购时用它自己的店铺码
    code = shopCode || code;
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
  home.href = "#/collection/all";
  crumb.append(home, h("span", "", " / "), h("span", "", `${product.category} / ${product.name}`));
  box.append(crumb);

  const state = createDetailState(product);
  const layout = h("div", "detail");
  layout.append(renderGallery(product, state));
  layout.append(renderProductInfo(product, state));
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
    // 推荐位没有对应的合集页，不挂「查看全部」
    href: "",
    products: picks,
  });
}

/** 详情页的共享状态：当前规格 + 当前看的是第几张图，两边互相联动。

    图源按规格来：每个规格可以带一张自己的图（商家在后台传），
    缩略图和左右箭头走的就是这份列表；点缩略图等于选那个规格，
    选规格又会把主图跳到这张规格图上。
*/
function createDetailState(product) {
  const images = [];
  const seen = new Set();
  product.skus.forEach((sku) => {
    const url = (sku.image_url || "").trim();
    if (!url || seen.has(url)) return;
    seen.add(url);
    images.push({ url, sku });
  });
  // 规格都没配图时退回商品主图，这张不对应任何规格
  if (!images.length && product.image_url) images.push({ url: product.image_url, sku: null });

  const listeners = new Set();
  const state = {
    product,
    images,
    index: 0,
    sku: product.skus.find((item) => item.purchasable) || product.skus[0] || null,
    onChange(fn) {
      listeners.add(fn);
    },
    notify() {
      listeners.forEach((fn) => fn());
    },
    /** 只翻图：翻到哪张，如果这张绑了规格就顺便把规格切过去。 */
    showIndex(next) {
      if (images.length < 2) return;
      state.index = (next + images.length) % images.length;
      const item = images[state.index];
      if (item.sku) state.sku = item.sku;
      state.notify();
    },
    /** 选规格：主图跳到这个规格的图。 */
    selectSku(sku) {
      if (!sku) return;
      state.sku = sku;
      const at = images.findIndex((item) => item.sku && item.sku.id === sku.id);
      if (at >= 0) state.index = at;
      state.notify();
    },
    /** 点缩略图：图和人一起切。 */
    selectImage(at) {
      state.index = at;
      const item = images[at];
      if (item.sku) state.sku = item.sku;
      state.notify();
    },
  };

  const first = images.findIndex((item) => item.sku && state.sku && item.sku.id === state.sku.id);
  if (first >= 0) state.index = first;
  return state;
}

function renderGallery(product, state) {
  const gallery = h("div", "gallery");
  const thumbs = h("div", "thumbs");
  const main = h("div", "main");
  const image = document.createElement("img");
  const caption = h("span", "shot-spec", "");
  const prev = h("button", "shot-nav prev", "‹");
  const next = h("button", "shot-nav next", "›");
  prev.type = "button";
  next.type = "button";
  prev.title = "上一张（对应上一个规格）";
  next.title = "下一张（对应下一个规格）";
  main.append(image, caption, prev, next);

  prev.addEventListener("click", () => state.showIndex(state.index - 1));
  next.addEventListener("click", () => state.showIndex(state.index + 1));

  const paint = () => {
    const item = state.images[state.index];
    const url = item ? item.url : product.image_url;
    image.src = cover(url || product.image_url);
    image.alt = item && item.sku ? `${product.name} ${item.sku.spec}` : product.name;
    if (item && item.sku) {
      caption.textContent = item.sku.spec;
      caption.hidden = false;
    } else {
      caption.hidden = true;
    }
    const many = state.images.length > 1;
    prev.hidden = !many;
    next.hidden = !many;
    // 规格切换时高亮跟着走
    [...thumbs.children].forEach((button, at) => button.classList.toggle("on", at === state.index));
  };

  // 缩略图一张对一个规格，点哪张就选哪个规格
  state.images.forEach((item, at) => {
    const button = h("button", "", "");
    button.type = "button";
    button.title = item.sku ? `${item.sku.spec} 效果图` : product.name;
    const thumb = document.createElement("img");
    thumb.src = cover(item.url);
    thumb.alt = item.sku ? `${product.name} ${item.sku.spec}` : product.name;
    button.append(thumb);
    if (item.sku) {
      const label = h("span", "thumb-spec", item.sku.spec);
      button.append(label);
    }
    button.addEventListener("click", () => state.selectImage(at));
    thumbs.append(button);
  });

  state.onChange(paint);
  paint();
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
  const add = h("button", "btn-cart btn-big", "加入购物车");
  const buy = h("button", "btn-buy btn-big", "立即购买");
  add.addEventListener("click", ctx.addToCart);
  buy.addEventListener("click", ctx.buyNow);
  inner.append(image, words, spacer, price, add, buy);
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

function renderProductInfo(product, state) {
  const info = h("div", "info");
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

  let current = state.sku;
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
    current = state.sku;
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
    // 规格按钮的高亮跟着状态走，这样从缩略图或箭头切过来也会对上
    [...specs.children].forEach((button) => button.classList.toggle("on", button.dataset.skuId === String(current.id)));
  }

  info.append(pricebox, promotions);
  info.append(h("div", "field-label", "选择规格"));
  const specs = h("div", "sku-list");
  product.skus.forEach((sku) => {
    const button = h("button", sku.id === current?.id ? "on" : "", sku.spec);
    button.dataset.skuId = String(sku.id);
    if (!sku.purchasable) button.classList.add("dead");
    button.addEventListener("click", () => state.selectSku(sku));
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
  const syncActions = () => {
    const usable = Boolean(current && current.purchasable);
    add.disabled = !usable;
    buy.disabled = !usable;
  };
  syncActions();
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
  actions.append(add, buy);
  info.append(actions);
  info.append(
    renderBuyBar(product, { addToCart, buyNow, price: () => current?.price_yuan, spec: () => current?.spec })
  );

  const services = h("div", "services");
  ["正品保障", "7 天无理由退货", "满 99 元包邮", "48 小时内发货"].forEach((text) => services.append(h("span", "", text)));
  info.append(services);
  // 先注册 paint（它会把 current 同步成最新规格），再注册按钮状态
  state.onChange(paint);
  state.onChange(syncActions);
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

/* ---------------- 浏览记录（跨店铺，下架的也保留） ---------------- */
function savedPanel(title, items, { onClear = null, note = "" } = {}) {
  const box = h("div");
  const panel = h("div", "panel saved-panel");
  const head = h("h2", "panel-title", `${title}（${items.length}）`);
  if (onClear && items.length) {
    const clear = h("button", "btn-ghost btn-mini", "清空记录");
    clear.style.marginLeft = "auto";
    clear.addEventListener("click", onClear);
    head.append(clear);
  }
  panel.append(head);
  if (note) panel.append(h("p", "muted note", note));
  if (!items.length) {
    panel.append(h("p", "muted", "这里还是空的。"));
    box.append(panel);
    return box;
  }
  const grid = h("div", "grid");
  // 和首页同一套卡片，只是多带店铺名，链接指向商品自己那家店
  items.forEach((item) => grid.append(productCard(item, { shopCode: item.shop_share_code, extra: true })));
  panel.append(grid);
  box.append(panel);
  return box;
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

  order.items.forEach((item, index) => {
    const line = h("div", index % 2 ? "order-line alt" : "order-line");
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
