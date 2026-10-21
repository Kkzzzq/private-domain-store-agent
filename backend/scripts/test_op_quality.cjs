const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');

class Element {
  constructor(tag) { this.tag = tag; this.children = []; this.textContent = ''; }
  append(...children) { this.children.push(...children); }
}
const source = fs.readFileSync('web/op-quality.js', 'utf8');
const document = {createElement: tag => new Element(tag), createTextNode: text => ({tag:'#text',textContent:text})};
const context = vm.createContext({document,window:{}});
vm.runInContext(fs.readFileSync('web/assistant-presentation.js','utf8'),context);
vm.runInContext(source.slice(source.indexOf('  const el ='), source.indexOf('  function mount(')), context);
const output = vm.runInContext('answer("**库存20件**\\n`SKU 1` <img src=x onerror=alert(1)>")', context);
assert.equal(output.children.find(node => node.tag === 'strong').textContent, '库存20件');
assert.equal(output.children.find(node => node.tag === 'code').textContent, 'SKU 1');
assert.equal(output.children.some(node => node.tag === 'img' || node.tag === 'script'), false);
assert.ok(output.children.some(node => node.textContent.includes('<img src=x')));
const descriptions=vm.runInContext('toolList(["check_inventory","prepare_product_draft","read_test_capabilities","propose_test_plan","<img onerror=alert(1)>"])',context);
assert.equal(descriptions.children[0].children[0].textContent,'check_inventory');
assert.ok(descriptions.children[0].children[1].textContent.includes('库存'));
assert.ok(descriptions.children[1].children[1].textContent.includes('不直接创建'));
assert.ok(descriptions.children[2].children[1].textContent.includes('测试环境'));
assert.ok(descriptions.children[3].children[1].textContent.includes('批准'));
assert.equal(descriptions.children[4].children[0].tag,'dt');
assert.ok(descriptions.children[4].children[1].textContent.includes('暂无'));
for (const file of ['b.html', 'c.html', 'index.html']) {
  assert.equal(fs.readFileSync('web/' + file, 'utf8').includes('op-quality'), false);
}
assert.ok(fs.readFileSync('web/op.html','utf8').includes('op-quality.js'));
const navigation = fs.readFileSync('web/op.js', 'utf8');
assert.ok(navigation.includes("id==='testing-overview'?'<div class=\"nav-label audit-label\">Agent 与测试中心</div>'"));
assert.ok(navigation.includes("'testing/overview':'testing-overview'"));
assert.ok(navigation.includes("id==='after-sales'?'<div class=\"nav-label audit-label\">管理与审计</div>'"));
assert.equal(navigation.includes("i===6?"), false);
console.log('OP-only entry and safe bold/inline-code answer rendering passed.');
