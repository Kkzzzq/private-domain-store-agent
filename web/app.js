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
