const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const storage = new Map();
const context = vm.createContext({structuredClone, storage: {
  getItem: key => storage.get(key), setItem: (key, value) => storage.set(key, value), removeItem: key => storage.delete(key)
}});
vm.runInContext(fs.readFileSync("web/decoration.js", "utf8") + "\nglobalThis.Workspace = DecorationWorkspace;", context);
const snapshot = {revision: "a".repeat(64), appearance: {hero_height: 640, strip_tint: true, promises: [], storefront: {}},
  banners: [{id: 1, title: "原图", image_url: "/covers/pillow.jpg", subtitle: "", link_type: "none", link_value: "", enabled: true},
    {id: 2, title: "第二张", image_url: "/covers/cup.jpg", subtitle: "", link_type: "none", link_value: "", enabled: true}],
  sections: [], testimonials: []};
const workspace = new context.Workspace(snapshot, {id: 1}, context.storage, 9);
assert.equal(workspace.dirty, false);
const candidate = workspace.candidate("banners", {title: "未应用的预览"}, 1);
assert.equal(candidate.banners[0].title, "未应用的预览");
assert.equal(workspace.data.banners[0].title, "原图");
assert.equal(workspace.dirty, false);
workspace.mutate("banners", "PATCH", {title: "草稿标题"}, 1);
assert.equal(workspace.dirty, true);
assert.equal(snapshot.banners[0].title, "原图");
workspace.reorder("banners", [2, 1]);
assert.deepEqual([...workspace.data.banners.map(row => row.id)], [2, 1]);
assert.throws(() => workspace.reorder("banners", [1, 1]));
const restored = new context.Workspace(snapshot, {id: 1}, context.storage, 9);
assert.equal(restored.data.banners[1].title, "草稿标题");
assert.equal(restored.conflict, false);
const conflicted = new context.Workspace({...snapshot, revision: "b".repeat(64)}, {id: 1}, context.storage, 9);
assert.equal(conflicted.conflict, true);
const otherActor = new context.Workspace(snapshot, {id: 1}, context.storage, 10);
assert.equal(otherActor.dirty, false);
const added = workspace.mutate("sections", "POST", {title: "新增栏目", source: "manual", product_ids: []});
assert.ok(added.id < 0);
workspace.mutate("banners", "PATCH", {link_type: "section", link_value: String(added.id)}, 1);
workspace.mutate("sections", "DELETE", {}, added.id);
assert.equal(workspace.data.banners.find(row => row.id === 1).link_type, "none");
assert.equal(context.decorationPayload(workspace.data).sections.length, 0);
console.log("Decoration draft: isolated preview, staged mutation, reorder, refresh restore, actor isolation and conflicts passed");
