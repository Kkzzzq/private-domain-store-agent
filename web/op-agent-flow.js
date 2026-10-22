window.OPAgentFlow = (() => {
  const definitions = {
    business: {
      name: '业务对话', boundary: '负责回答与业务查询，不在这里给自己评分',
      note: '当前是独立合成店铺。需要验证回答质量时，先转为评测候选，再审核并运行。',
      steps: [
        ['选择身份并提问', '买家问购物，商家问经营；从一句具体问题开始。', '.ae-dialogue select', '请选择身份，再输入问题。'],
        ['查看回答与实际调用', '先看助手回答，需要时展开工具轨迹和业务证据。', '.ae-dialogue', '发送问题后，回答与实际调用会在工作台显示。'],
        ['按需转入评测', '将问题保存为候选用例；创建候选不等于已经评测。', '.ae-main-evidence', '先完成一次对话，再在业务证据区转为评测候选。']
      ]
    },
    functional: {
      name: '功能验证', boundary: '验证 B/C/OP 功能与业务状态，不用模型文案代替断言',
      note: '分析需求不会立即执行。只有核对并批准计划后，才会运行批准范围内的测试。',
      steps: [
        ['描述测试需求', '说明在哪一端、做什么，以及预期怎样。', '.fi-input', '先填写需求与测试环境，再分析可测试范围。'],
        ['确认范围并生成计划', '查看可执行用例和缺口，再提交计划。', '.fi-result', '先点击“分析需求并匹配用例”；分析结果会显示在输入区下方。'],
        ['核对并批准执行', '检查用例、环境与预算；批准后启动。', 'heading:计划与审批', '在计划列表选择一份计划，核对详情后再批准执行。'],
        ['查看结果与失败原因', '区分通过、失败与阻塞，核对断言和清理。', 'heading:4. 查看测试结果', '执行后在报告中查看每条用例的预期、实际和证据。']
      ]
    },
    evaluator: {
      name: '质量评审', boundary: '评测业务 Agent 与功能测试 Agent，不把产品失败等同测试 Agent 失败',
      note: '程序核验不重跑原任务；模型评分会调用模型。程序、模型与人工三种结论分别保存。',
      steps: [
        ['选择对象与来源', '选择要评测的 Agent，以及一份已结束运行。', '.aq-source-form', '先选择评测对象和来源运行；没有来源时需先完成一次对应运行。'],
        ['核验事实与按需评分', '生成程序核验，打开结果后再补充模型评分。', '.aq-detail', '先生成程序核验或打开一份历史评测，再查看三类结论。'],
        ['人工复核并留存', '核对证据，填写复核结论与理由。', '.aq-manual', '请先打开一份评测；人工复核区位于评测详情末尾。']
      ]
    }
  };
  const introductions = {
    business: {
      prepare: '选择合成买家或商家。这里的商品是测试副本，不是实际店铺目录。',
      first: '输入一个具体问题后发送；等待完整回答，再按需展开执行轨迹。',
      result: '得到助手回答、商品建议和实际调用证据；本页不会自动判分。',
      recovery: '无法切换身份：开始新对话。无匹配商品：调整条件。模型失败：查看提示后重试，不会补造成功回答。',
      features: ['业务问答：查询商品规格、库存、价格、政策与本人订单。', '经营指导：商家可查询经营信息及后台配置方法，不等于已保存配置。', '历史对话：查看近7天记录；每段最多5轮，开始新对话会重置当前上下文。', '评测候选：填写预期后创建候选；还需在用例管理审核启用、运行，再到评测页核验。'],
      example: '预算100元，推荐适合送朋友的礼物',
      cost: '发送对话会调用真实模型。查看已有记录、轨迹不重新运行；转为候选不会自动执行。'
    },
    functional: {
      prepare: '准备“操作 + 预期结果”，确认测试环境；首次使用优先选择独立合成环境。',
      first: '填写需求并分析，核对匹配范围后创建计划；计划待审批时，确认环境、用例和预算再批准。',
      result: '运行后得到一份含多个用例的报告：实际步骤、预期与实际、失败原因、截图及清理状态。',
      recovery: '未覆盖：补登记工具或缩小需求。规划失败：查看错误后重新规划。版本已变化：创建新计划并重新批准。',
      features: ['需求分析：匹配已登记工具，不会编造未接入步骤。', '用例管理：可新增声明式用例，审核后使用。自建步骤支持商品列表/详情、查看购物车/加购、订单查询，不支持任意代码或URL。', '计划与审批：冻结执行范围，修改后需重新批准；批准不等于运行通过。', '报告、重跑与对比：区分执行失败与环境阻塞，同条件记录才可有效比较。', '能力目录：区分B、C和OP端；已登记场景不等于所有业务分支已覆盖。'],
      example: '验证C端购物车数量超过库存时拒绝修改，并且原购物车数量和金额不变',
      cost: '需求分析、模型规划与正式Agent工具编排会调用模型。固定接口/UI断言不靠模型自报成功。'
    },
    evaluator: {
      prepare: '需要一份已结束的业务Agent或功能测试Agent运行。没有来源时，先到对应页面产生运行记录。',
      first: '选择对象与来源，生成程序核验；打开历史评测，再按需补充模型评分并填写人工复核。',
      result: '程序检查、模型维度评分、人工意见分别留存；功能Agent来源同时记录隐藏集对照状态，未启用或缺场景不计通过。',
      recovery: '无来源：先完成对应运行。证据不足：补运行而非强行判通过。无隐藏答案：该评测未启用，不能计算为通过。',
      features: ['双对象评测：业务Agent看任务事实，功能测试Agent看测试行为与证据；发现产品缺陷不等于测试Agent差。', '程序核验：读取已有记录，不重跑原任务；阻塞或缺项不能当通过。', '模型评分与人工复核：需要实际证据，结论分别保存。', '版本对比与稳定性：至少两份符合条件的记录；不同来源、版本或环境会标明限制。', '缺陷基准：在隔离环境运行正常版/缺陷版，会消耗额度，不代表全站缺陷检出率。', '隐藏评测：答案文件需单独准备；揭示需要审批权限并留痕，不会因没有答案默认通过。'],
      cost: '程序核验、查看历史不调用模型。补充模型评分、缺陷基准会调用模型；人工复核需要审批权限。'
    }
  };
  function mount(root, id, options = {}) {
    const definition = definitions[id];
    if (!definition) return;
    root.classList.add('af-page', 'af-' + id);
    const section = document.createElement('section');
    section.className = 'af-flow';
    section.setAttribute('aria-label', definition.name + '操作流程');
    const header = document.createElement('div');
    header.className = 'af-flow-header';
    const title = document.createElement('strong');
    title.textContent = definition.name;
    const boundary = document.createElement('span');
    boundary.textContent = definition.boundary;
    header.append(title, boundary);
    const steps = document.createElement('ol');
    steps.className = 'af-steps qa-eval-guide';
    steps.style.setProperty('--af-step-count', String(definition.steps.length));
    const hint = document.createElement('p');
    hint.className = 'af-hint';
    hint.setAttribute('role', 'status');
    hint.textContent = definition.note;
    for (const [index, [name, description, selector, help]] of definition.steps.entries()) {
      const item = document.createElement('li');
      item.className = 'qa-eval-step';
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'af-step-button';
      button.setAttribute('aria-label', `定位至第 ${index + 1} 步：${name}`);
      const number = document.createElement('span');
      number.className = 'qa-eval-number';
      number.textContent = String(index + 1).padStart(2, '0');
      const heading = document.createElement('strong');
      heading.textContent = name;
      const copy = document.createElement('span');
      copy.className = 'af-step-copy';
      copy.textContent = description;
      button.append(number, heading, copy);
      button.onclick = () => {
        let target = selector.startsWith('heading:')
          ? Array.from(root.querySelectorAll('h2,h3')).find(node => node.textContent.includes(selector.slice(8)))?.parentElement
          : root.querySelector(selector);
        if (selector === '.fi-result' && !target?.children.length) target = root.querySelector('.fi-panel');
        for (let parent = target?.parentElement; parent && parent !== root; parent = parent.parentElement) {
          if (parent.tagName === 'DETAILS') parent.open = true;
        }
        hint.textContent = help;
        if (id === 'business' && index === 0 && target?.disabled) {
          target = root.querySelector('.ae-dialogue textarea');
          hint.textContent = target?.disabled ? '当前对话正在执行，请等待完成后再继续。' : '当前对话身份已固定；可继续提问，或点击“开始新对话”后重新选择身份。';
        }
        if (!target) return;
        target.scrollIntoView({behavior: 'smooth', block: 'start'});
        if (target.matches('input,textarea,select') && !target.disabled) target.focus({preventScroll: true});
      };
      item.append(button);
      steps.append(item);
    }
    section.append(header, steps, hint);
    const content = introductions[id];
    const welcome = document.createElement('section');
    welcome.className = 'af-welcome';
    const welcomeTitle = document.createElement('h3');
    welcomeTitle.textContent = '第一次使用，从这里开始';
    welcome.append(welcomeTitle);
    const required = id === 'business' ? 'qa.assistant.run' : id === 'functional' ? 'qa.functional.run' : 'qa.view';
    if (Array.isArray(options.capabilities) && !options.capabilities.includes(required)) {
      const permission = document.createElement('p');
      permission.className = 'af-permission';
      permission.textContent = '当前账号没有此操作权限，可以阅读流程说明；执行功能请联系平台管理员授权。';
      welcome.append(permission);
    }
    for (const [label, value] of [['开始前', content.prepare], ['第一次怎么做', content.first], ['最终会得到', content.result], ['执行与费用', content.cost]]) {
      const line = document.createElement('p');
      const caption = document.createElement('strong');
      caption.textContent = label;
      const text = document.createElement('span');
      text.textContent = value;
      line.append(caption, text);
      welcome.append(line);
    }
    const action = document.createElement('button');
    action.type = 'button';
    action.className = 'af-start';
    action.textContent = content.example ? '填入一个示例，先不运行' : '没有来源？先去功能测试';
    action.onclick = () => {
      if (!content.example) { options.navigate?.('testing-functional'); return; }
      const input = root.querySelector(id === 'business' ? '.ae-dialogue textarea' : '.fi-input');
      if (!input || input.disabled) { hint.textContent = '当前操作尚未准备好，请等待加载或执行结束。'; return; }
      input.value = id === 'business' && root.querySelector('.ae-dialogue select')?.value === 'merchant'
        ? '本店有哪些低库存商品？请帮我整理需要关注的规格' : content.example;
      input.dispatchEvent(new Event('input', {bubbles: true}));
      input.scrollIntoView({behavior: 'smooth', block: 'center'});
      input.focus({preventScroll: true});
      hint.textContent = '示例已填入，可先修改内容。尚未发送、分析或执行，也未产生模型调用。';
    };
    welcome.append(action);
    if (options.navigate) {
      for (const [label, route] of [['管理测试用例', 'testing-cases'], ['查看全部报告', 'testing-runs']]) {
        const link = document.createElement('button');
        link.type = 'button';
        link.className = 'af-start af-link';
        link.textContent = label;
        link.onclick = () => options.navigate(route);
        welcome.append(link);
      }
    }
    const details = document.createElement('details');
    details.className = 'af-manual';
    const summary = document.createElement('summary');
    summary.textContent = '全部功能说明、费用与失败处理';
    details.append(summary);
    for (const text of [...content.features, content.cost, content.recovery]) {
      const paragraph = document.createElement('p');
      paragraph.textContent = text;
      details.append(paragraph);
    }
    const glossary = document.createElement('p');
    glossary.textContent = '状态怎么看：通过＝断言满足；失败＝发现不符；阻塞＝未完成、不能判通过；清理成功＝释放测试资源，不等于测试通过。没有权限或缺少前置记录时，按钮会禁用，不绕过保护。';
    details.append(glossary);
    section.append(welcome, details);
    root.append(section);
  }
  return {mount};
})();
