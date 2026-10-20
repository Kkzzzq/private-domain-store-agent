/* Shared login / registration UI. No sample credentials or password storage. */
window.StoreAuth = (() => {
  const el = (tag, cls, text) => {
    const node = document.createElement(tag); if (cls) node.className = cls;
    if (text != null) node.textContent = text; return node;
  };
  function createForm(options = {}) {
    const root = el("section", "auth-card");
    let mode = "login", role = options.role || "customer", username = "", busy = false, controller;
    root.dispose = () => controller?.abort();
    function paint() {
      root.replaceChildren();
      const eyebrow = el("p", "auth-eyebrow", "A LITTLE STORE, A LOVELY EVERYDAY");
      const title = el("h1", "auth-title", mode === "login" ? "欢迎回来" : "开启你的小店日常");
      root.append(eyebrow, title, el("p", "auth-description", mode === "register" ? "创建你的账号，开启一段新的小店日常。" : role === "merchant" ? "登录商家账号，轻松打理每一份热爱。" : "登录买家账号，继续发现喜欢的好物。"));
      const tabs = el("div", "auth-tabs");
      for (const [value, label] of [["login", "登录"], ["register", "注册"]]) {
        const tab = el("button", mode === value ? "active" : "", label); tab.type = "button";
        tab.setAttribute("aria-pressed", String(mode === value));
        tab.addEventListener("click", () => { if (!busy) { username = root.querySelector('[name="username"]').value; mode = value; paint(); } });
        tabs.append(tab);
      }
      root.append(tabs);
      const form = el("form", "auth-form");
      if (!options.role) {
        const choice = el("fieldset", "auth-roles"); choice.append(el("legend", "", "账号类型"));
        for (const [value, label] of [["customer", "买家账号"], ["merchant", "商家账号"]]) {
          const wrap = el("label"); const radio = el("input"); radio.type = "radio"; radio.name = "role"; radio.value = value; radio.checked = role === value;
          radio.addEventListener("change", () => { username = form.elements.username.value; role = value; paint(); });
          wrap.append(radio, document.createTextNode(label)); choice.append(wrap);
        }
        form.append(choice);
      }
      const field = (label, name, type, placeholder, required = true) => {
        const wrap = el("label", "auth-field"); wrap.append(el("span", "", label));
        const input = el("input"); input.type = type; input.name = name; input.required = required; input.placeholder = placeholder;
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
        busy = true; controller = new AbortController();
        root.querySelectorAll("button,input").forEach(node => { node.disabled = true; });
        submit.textContent = mode === "login" ? "正在登录…" : "正在创建账号…";
        try {
          const body = {username: form.elements.username.value.trim(), password: form.elements.password.value};
          if (mode === "register") Object.assign(body, {role, nickname: form.elements.nickname.value.trim()});
          const response = await fetch(`/api/v1/auth/${mode}`, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body), signal:controller.signal});
          const data = await response.json();
          if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "请检查账号、密码和填写格式");
          if (data.user.role !== role) throw new Error(`请使用${role === "merchant" ? "商家" : "买家"}账号登录`);
          if (!root.isConnected) return;
          sessionStorage.setItem(role === "merchant" ? "token_b" : "token_c", data.access_token);
          sessionStorage.setItem("portal_role", role);
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
    const order = sessionStorage.getItem("portal_role") === "merchant" ? ["token_b", "token_c"] : ["token_c", "token_b"];
    for (const key of order) {
      const token = sessionStorage.getItem(key); if (!token) continue;
      const response = await fetch("/api/v1/auth/me", {headers:{Authorization:`Bearer ${token}`}});
      if (response.ok) return response.json();
      if (response.status === 401) sessionStorage.removeItem(key);
    }
    return null;
  }
  return {createForm, openDialog, currentUser};
})();
