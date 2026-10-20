const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const context = vm.createContext({});
vm.runInContext(fs.readFileSync('web/coupon-policy.js', 'utf8'), context);
const coupon = (id, amount, extra = {}) => ({user_coupon_id: id, active: true, status: 'available', eligible: true, amount_cents: amount, threshold_cents: 9900, ...extra});
assert.equal(context.bestOwnedCoupon([], 109), null);
assert.equal(context.bestOwnedCoupon([coupon(1, 1000), coupon(2, 2000)], 109).user_coupon_id, 2);
assert.equal(context.bestOwnedCoupon([coupon(1, 5000), coupon(2, 10000, {threshold_cents: 20000})], 10).user_coupon_id, 1);
for (const extra of [{active: false}, {eligible: false}, {status: 'used'}, {status: 'reserved'}, {user_coupon_id: null}]) {
  assert.equal(context.bestOwnedCoupon([coupon(1, 1000, extra)], 109), null);
}
assert.equal(context.visibleShopCoupons([coupon(1, 1000, {active: false})]).length, 0);
assert.equal(context.visibleShopCoupons([coupon(1, 1000, {status: 'used'})]).length, 0);
assert.equal(context.visibleShopCoupons([coupon(null, 1000, {can_claim: true, status: null})]).length, 1);
assert.equal(context.visibleShopCoupons([coupon(1, 1000, {eligible: false})]).length, 1);
assert.equal(context.bestOwnedCoupon([coupon(4, 1000), coupon(2, 1000)], 109).user_coupon_id, 2);
console.log('Coupon automatic selection, cap, tie-break, status and visibility checks passed');

class Element {
  constructor(tag, className = '', text = '') { this.tagName = tag; this.className = className; this.textContent = text; this.children = []; }
  append(...nodes) { this.children.push(...nodes); }
  setAttribute() {}
  addEventListener() {}
}
context.h = (tag, className, text) => new Element(tag, className, text);
context.code = 'nanzhi';
context.couponCondition = item => `满${item.threshold_cents / 100}减${item.amount_cents / 100}`;
const source = fs.readFileSync('web/c.js', 'utf8');
const begin = source.indexOf('function renderCouponEntry(');
const end = source.indexOf('\nfunction renderProductInfo(', begin);
assert.ok(begin >= 0 && end > begin);
vm.runInContext(source.slice(begin, end), context);
const entry = context.renderCouponEntry({getCoupons: () => [], selectedId: () => 1});
entry.refreshCoupons([]);
assert.equal(entry.hidden, true);
entry.refreshCoupons([coupon(1, 1000)]);
assert.equal(entry.hidden, false);
assert.ok(entry.children[1].textContent.includes('使用中'));
entry.refreshCoupons([coupon(1, 1000, {active: false})]);
assert.equal(entry.hidden, true);
console.log('Coupon entry DOM hide/show and selected ticket checks passed');
