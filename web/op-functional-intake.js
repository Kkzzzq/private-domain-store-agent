/* 功能测试 Agent 的自由需求受理：先判断需求能否由真实功能工具实现，再产出需审批的执行计划。 */
window.OPFunctionalIntake = (() => {
  const el = (tag, cls, text) => { const node = document.createElement(tag); node.className = cls || ''; if (text != null) node.textContent = cls === 'fi-reason' ? window.AssistantPresentation.clean(text) : String(text); return node; };
  const button = (text, fn, primary = false) => { const node = el('button', primary ? 'qa-primary' : '', text); node.type = 'button'; node.onclick = fn; return node; };
  const pre = value => el('pre', 'qa-json', typeof value === 'string' ? value : JSON.stringify(value, null, 2));
  const chip = (text, state) => el('span', `qa-badge ${state ? 'qa-' + state : ''}`, text);
  const rows = value => Array.isArray(value) ? value : [];
  function mount(root, options) {
    const { api, refresh, data, reviewPlan } = options;
    if (!data?.capabilities?.capabilities?.includes('qa.functional.run')) return;
    const panel = el('section', 'qa-card fi-panel');
    panel.append(el('h3', '', '1. 描述你要验证的功能'),
      el('p', 'qa-muted', '写清「在哪一端、做什么、期望怎样」。Agent 会匹配可执行用例；确认可测试后，再由你创建计划。'));
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
    const submit = button('分析需求并匹配用例', async () => {
      message.textContent = ''; result.replaceChildren(el('p', 'qa-muted', '正在读取真实功能目录，由 DeepSeek-Flash 判断…'));
      submit.disabled = true;
      try {
        const record = await api('/functional-intake', { requirement: input.value.trim(), environment_id: environment.value });
        render(record);
      } catch (err) { message.textContent = err.message; result.replaceChildren(); }
      finally { submit.disabled = false; }
    }, true);
    submit.disabled = !input.value.trim();
    input.oninput = () => { submit.disabled = input.value.trim().length < 4; };
    const examples=el('div','fi-examples');examples.append(el('span','qa-muted','试试这些需求：'));
    for(const text of ['购物车数量超过库存时应拒绝修改','B 端修改商品价格后，C 端应显示新价格','OP 修改商品后，B/C 端数据与数据库应一致'])examples.append(button(text,()=>{input.value=text;input.oninput();input.focus();}));
    const toolbar=el('div','fi-toolbar'),envLabel=el('label','fi-environment');envLabel.append(el('span','','测试环境'),environment);toolbar.append(envLabel,submit);
    form.append(input,examples,toolbar,message);
    panel.append(form, result, history);
    root.append(panel);

    function planButton(record) {
      const payload = record.plan;
      const create = button('创建计划，下一步核对并批准', async () => {
        create.disabled = true;
        try {
          const plan=await api('/plans', payload);
          if(reviewPlan)await reviewPlan(plan.id);else await refresh();
          message.textContent = '';
          result.append(el('p', 'qa-notice', '已提交计划，请在下方「计划与审批」中核对用例与预算后批准；批准后由功能测试 Agent 读取功能目录并调用对应工具执行。'));
        } catch (err) { message.textContent = err.message; create.disabled = false; }
      }, true);
      return create;
    }
    function render(record) {
      const verdict = record.verdict || {};
      const item = el('section', 'fi-verdict');
      const failed=record.status!=='completed';
      item.append(chip(failed?'判断未完成':verdict.feasible?'已匹配可执行用例':'暂时无法执行',failed?'blocked':verdict.feasible?'passed':'blocked'),
        el('p','fi-reason',failed?(record.error||record.evidence?.error||'受理服务未完成，请重试；本次不代表功能不可测。'):(verdict.reason||'未给出判断理由')));
      if (verdict.feature_ids?.length) item.append(el('p', 'qa-muted', `匹配功能域：${verdict.feature_ids.join('、')}`));
      if (verdict.case_ids?.length) item.append(el('p', 'qa-muted', `匹配用例：${verdict.case_ids.join('、')}${window.OPReportName ? '（' + verdict.case_ids.map(id => OPReportName.titleOf({ results: [] }, id, data.cases) || id).join('、') + '）' : ''}`));
      if (verdict.missing?.length) item.append(el('p', 'qa-error', `缺少依据：${verdict.missing.join('；')}`));
      item.append(el('p', 'qa-muted', `环境 ${record.environment_id} · 功能目录 ${String(record.catalog_version || '').slice(0, 12)} · 受理记录 ${String(record.id).slice(0, 8)} · ${record.status === 'completed' ? '判断已形成' : '判断未完成'}`));
      if (record.plan) {
        item.append(el('p', '', `计划目标：${record.plan.goal}`),
          el('p', 'qa-muted', `用例 ${record.plan.case_ids.length} 条 · 上限 ${record.plan.max_calls} 次模型调用 / ${record.plan.max_tokens} tokens · 规划 ${record.plan.planner === 'model' ? '真实模型' : '固定'} · 执行 ${record.plan.functional_driver ? '读取功能目录后调用已登记工具' : '实店固定执行器'}`),
          planButton(record));
      } else item.append(el('p', 'qa-muted', failed?'本次没有生成计划。请重试需求判断；若仍失败，请查看下方错误详情。':'没有可提交的执行计划：需要先补齐功能目录中的工具或被测功能。'));
      const evidence = el('details', 'fi-details');
      evidence.append(el('summary', '', '受理依据、工具调用与模型用量'), pre({ catalog_version: record.catalog_version, verdict, tools: record.evidence?.tools, budget: record.evidence?.budget, conversation: record.evidence?.conversation, error: record.evidence?.error }));
      item.append(evidence);
      result.replaceChildren(item);
    }
    function paintHistory() {
      history.replaceChildren();
      if (!historyRows.length) return;
      const previous=el('details','fi-previous');previous.append(el('summary','',`我的需求记录（${historyRows.length} 条）`));history.append(previous);
      for (const record of historyRows) {
        const line = el('div', 'fi-line');
        line.append(chip(record.verdict?.feasible ? '可实现' : '不可测', record.verdict?.feasible ? 'passed' : 'blocked'),
          el('span', 'fi-requirement', record.requirement),
          button('查看', () => { input.value = record.requirement; environment.value = record.environment_id; input.oninput(); render(record); }));
        previous.append(line);
      }
    }
    api('/functional-intake').then(list => { if (!panel.isConnected) return; historyRows = rows(list); environment.value = data.capabilities.environments.find(row => row.id === environment.value)?.id || environment.value; paintHistory(); }).catch(() => {});
  }
  return { mount };
})();
