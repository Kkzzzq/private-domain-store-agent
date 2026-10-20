/* Shared login / registration UI. No sample credentials or password storage. */
window.StoreAuth = (() => {
  // Shared across same-origin tabs; page-specific state stays in sessionStorage.
  const sharedKey = 'store_account_session';
  function restoreSession() {
    try {
      const raw = localStorage.getItem(sharedKey);
      if (raw === 'null') for (const key of ['token_b','token_c','account_shared','portal_role']) sessionStorage.removeItem(key);
      const saved = JSON.parse(raw || 'null');
      if (saved) for (const key of ['token_b','token_c','account_shared','portal_role']) {
        if (saved[key]) sessionStorage.setItem(key, saved[key]); else sessionStorage.removeItem(key);
      }
    } catch {}
  }
  restoreSession();
  const el = (tag, cls, text) => {
    const node = document.createElement(tag); if (cls) node.className = cls;
    if (text != null) node.textContent = text; return node;
  };
  function createForm(options = {}) {
    const root = el("section", "auth-card");
    let mode = "login", role = options.role || "customer", username = options.username || "", busy = false, controller;
    root.dispose = () => controller?.abort();
    function paint() {
      root.replaceChildren();
      const eyebrow = el("p", "auth-eyebrow", "A LITTLE STORE, A LOVELY EVERYDAY");
      const title = el("h1", "auth-title", mode === "login" ? "欢迎回来" : "创建你的账号");
      root.append(eyebrow, title, el("p", "auth-description", mode === "register" ? "创建你的账号，开启一段新的小店日常。" : "使用当前账号购物；获授权后可进入商家工作台。"));
      const tabs = el("div", "auth-tabs");
      for (const [value, label] of [["login", "登录"], ["register", "注册"]]) {
        const tab = el("button", mode === value ? "active" : "", label); tab.type = "button";
        tab.setAttribute("aria-pressed", String(mode === value));
        tab.addEventListener("click", () => { if (!busy) { username = root.querySelector('[name="username"]').value; mode = value; paint(); } });
        tabs.append(tab);
      }
      root.append(tabs);
      const form = el("form", "auth-form");
      const field = (label, name, type, placeholder, required = true) => {
        const wrap = el("label", "auth-field"); wrap.append(el("span", "", label));
        const input = el("input"); input.type = type; input.name = name; input.required = required; input.placeholder = placeholder;
        if (name === "password" && mode === "login" && options.demo) input.value = options.password || "";
        input.maxLength = name === "username" || name === "nickname" ? 32 : 64;
        input.autocomplete = name === "username" ? "username" : name === "password" ? (mode === "login" ? "current-password" : "new-password") : "off";
        if (name === "username") { input.value = username; if (mode === "register") { input.pattern = "[A-Za-z0-9_]{3,32}"; input.title = "3至32位字母、数字或下划线"; } }
        if (mode === "register" && type === "password") input.minLength = 6;
        wrap.append(input); form.append(wrap);
      };
      field("账号", "username", "text", mode === "login" ? "请输入账号" : "3至32位字母、数字或下划线");
      if (mode === "register") field("昵称", "nickname", "text", "怎么称呼你（选填）", false);
      field("密码", "password", "password", mode === "login" ? "请输入密码" : "设置至少6位密码");
      if (mode === "register") field("确认密码", "confirm_password", "password", "再次输入密码");
      const error = el("p", "auth-error"); error.setAttribute("role", "alert");
      const submit = el("button", "auth-submit", mode === "login" ? "登录并继续" : "注册并进入"); submit.type = "submit";
      form.append(error, submit);
      form.addEventListener("submit", async event => {
        event.preventDefault(); if (busy) return;
        error.textContent = "";
        if (mode === "register" && form.elements.password.value !== form.elements.confirm_password.value) { error.textContent = "两次输入的密码不一致"; return; }
        if (mode === "register" && new TextEncoder().encode(form.elements.password.value).length > 72) { error.textContent = "密码最多72个UTF-8字节（中文通常每字3字节）"; return; }
        busy = true; controller = new AbortController();
        root.querySelectorAll("button,input").forEach(node => { node.disabled = true; });
        submit.textContent = mode === "login" ? "正在登录…" : "正在创建账号…";
        try {
          const body = {username: form.elements.username.value.trim(), password: form.elements.password.value};
          if (mode === "register") Object.assign(body, {role, nickname: form.elements.nickname.value.trim()});
          const response = await fetch(`/api/v1/auth/portal-${mode}`, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body), signal:controller.signal});
          const data = await response.json();
          if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "请检查账号、密码和填写格式");

          if (!root.isConnected) return;
          saveSession(data);
          data.user.role = role;
          await options.onSuccess?.(data);
        } catch (err) { if (err.name !== "AbortError") error.textContent = err.message; }
        finally {
          busy = false;
          root.querySelectorAll("button,input").forEach(node => { node.disabled = false; });
          submit.textContent = mode === "login" ? "登录并继续" : "注册并进入";
        }
      });
      root.append(form, el("p", "auth-footnote", mode === "login" ? "还没有账号？点击上方「注册」即可创建。" : "已有账号？切回「登录」，继续你的日常。"));
    }
    paint(); return root;
  }
  function openDialog(options = {}) {
    const existing = document.querySelector(".auth-dialog"); if (existing) { existing.querySelector("input")?.focus(); return existing; }
    const dialog = el("dialog", "auth-dialog");
    dialog.setAttribute("aria-label", options.role === "customer" ? "买家登录或注册" : "登录或注册");
    const form = createForm({...options, onSuccess: async data => { dialog.close(); await options.onSuccess?.(data); }});
    if (!options.required) {
      const close = el("button", "auth-close", "×"); close.type = "button"; close.setAttribute("aria-label", "关闭登录窗口");
      close.addEventListener("click", () => dialog.close()); dialog.append(close);
      dialog.addEventListener("click", event => { if (event.target === dialog) { const r = dialog.getBoundingClientRect(); if (event.clientX < r.left || event.clientX > r.right || event.clientY < r.top || event.clientY > r.bottom) dialog.close(); } });
    } else dialog.addEventListener("cancel", event => event.preventDefault());
    dialog.append(form); dialog.addEventListener("close", () => { form.dispose(); dialog.remove(); }, {once:true});
    document.body.append(dialog); dialog.showModal(); form.querySelector("input")?.focus(); return dialog;
  }
  async function currentUser() {
    restoreSession();
    const order = sessionStorage.getItem("portal_role") === "merchant" ? ["token_b", "token_c"] : ["token_c", "token_b"];
    for (const key of order) {
      const token = sessionStorage.getItem(key); if (!token) continue;
      const response = await fetch("/api/v1/auth/me", {headers:{Authorization:`Bearer ${token}`}});
      if (sessionStorage.getItem(key) !== token) continue;
      if (response.ok) return response.json();
      if (response.status === 401 || response.status === 403) sessionStorage.removeItem(key);
    }
    return null;
  }
  function saveSession(data) {
    if (data.token_b) sessionStorage.setItem("token_b", data.token_b); else sessionStorage.removeItem("token_b");
    sessionStorage.setItem("token_c", data.token_c);
    sessionStorage.setItem("account_shared", "1");
    sessionStorage.setItem("portal_role", data.token_b ? "merchant" : "customer");
    try { localStorage.setItem(sharedKey, JSON.stringify(Object.fromEntries(['token_b','token_c','account_shared','portal_role'].map(key => [key,sessionStorage.getItem(key)])))); } catch {}
  }
  async function logout(tokenKey) {
    restoreSession();
    if (sessionStorage.getItem("account_shared") === "1") {
      const saved = ["token_b", "token_c"].map(key => [key, sessionStorage.getItem(key)]);
      for (const [, value] of saved) {
        if (!value) continue;
        const response = await fetch("/api/v1/auth/logout", {method:"POST", headers:{Authorization:`Bearer ${value}`}});
        if (!response.ok && response.status !== 401) throw new Error("退出失败，请稍后重试");
      }
      for (const [key, value] of saved) if (sessionStorage.getItem(key) === value) sessionStorage.removeItem(key);
      if (!sessionStorage.getItem("token_b") && !sessionStorage.getItem("token_c")) sessionStorage.removeItem("account_shared");
      try { localStorage.setItem(sharedKey, "null"); } catch {}
      return;
    }
    const token = sessionStorage.getItem(tokenKey);
    if (token) {
      const response = await fetch("/api/v1/auth/logout", {method:"POST", headers:{Authorization:`Bearer ${token}`}});
      if (!response.ok && response.status !== 401) throw new Error("退出失败，请稍后重试");
    }
    if (sessionStorage.getItem(tokenKey) === token) sessionStorage.removeItem(tokenKey);
  }
  async function ensureSession() {
    const user = await currentUser();
    if (!user) return null;
    const preferred = sessionStorage.getItem('portal_role') === 'merchant' ? ['token_b','token_c'] : ['token_c','token_b'];
    const token = sessionStorage.getItem(preferred[0]) || sessionStorage.getItem(preferred[1]);
    const response = await fetch('/api/v1/auth/portal-session', {method:'POST',headers:{Authorization:`Bearer ${token}`,'Content-Type':'application/json'},body:JSON.stringify({token_b:sessionStorage.getItem('token_b')||'',token_c:sessionStorage.getItem('token_c')||''})});
    if (!response.ok) throw Error('登录状态恢复失败，请刷新重试');
    const data = await response.json(); saveSession(data); return data;
  }
  return {createForm, openDialog, currentUser, logout, saveSession, ensureSession};
})();
