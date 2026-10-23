/* Offline operator-account outcomes; actual Chrome is a separate gate. */
"use strict";
const assert = require("node:assert/strict");
const { test } = require("node:test");
const { component, settle } = require("./test_ui_evaluate.js");
const user = (id, disabled = false) => ({ id, label: "Synthetic " + id, email_hash: "hash-" + id,
  created_at: "2026-10-13T10:00:00Z", disabled_at: disabled ? "2026-10-13T11:00:00Z" : null });
function setup(kind = "admin") {
  const { c, calls, window } = component(kind);
  c.state.screen = "adminusers";
  let rows = [user("a"), user("b", true)];
  window.VeritasAPI.get = async (p, opts) => { calls.push(["GET", p, opts]); return rows; };
  window.VeritasAPI.post = async (p, body, opts) => {
    calls.push(["POST", p, body, opts]); const created = { ...user("new"), label: body.label };
    rows.push(created); return created;
  };
  window.VeritasAPI.del = async (p, opts) => {
    calls.push(["DELETE", p, opts]); const id = decodeURIComponent(p.split("/").pop());
    rows = rows.filter(u => u.id !== id); return { admin_user_id: id, deleted: true };
  };
  return { c, calls, window };
}
test("operator account landing loads actual users and server status", async () => {
  const { c, calls } = setup();
  c.loadForScreen("adminusers"); await settle();
  assert.equal(calls[0]?.[1], "/admin/users", "operator accounts must request actual rows");
  assert.deepEqual(c.renderVals().adminUsers.map(u => u.id), ["a", "b"]);
  assert.equal(c.renderVals().adminUsers[1].status, "Disabled");
  assert.equal(c.renderVals().adminUsers[0].role, "Operator");
});

test("loading/empty/filter/page/error reflect actual rows without fixture emails", async () => {
  const { c, window } = setup(); let finish;
  window.VeritasAPI.get = () => new Promise(resolve => { finish = resolve; });
  c.loadUserAdmin(); assert.equal(c.renderVals().usersLoading, true);
  assert.equal(c.renderVals().usersEmpty, false);
  finish([]); await settle(); assert.equal(c.renderVals().usersEmpty, true);
  c.state.usersList.data = Array.from({ length: 23 }, (_, i) => user("row" + i));
  assert.equal(c.renderVals().adminUsers.length, 20);
  c.nextUsers(); assert.equal(c.renderVals().adminUsers.length, 3);
  c.setUsersFilter({ target: { value: "ROW22" } });
  assert.equal(c.state.usersPage, 0); assert.deepEqual(c.renderVals().adminUsers.map(u => u.id), ["row22"]);
  assert.equal("email" in c.renderVals().adminUsers[0], false);
  assert.equal("email_hash" in c.renderVals().adminUsers[0], false);
  window.VeritasAPI.get = async () => { throw { status: 403, kind: "consent" }; };
  c.loadUserAdmin(); await settle();
  assert.equal(c.renderVals().adminUsers.length, 0);
  assert.match(c.renderVals().usersListErrorText, /not permitted to administer operator accounts/);
});

test("create waits for response, trims input and refreshes persisted state", async () => {
  const { c, calls, window } = setup(); c.loadUserAdmin(); await settle();
  const native = window.VeritasAPI.post; let release;
  window.VeritasAPI.post = async (...args) => { await new Promise(resolve => { release = resolve; }); return native(...args); };
  c.state.usersEmail = " operator@example.com "; c.state.usersLabel = " New Operator ";
  c.createUser(); c.createUser(); assert.equal(c.state.usersBusy, true);
  assert.equal(c.state.usersNotice, ""); release(); await settle(); await settle();
  const posts = calls.filter(x => x[0] === "POST"); assert.equal(posts.length, 1);
  assert.deepEqual(posts[0][2], { email: "operator@example.com", label: "New Operator" });
  assert(posts[0][3].timeoutMs > 0);
  assert.equal(c.state.usersEmail, ""); assert.equal(c.state.usersLabel, "");
  assert(c.renderVals().adminUsers.some(u => u.id === "new"));
  assert.match(c.state.usersNotice, /created/); assert.equal(c.state.usersBusy, false);
});

