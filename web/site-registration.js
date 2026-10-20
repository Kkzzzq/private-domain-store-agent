// Platform registration remains visible independently of shop decoration.
(() => {
  if (document.getElementById("site-registration")) return;
  const footer = document.createElement("footer");
  footer.id = "site-registration";
  footer.style.cssText = "padding:20px 16px;text-align:center;font:12px/1.8 system-ui,sans-serif;color:#666;background:#faf7f2";
  const link = document.createElement("a");
  link.href = "https://beian.miit.gov.cn/";
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.textContent = "陕ICP备2026029472号-1";
  link.style.cssText = "color:inherit;text-decoration:none";
  footer.append(link);
  document.body.append(footer);
})();
