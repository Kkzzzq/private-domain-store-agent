/* 功能测试 Agent 的自由需求受理：先判断需求能否由真实功能工具实现，再产出需审批的执行计划。 */
window.OPFunctionalIntake = (() => {
  const el = (tag, cls, text) => { const node = document.createElement(tag); node.className = cls || ''; if (text != null) node.textContent = String(text); return node; };
  const button = (text, fn, primary = false) => { const node = el('button', primary ? 'qa-primary' : '', text); node.type = 'button'; node.onclick = fn; return node; };
  const pre = value => el('pre', 'qa-json', typeof value === 'string' ? value : JSON.stringify(value, null, 2));
  const chip = (text, state) => el('span', `qa-badge ${state ? 'qa-' + state : ''}`, text);
  const rows = value => Array.isArray(value) ? value : [];
  function mount(root, options) {
    const { api, refresh, data } = options;
    if (!data?.capabilities?.capabilities?.includes('qa.functional.run')) return;
    const panel = el('section', 'qa-card fi-panel');
    panel.append(el('h3', '', '自由需求受理（功能测试 Agent）'),
      el('p', 'qa-muted', '直接写下你想验证的需求。Agent 先读真实 B/C 功能目录与当前环境的已登记工具，判断这条需求能否被实现和测试：能对应到真实功能域且有执行工具的才判为可实现，并给出用例；只有接口清单、功能未覆盖或没有工具时明确判为不可测，不会凭一句话就编造测试。'));
    const form = el('div', 'fi-form');
    const input = el('textarea', 'fi-input'); input.rows = 3; input.maxLength = 600;
    input.setAttribute('aria-label', '功能测试需求');
    input.placeholder = '例如：验证 C 端购物车修改数量时，数量超过库存会被拒绝，并且购物车金额和库存保持不变';
    const environment = el('select'); environment.setAttribute('aria-label', '测试环境');
    for (const row of rows(data.capabilities.environments)) { const option = el('option', '', `${row.name || row.id}`); option.value = row.id; environment.append(option); }
    const message = el('p', 'qa-error');
    const result = el('div', 'fi-result');
    const history = el('div', 'fi-history');
    let historyRows = [];
    const submit = button('判断这条需求能否测试', async () => {
      message.textContent = ''; result.replaceChildren(el('p', 'qa-muted', '正在读取真实功能目录，由独立测试模型判断…'));
      submit.disabled = true;
      try {
        const record = await api('/functional-intake', { requirement: input.value.trim(), environment_id: environment.value });
        render(record);
      } catch (err) { message.textContent = err.message; result.replaceChildren(); }
      finally { submit.disabled = false; }
    }, true);
    submit.disabled = !input.value.trim();
    input.oninput = () => { submit.disabled = input.value.trim().length < 4; };
    form.append(input, environment, submit, message);
    panel.append(form, result, history);
    root.append(panel);

    function planButton(record) {
      const payload = record.plan;
      const create = button('生成功能测试计划（需审批）', async () => {
        create.disabled = true;
        try {
          await api('/plans', payload);
          await refresh();
          message.textContent = '';
          result.append(el('p', 'qa-notice', '已提交计划，请在下方「测试计划与审批」中核对用例与预算后批准；批准后由功能测试 Agent 读取功能目录并调用对应工具执行。'));
        } catch (err) { message.textContent = err.message; create.disabled = false; }
      }, true);
      return create;
    }
    function render(record) {
      const verdict = record.verdict || {};
      const item = el('section', 'fi-verdict');
      item.append(chip(verdict.feasible ? '可实现且可测试' : '当前不可测', verdict.feasible ? 'passed' : 'blocked'),
        el('p', 'fi-reason', verdict.reason || '未给出判断理由'));
      if (verdict.feature_ids?.length) item.append(el('p', 'qa-muted', `匹配功能域：${verdict.feature_ids.join('、')}`));
      if (verdict.case_ids?.length) item.append(el('p', 'qa-muted', `可执行已登记用例：${verdict.case_ids.join('、')}${window.OPReportName ? '（' + verdict.case_ids.map(id => OPReportName.titleOf({ results: [] }, id, data.cases) || id).join('、') + '）' : ''}`));
      if (verdict.missing?.length) item.append(el('p', 'qa-error', `缺少依据：${verdict.missing.join('；')}`));
      item.append(el('p', 'qa-muted', `环境 ${record.environment_id} · 功能目录 ${String(record.catalog_version || '').slice(0, 12)} · 受理记录 ${String(record.id).slice(0, 8)} · ${record.status === 'completed' ? '判断已形成' : '判断未完成'}`));
      if (record.plan) {
        item.append(el('p', '', `计划目标：${record.plan.goal}`),
          el('p', 'qa-muted', `用例 ${record.plan.case_ids.length} 条 · 上限 ${record.plan.max_calls} 次模型调用 / ${record.plan.max_tokens} tokens · 规划 ${record.plan.planner === 'model' ? '真实模型' : '固定'} · 执行 ${record.plan.functional_driver ? '读取功能目录后调用已登记工具' : '实店固定执行器'}`),
          planButton(record));
      } else item.append(el('p', 'qa-muted', '没有可提交的执行计划：需要先补齐功能目录中的工具或被测功能。'));
      const evidence = el('details', 'fi-details');
      evidence.append(el('summary', '', '受理依据、工具调用与模型用量'), pre({ catalog_version: record.catalog_version, verdict, tools: record.evidence?.tools, budget: record.evidence?.budget, conversation: record.evidence?.conversation, error: record.evidence?.error }));
      item.append(evidence);
      result.replaceChildren(item);
    }
    function paintHistory() {
      history.replaceChildren();
      if (!historyRows.length) return;
      history.append(el('h4', '', '最近受理记录（本账号）'));
      for (const record of historyRows) {
        const line = el('div', 'fi-line');
        line.append(chip(record.verdict?.feasible ? '可实现' : '不可测', record.verdict?.feasible ? 'passed' : 'blocked'),
          el('span', 'fi-requirement', record.requirement),
          button('查看', () => { input.value = record.requirement; environment.value = record.environment_id; render(record); }));
        history.append(line);
      }
    }
    api('/functional-intake').then(list => { if (!panel.isConnected) return; historyRows = rows(list); environment.value = data.capabilities.environments.find(row => row.id === environment.value)?.id || environment.value; paintHistory(); }).catch(() => {});
  }
  return { mount };
})();