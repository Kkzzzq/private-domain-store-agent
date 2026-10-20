function makeSortable(container, selector, onSave) {
  let dragged = null;
  let saving = false;
  let startOrder = [];
  const animations = new WeakMap();
  const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  const rows = () => [...container.querySelectorAll(selector)];
  const announcement = document.createElement("span");
  announcement.className = "sort-announcement";
  announcement.setAttribute("aria-live", "polite");
  container.insertAdjacentElement("afterend", announcement);
  const restore = () => {
    const current = rows();
    for (const id of startOrder) container.append(current.find(row => Number(row.dataset.sortId) === id));
  };
  const moveAt = (source, target, below) => {
    if (!target || source === target || target.parentElement !== source.parentElement) return;
    if ((below && target.nextElementSibling === source) || (!below && source.nextElementSibling === target)) return;
    const positions = new Map(rows().map(row => [row, row.getBoundingClientRect().top]));
    rows().forEach(row => animations.get(row)?.cancel());
    target.parentElement.insertBefore(source, below ? target.nextSibling : target);
    if (!reducedMotion) rows().forEach(row => {
      const offset = positions.get(row) - row.getBoundingClientRect().top;
      if (offset && row.animate) animations.set(row, row.animate([
        {transform: `translateY(${offset}px)`}, {transform: "translateY(0)"},
      ], {duration: 150, easing: "cubic-bezier(.2,.7,.2,1)"}));
    });
  };
  const finish = async () => {
    const ids = rows().map(row => Number(row.dataset.sortId));
    const changed = ids.some((id, index) => id !== startOrder[index]);
    if (dragged) dragged.classList.remove("is-dragging");
    dragged = null;
    if (!changed || saving) return;
    saving = true;
    container.setAttribute("aria-busy", "true");
    try {
      await onSave(ids);
      announcement.textContent = "排序已更新";
    } catch (error) {
      restore();
      announcement.textContent = error.message;
    } finally {
      saving = false;
      container.removeAttribute("aria-busy");
    }
  };
  for (const row of rows()) {
    const handle = document.createElement("button");
    handle.type = "button";
    handle.className = "drag-handle";
    const icon = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    icon.setAttribute("viewBox", "0 0 16 20");
    icon.setAttribute("aria-hidden", "true");
    for (const y of [4, 10, 16]) for (const x of [5, 11]) {
      const dot = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      dot.setAttribute("cx", x);
      dot.setAttribute("cy", y);
      dot.setAttribute("r", "1.25");
      icon.append(dot);
    }
    handle.append(icon);
    handle.title = "拖拽排序，也可使用方向键调整";
    handle.setAttribute("aria-label", `拖动${row.dataset.sortName || ""}排序`);
    if (row.tagName === "TR") row.querySelector("td").prepend(handle);
    else row.prepend(handle);
    handle.addEventListener("keydown", async event => {
      if (saving || !["ArrowUp", "ArrowDown"].includes(event.key)) return;
      event.preventDefault();
      const current = rows();
      const index = current.indexOf(row);
      const target = current[index + (event.key === "ArrowDown" ? 1 : -1)];
      if (!target) return;
      startOrder = current.map(item => Number(item.dataset.sortId));
      moveAt(row, target, event.key === "ArrowDown");
      await finish();
      handle.focus({preventScroll: true});
    });
    handle.addEventListener("pointerdown", event => {
      if (saving || dragged || (event.pointerType === "mouse" && event.button !== 0)) return;
      event.preventDefault();
      dragged = row;
      startOrder = rows().map(item => Number(item.dataset.sortId));
      handle.focus({preventScroll: true});
      const startX = event.clientX;
      const startY = event.clientY;
      let moved = false;
      const controller = new AbortController();
      window.addEventListener("pointermove", move => {
        if (dragged !== row) return;
        move.preventDefault();
        if (!moved && Math.hypot(move.clientX - startX, move.clientY - startY) < 4) return;
        moved = true;
        row.classList.add("is-dragging");
        const target = document.elementFromPoint(move.clientX, move.clientY)?.closest(selector);
        if (target && container.contains(target)) moveAt(row, target, move.clientY > target.getBoundingClientRect().top + target.getBoundingClientRect().height / 2);
        if (move.clientY < 80) window.scrollBy(0, -18);
        if (move.clientY > window.innerHeight - 80) window.scrollBy(0, 18);
      }, {signal: controller.signal, passive: false});
      window.addEventListener("pointerup", () => {
        controller.abort();
        if (container.isConnected && dragged === row) finish();
      }, {signal: controller.signal});
      window.addEventListener("keydown", key => {
        if (key.key !== "Escape") return;
        controller.abort();
        row.classList.remove("is-dragging");
        dragged = null;
        restore();
        handle.focus({preventScroll: true});
      }, {signal: controller.signal});
      window.addEventListener("pointercancel", () => {
        controller.abort();
        row.classList.remove("is-dragging");
        dragged = null;
        restore();
      }, {signal: controller.signal});
    });
  }
}