test("invalid input, unsupported actions and non-admin planes cannot grant permissions", async () => {
  for (const kind of ["admin", "org", "candidate"]) {
    const { c, calls } = setup(kind);
    if (kind === "admin") { c.loadUserAdmin(); await settle(); }
    for (const email of ["", "no-at", "two@@example.com", "x@ example.com"]) {
      c.state.usersEmail = email; c.createUser();
    }
    c.state.usersEmail = "operator@example.com"; c.state.usersLabel = "x".repeat(201); c.createUser();
    c.changeUser("promote"); c.confirmUserDelete();
    if (kind !== "admin") {
      c.state.usersLabel = ""; c.state.usersList = { loading: false, data: [user("cached")], error: null };
      c.loadUserAdmin(); c.createUser(); c.armUserDelete("cached")(); c.confirmUserDelete();
      assert.equal(c.renderVals().adminUsers.length, 0); assert.equal(c.renderVals().usersEmail, "");
      assert.equal(c.renderVals().usersAdminDenied, true);
      assert.equal(calls.length, 0);
    }
    await settle(); assert.equal(calls.filter(x => x[0] !== "GET").length, 0);
  }
});

test("delete confirmation/cancel/refresh scope the target and explain self/last deletion", async () => {
  const { c, calls } = setup(); c.loadUserAdmin(); await settle();
  c.armUserDelete("a")(); assert.equal(calls.filter(x => x[0] === "DELETE").length, 0);
  assert.match(c.renderVals().usersConfirmCopy, /own account.*sign-in ends/);
  assert.match(c.renderVals().usersConfirmCopy, /last operator.*machine admin key/);
  c.cancelUserDelete(); c.confirmUserDelete(); await settle();
  assert.equal(calls.filter(x => x[0] === "DELETE").length, 0);
  c.armUserDelete("a")(); c.reloadUsers(); await settle(); c.confirmUserDelete();
  assert.equal(calls.filter(x => x[0] === "DELETE").length, 0);
  c.armUserDelete("b")(); c.confirmUserDelete(); c.confirmUserDelete(); await settle(); await settle();
  const deletes = calls.filter(x => x[0] === "DELETE"); assert.equal(deletes.length, 1);
  assert.equal(deletes[0][1], "/admin/users/b"); assert(deletes[0][2].timeoutMs > 0);
  assert.deepEqual(c.renderVals().adminUsers.map(u => u.id), ["a"]);
});

for (const error of [{ status: 409, detail: "operator already exists" },
  { status: 403, kind: "csrf", detail: "missing or invalid CSRF token" },
  { status: 403, kind: "consent", detail: "operation refused" },
  { status: 0, kind: "timeout", detail: "Request timed out" },
  { status: 0, kind: "network", detail: "Network unavailable" },
  { status: 503, detail: "Service unavailable" }]) {
  test("refused/ambiguous creation settles without false success: " + error.kind + error.status, async () => {
    const { c, window } = setup(); c.loadUserAdmin(); await settle();
    c.state.usersEmail = "retry@example.com"; c.state.usersLabel = "Retry";
    window.VeritasAPI.post = async () => { throw error; }; c.createUser(); await settle();
    assert.equal(c.state.usersBusy, false); assert.equal(c.state.usersNotice, "");
    assert.equal(c.state.usersEmail, "retry@example.com"); assert.equal(c.state.usersLabel, "Retry");
    assert(c.renderVals().usersActionError);
    if (error.kind === "consent") assert.match(c.renderVals().usersActionErrorText, /not permitted.*operator accounts/);
    if (["timeout", "network"].includes(error.kind) || error.status >= 500)
      assert.match(c.renderVals().usersActionErrorText, /may have completed.*Refresh.*before retry/);
  });
}

