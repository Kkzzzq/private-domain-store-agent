const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');

function setup() {
  const tokens = new Map([['token_b', 'merchant-token'], ['token_c', 'buyer-token']]);
  const events = [];
  const context = vm.createContext({
    window: {dispatchEvent(event) { events.push(event); }},
    CustomEvent: class { constructor(type, options) { this.type = type; this.detail = options.detail; } },
    sessionStorage: {getItem(key) { return tokens.get(key) ?? null; }, setItem(key, value) { tokens.set(key, value); }, removeItem(key) { tokens.delete(key); }},
    fetch: async () => ({ok: true, status: 200, json: async () => ({})}),
  });
  vm.runInContext(fs.readFileSync('web/auth-ui.js', 'utf8'), context);
  const app = fs.readFileSync('web/app.js', 'utf8');
  vm.runInContext(app.slice(app.indexOf('function detailOf('), app.indexOf('function storefrontSettings(')), context);
  return {context, tokens, events};
}

(async () => {
  const {context, tokens, events} = setup();
  let request;
  context.fetch = async (path, options) => { request = {path, options}; return {ok: true, status: 200}; };
  await context.window.StoreAuth.logout('token_b');
  assert.equal(request.path, '/api/v1/auth/logout');
  assert.equal(request.options.headers.Authorization, 'Bearer merchant-token');
  assert.equal(tokens.has('token_b'), false);
  assert.equal(tokens.get('token_c'), 'buyer-token');
  tokens.set('token_b', 'next-token');
  context.fetch = async () => ({ok: false, status: 503});
  await assert.rejects(context.window.StoreAuth.logout('token_b'), /退出失败/);
  assert.equal(tokens.get('token_b'), 'next-token');
  context.fetch = async () => ({ok: false, status: 401, json: async () => ({detail: '登录已失效'})});
  await assert.rejects(vm.runInContext('createApi("token_b")("/protected")', context), /登录已失效/);
  assert.equal(tokens.has('token_b'), false);
  assert.equal(events[0].detail.tokenKey, 'token_b');
  assert.equal(tokens.get('token_c'), 'buyer-token');
  vm.runInContext('expireAuth({status:401}, "token_c", "old-token")', context);
  assert.equal(tokens.get('token_c'), 'buyer-token');
  vm.runInContext('expireAuth({status:403}, "token_c", "buyer-token")', context);
  assert.equal(tokens.get('token_c'), 'buyer-token');
  context.window.StoreAuth.saveSession({token_b:'shared-b',token_c:'shared-c'});
  assert.equal(tokens.get('account_shared'),'1');
  const revoked=[];
  context.fetch=async (path,options)=>{revoked.push(options.headers.Authorization);return {ok:true,status:200};};
  await context.window.StoreAuth.logout('token_c');
  assert.deepEqual(revoked,['Bearer shared-b','Bearer shared-c']);
  assert.equal(tokens.has('token_b'),false);
  assert.equal(tokens.has('token_c'),false);
  assert.equal(tokens.has('account_shared'),false);
  console.log('Auth logout, failed logout, role isolation, expired session and stale-response checks passed');
})().catch(error => { console.error(error); process.exitCode = 1; });
