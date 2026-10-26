const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

// Exercise the real click handler without depending on the removed parameter editor.
class Element {
  constructor(tag, className = '', text = '') {
    this.tagName = tag; this.className = className; this.textContent = text;
    this.children = []; this.events = {}; this.attributes = {}; this.style = {}; this.dataset = {};
    this.classList = {add() {}, remove() {}};
  }
  append(...children) { this.children.push(...children.filter(c => typeof c === 'object')); }
  replaceChildren(...children) { this.children = children; }
  addEventListener(type, handler) { this.events[type] = handler; }
  setAttribute(name, value) { this.attributes[name] = value; }
  all() { return [this, ...this.children.flatMap(c => c.all())]; }
  querySelector(selector) { return this.all().find(n => n.tagName === selector); }
  querySelectorAll(selector) { return this.all().filter(n => selector.split(', ').includes(n.tagName)); }
}
const requests = [], notices = [];
const sandbox = {
  document: {createElement: tag => new Element(tag), createTextNode: () => new Element('text')},
  h: (tag, cls, text) => new Element(tag, cls, text),
  STATUS: {on: '在售'}, render() {}, makeSortable() {}, statusActions: () => [],
  skuImageField: () => { const node = new Element('div'); const input = new Element('input'); input.value = ''; node.append(input); return node; },
  api: async (path, options) => { requests.push({path, body: JSON.parse(options.body)}); },
  toast: message => notices.push(message),
};
const source = fs.readFileSync('web/b.js', 'utf8');
vm.createContext(sandbox);
vm.runInContext(source.slice(source.indexOf('function renderSkuPanel('), source.indexOf('function skuImageField(')), sandbox);
(async () => {
  let reloads = 0;
  const panel = sandbox.renderSkuPanel({id: 7, status: 'on', skus: [
    {id: 9, spec: '米白', price_yuan: 29, stock: 10, status: 'on', parameters: [{name: '材质', value: '棉麻'}]},
  ]}, async () => { reloads++; });
  const controls = panel.all();
  controls.find(n => n.attributes['aria-label'] === '米白 售价').value = '31.25';
  controls.find(n => n.attributes['aria-label'] === '米白 库存').value = '7';
  await controls.find(n => n.tagName === 'button' && n.textContent === '保存').events.click();
  assert.equal(requests.length, 1, notices.join('; '));
  assert.equal(requests[0].path, '/api/v1/b/skus/9');
  assert.equal(requests[0].body.price_yuan, 31.25);
  assert.equal(requests[0].body.stock, 7);
  assert.equal(Object.hasOwn(requests[0].body, 'parameters'), false, 'Hidden existing parameters must not be cleared');
  assert.equal(reloads, 1);
  console.log('SKU save click submits price/stock, preserves hidden parameters and reloads successfully');
})().catch(error => { console.error(error); process.exitCode = 1; });
