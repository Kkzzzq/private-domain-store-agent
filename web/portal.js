// Public, per-shop branding; all text is inserted as text, never HTML.
(async () => {
  const code = new URLSearchParams(location.search).get("code") || "nanzhi";
  try {
    const response = await fetch(`/api/v1/c/shops/${encodeURIComponent(code)}`);
    if (!response.ok) return;
    const shop = await response.json();
    const settings = shop.storefront || {};
    document.title = `${shop.name} · 欢迎来到小店`;
    const name = document.querySelector(".brand-name");
    name.firstChild.textContent = shop.name;
    name.querySelector("small").textContent = "PRIVATE STORE";
    document.querySelector(".brand").setAttribute("aria-label", `${shop.name}首页`);
    const oldMark = document.querySelector(".brand-mark");
    if (shop.logo_url) {
      const mark = document.createElement("img"); mark.className = "brand-mark"; mark.src = shop.logo_url; mark.alt = shop.name;
      oldMark.replaceWith(mark);
    } else oldMark.textContent = shop.name.slice(0, 1);
    for (const [selector, key] of [[".header-note", "brand_slogan"], ["#welcome-title", "portal_title"], [".intro-copy", "portal_description"]]) {
      if (typeof settings[key] === "string") document.querySelector(selector).textContent = settings[key];
    }
    const buyer = document.querySelector(".entry-card");
    buyer.href = `/c.html?code=${encodeURIComponent(code)}`;
    buyer.querySelector("h2").textContent = `逛逛${shop.name}`;
    buyer.querySelector(".entry-code").textContent = `小店 · ${code}`;
    document.querySelector(".portal-footer span").textContent = shop.name;
  } catch { /* Keep the existing entry links usable if the shop API is unavailable. */ }
})();

// Validate the session before revealing the entry page, including expired tokens.
(async () => {
  const reveal = () => document.body.classList.remove("auth-pending");
  try { if (await StoreAuth.currentUser()) { reveal(); return; } } catch { /* Allow a fresh sign-in after a network failure. */ }
  StoreAuth.openDialog({required: true, onSuccess: reveal});
})();