test("malformed/duplicate list and mutation replies refuse safely; refresh failure hides stale list", async () => {
  for (const rows of [{}, [user("a"), user("a")], [{ id: "bad" }]]) {
    const { c, window } = setup(); window.VeritasAPI.get = async () => rows;
    c.loadUserAdmin(); await settle(); assert(c.state.usersList.error);
    assert.equal(c.renderVals().adminUsers.length, 0);
  }
  const { c, window } = setup(); c.loadUserAdmin(); await settle();
  c.state.usersEmail = "valid@example.com"; window.VeritasAPI.post = async () => ({ id: "incomplete" });
  c.createUser(); await settle(); assert.equal(c.state.usersNotice, ""); assert(c.state.usersError);
  window.VeritasAPI.del = async () => ({ admin_user_id: "other", deleted: true });
  c.armUserDelete("a")(); c.confirmUserDelete(); await settle();
  assert.equal(c.state.usersNotice, ""); assert.equal(c.state.usersList.data.length, 2);
  window.VeritasAPI.get = async () => { throw { status: 503 }; };
  c.reloadUsers(); await settle(); assert.equal(c.renderVals().adminUsers.length, 0);
  assert.equal(c.renderVals().usersControlsDisabled, true);
});

test("navigation/session loss/unmount invalidate late actions and erase email drafts", async () => {
  for (const event of ["navigation", "session", "unmount"]) {
    const { c, window } = setup(); c.loadUserAdmin(); await settle(); let finish;
    window.VeritasAPI.post = () => new Promise(resolve => { finish = resolve; });
    c.state.usersEmail = "private@example.com"; c.createUser();
    if (event === "navigation") { c.nav("devices")(); c.nav("adminusers")(); }
    else if (event === "session") { c.handleSessionLost(); c.setState({ me: { kind: "admin" }, screen: "adminusers" }); }
    else c.componentWillUnmount();
    c.state.usersEmail = "new-draft@example.com";
    finish(user("foreign")); await settle(); assert.equal(c.state.usersEmail, "new-draft@example.com");
    assert(!c.state.usersNotice.includes("created"));
    if (event === "session") assert.equal(c.state.usersList.data, null);
  }
  const { c, window } = setup(); let finish;
  window.VeritasAPI.get = () => new Promise(resolve => { finish = resolve; });
  c.loadUserAdmin(); c.handleSessionLost(); finish([user("old")]); await settle();
  assert.equal(c.state.usersList.data, null); assert.equal(c.state.usersEmail, "");
});

test("deleted target 404 does not remove cached row optimistically; encoded ID stays scoped", async () => {
  const { c, calls, window } = setup(); c.loadUserAdmin(); await settle();
  c.state.usersList.data.push(user("slash /?#"));
  window.VeritasAPI.del = async (p, opts) => { calls.push(["DELETE", p, opts]); throw { status: 404, detail: "operator not found" }; };
  c.armUserDelete("slash /?#")(); c.confirmUserDelete(); await settle();
  assert.equal(calls.find(x => x[0] === "DELETE")[1], "/admin/users/slash%20%2F%3F%23");
  assert(c.renderVals().adminUsers.some(u => u.id === "slash /?#"));
  assert.equal(c.state.usersNotice, ""); assert.equal(c.state.usersBusy, false);
});

test("detached account callbacks keep their receiver and separate component instances", async () => {
  const first = setup(), second = setup();
  await first.c.loadUserAdmin(); await second.c.loadUserAdmin();
  const view = first.c.renderVals();
  assert.notEqual(view.createUser, second.c.renderVals().createUser);
  view.setUsersEmail({ target: { value: "detached@example.com" } });
  view.setUsersLabel({ target: { value: "Detached callback" } });
  await view.createUser();
  assert(first.c.renderVals().adminUsers.some(u => u.displayLabel === "Detached callback"));
  assert.equal(second.c.renderVals().adminUsers.length, 2);
  assert.equal(second.c.state.usersEmail, "");
  assert.equal(second.calls.filter(row => row[0] === "POST").length, 0);
  assert.equal(first.c.renderVals().createUser, view.createUser);
});

test("one component's stale account read cannot replace another component's current rows", async () => {
  const first = setup(), second = setup();
  let finish;
  first.window.VeritasAPI.get = () => new Promise(resolve => { finish = resolve; });
  second.window.VeritasAPI.get = async () => [user("second-only")];
  const pending = first.c.loadUserAdmin();
  await second.c.loadUserAdmin();
  first.c.handleSessionLost();
  first.c.setState({ me: { kind: "admin" }, screen: "adminusers" });
  finish([user("stale-first")]); await pending;
  assert.equal(first.c.state.usersList.data, null);
  assert.deepEqual(second.c.renderVals().adminUsers.map(u => u.id), ["second-only"]);
  assert.equal(second.c.state.usersBusy, false);
});
