// Run with Node from the repository root. No browser account or model calls.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync('web/c.js', 'utf8');
const functions = source.slice(source.indexOf('function currentChatIdentity()'), source.indexOf('function renderChat()'));
function setup(api) {
  const context = vm.createContext({code: 'nanzhi', token: 'account-a', sessionStorage: {getItem() {return context.token;}},
    chatRestoring: false, chatRestored: false, chatRestoreError: '', sessionId: '', chatLines: [],
    renders: 0, render() {throw Error("Chat must not redraw the page");}, updateChatView() {context.renders++;}, api});
  vm.runInContext(functions, context);
  return context;
}
(async () => {
  const saved = {session_id: 'saved-session', messages: [{role: 'user', content: '问题'}, {role: 'assistant', content: '回答', products: [{id: 1}]}]};
  const first = setup(async () => saved);
  await first.restoreChat(first.currentChatIdentity());
  assert.equal(first.sessionId, 'saved-session');
  assert.equal(first.renders, 1);
  assert.equal(first.chatLines.length, 2);
  assert.equal(first.chatLines[0].me, true);
  assert.equal(first.chatLines[1].products[0].id, 1);
  const refreshed = setup(async () => saved);
  await refreshed.restoreChat(refreshed.currentChatIdentity());
  assert.equal(refreshed.sessionId, first.sessionId);
  let resolve;
  const switched = setup(() => new Promise(r => {resolve = r;}));
  const pending = switched.restoreChat(switched.currentChatIdentity());
  switched.token = 'account-b';
  resolve(saved);
  await pending;
  assert.equal(switched.chatLines.length, 0);
  assert.equal(switched.sessionId, '');
  const failed = setup(async () => {throw Error('offline');});
  await failed.restoreChat(failed.currentChatIdentity());
  assert.equal(failed.chatRestored, false);
  assert.ok(failed.chatRestoreError);
  failed.api = async () => saved;
  await failed.restoreChat(failed.currentChatIdentity());
  assert.equal(failed.chatRestored, true);
  assert.equal(failed.chatRestoreError, '');
  console.log('Chat restore: saved messages, refreshed state, account switch, failure/retry passed.');
})().catch(error => {console.error(error); process.exitCode = 1;});
const localUpdate = source.slice(source.indexOf('function updateChatView('), source.indexOf('function renderChatToggle()'));
{
  let box = {draft: 'unsent', hidden: false, remove() {box = null;}};
  let fab = {remove() {fab = null;}};
  const page = {querySelector(selector) {return selector === '.chat' ? box : fab;}, append(node) {if (node.kind === 'fab') fab = node; else box = node;}};
  const state = vm.createContext({document: {getElementById: () => page}, shop: {}, chatOpen: false,
    storefrontSettings: () => ({assistant_enabled: true}),
    renderChatToggle: () => ({kind:'fab', remove() {fab = null;}}),
    renderChat: () => ({hidden:false, remove() {box = null;}})});
  vm.runInContext(localUpdate, state);
  const original = box;
  state.updateChatView();
  assert.equal(box, original);
  assert.equal(box.hidden, true);
  state.chatOpen = true;
  state.updateChatView();
  assert.equal(box, original);
  assert.equal(box.draft, 'unsent');
  assert.equal(box.hidden, false);
  console.log('Chat toggle preserves the existing DOM and unsent draft.');
}
