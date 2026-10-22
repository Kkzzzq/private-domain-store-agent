window.OPDialogs = (() => {
  const pending = new Set();
  function open(message, input) {
    const identity = sessionStorage.getItem('token_op');
    return new Promise(resolve => {
      const dialog = document.createElement('dialog');
      dialog.className = 'op-action-dialog';
      const form = document.createElement('form');
      const title = document.createElement('h2');
      title.textContent = input ? '填写操作原因' : '确认操作';
      const description = document.createElement('p');
      description.textContent = message;
      form.append(title, description);
      let field;
      if (input) {
        field = document.createElement('textarea');
        field.rows = 3;
        field.required = true;
        field.maxLength = 200;
        field.setAttribute('aria-label', '操作原因');
        form.append(field);
      }
      const actions = document.createElement('div');
      const cancel = document.createElement('button');
      cancel.type = 'button';
      cancel.textContent = '取消';
      const submit = document.createElement('button');
      submit.type = 'submit';
      submit.textContent = input ? '确认提交' : '确认执行';
      submit.className = 'primary';
      actions.append(cancel, submit);
      form.append(actions);
      dialog.append(form);
      let settled = false;
      function finish(value) {
        if (settled) return;
        settled = true;
        pending.delete(cancelAction);
        dialog.remove();
        resolve(sessionStorage.getItem('token_op') === identity ? value : input ? null : false);
      }
      const cancelAction = () => finish(input ? null : false);
      pending.add(cancelAction);
      cancel.onclick = cancelAction;
      dialog.oncancel = event => { event.preventDefault(); cancelAction(); };
      dialog.onclose = cancelAction;
      form.onsubmit = event => {
        event.preventDefault();
        if (field) {
          field.setCustomValidity(field.value.trim().length < 2 ? '请填写至少2个字的操作原因' : '');
          if (!field.reportValidity()) return;
        }
        finish(field ? field.value.trim() : true);
      };
      if (field) field.oninput = () => field.setCustomValidity('');
      document.body.append(dialog);
      dialog.showModal();
      (field || cancel).focus();
    });
  }
  function alert(message) {
    const notice = document.createElement('div');
    notice.className = 'op-action-notice';
    notice.setAttribute('role', 'alert');
    const text = document.createElement('span');
    text.textContent = String(message || '操作未完成，请重试');
    const close = document.createElement('button');
    close.type = 'button';
    close.textContent = '关闭';
    close.onclick = () => notice.remove();
    notice.append(text, close);
    const host = Array.from(document.querySelectorAll('dialog[open]')).at(-1) || document.body;
    host.append(notice);
    setTimeout(() => notice.remove(), 10000);
  }
  window.addEventListener('op-session-ended', () => { for (const cancel of [...pending]) cancel(); });
  window.addEventListener('hashchange', () => { for (const cancel of [...pending]) cancel(); });
  return {prompt: message => open(message, true), confirm: message => open(message, false), alert};
})();
