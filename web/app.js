const STATUS = {
  on: "在售",
  off: "下架",
  banned: "禁售",
  open: "营业中",
  closed: "已停业",
  pending: "待支付",
  paid: "已支付",
  shipped: "已发货",
  completed: "已完成",
  cancelled: "已取消",
};

function money(value) {
  return `¥${Number(value || 0).toFixed(2)}`;
}

function detailOf(data) {
  if (!data) return "请求失败";
  if (typeof data.detail === "string") return data.detail;
  if (Array.isArray(data.detail)) return data.detail.map((item) => item.msg).join("；");
  return "请求失败";
}

function createApi(tokenKey) {
  return async function api(path, options = {}) {
    const headers = { ...(options.headers || {}) };
    const token = sessionStorage.getItem(tokenKey);
    if (token) headers.Authorization = `Bearer ${token}`;
    if (options.body) headers["Content-Type"] = "application/json";
    const response = await fetch(path, { ...options, headers });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(detailOf(data));
    return data;
  };
}

function statusActions(status) {
  if (status === "on") return [["off", "下架"], ["ban", "禁售"]];
  if (status === "off") return [["on", "上架"], ["ban", "禁售"]];
  return [["unban", "解禁"]];
}

function toast(message, kind = "info") {
  let host = document.querySelector(".toast-host");
  if (!host) {
    host = document.createElement("div");
    host.className = "toast-host";
    document.body.append(host);
  }
  const node = document.createElement("div");
  node.className = `toast ${kind}`;
  node.textContent = message;
  host.append(node);
  setTimeout(() => {
    node.classList.add("out");
    setTimeout(() => node.remove(), 280);
  }, 2400);
}

/** 把店铺主题色写到 :root，整站配色跟着变。 */
function applyTheme(color) {
  if (typeof color === "string" && /^#[0-9a-fA-F]{6}$/.test(color)) {
    document.documentElement.style.setProperty("--theme", color);
  }
}

function star(value) {
  const filled = "★".repeat(Math.round(value));
  const empty = "☆".repeat(Math.max(0, 5 - Math.round(value)));
  return `${filled}${empty}`;
}

/** 评分用 Web Awesome 的 wa-rating，CDN 不可用时退化成文字。 */
function ratingStars(value, { readonly = true, size = "s", label = "评分" } = {}) {
  const node = document.createElement("wa-rating");
  node.setAttribute("label", label);
  node.setAttribute("size", size);
  node.setAttribute("max", "5");
  node.setAttribute("value", String(value || 0));
  if (readonly) node.setAttribute("readonly", "");
  node.className = "stars-widget";
  return node;
}

function ratingText(value, count) {
  if (!count) return "暂无评价";
  return `${Number(value).toFixed(1)} 分 · ${count} 条评价`;
}

/** 待支付订单的剩余时间。 */
function remainText(seconds) {
  if (seconds == null) return "";
  const total = Math.max(0, Math.floor(seconds));
  const mm = String(Math.floor(total / 60)).padStart(2, "0");
  const ss = String(total % 60).padStart(2, "0");
  return `${mm}:${ss}`;
}

function maskName(name) {
  if (!name) return "买家";
  return name.length <= 1 ? name : name[0] + "*".repeat(name.length - 1);
}

