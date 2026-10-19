/* Offline org-admin outcomes; actual Chrome remains a separate gate. */
"use strict";
const assert = require("node:assert/strict");
const { test } = require("node:test");
const { component, settle } = require("./test_ui_evaluate.js");
const org = (id, weight = 1) => ({ id, name: "Synthetic " + id, status: "active",
  reliability_weight: weight, created_at: "2026-10-13T10:00:00Z" });
function setup(kind = "admin") {
  const { c, calls, window } = component(kind);
  c.state.screen = "adminorgs";
  let rows = [org("a"), org("b")];
  window.VeritasAPI.get = async (p, opts) => { calls.push(["GET", p, opts]); return rows; };
  window.VeritasAPI.post = async (p, body, opts) => {
    calls.push(["POST", p, body, opts]);
    if (p === "/ledger/orgs") { const created = { ...org("new"), name: body.name }; rows.push(created); return { org: created, api_key: "synthetic-new-key" }; }
    if (p.endsWith("/reliability")) { const id = p.split("/")[3]; rows = rows.map(o => o.id === id ? { ...o, reliability_weight: body.weight } : o); return rows.find(o => o.id === id); }
    return { org_id: p.split("/")[3], api_key: "synthetic-rotated-key" };
  };
  window.VeritasAPI.del = async (p, opts) => { calls.push(["DELETE", p, opts]); const id = p.split("/")[3]; rows = rows.filter(o => o.id !== id); return { org_id: id, deleted: true }; };
  return { c, calls, window, rows };
}

test("operator landing loads actual orgs and inspects server fields", async () => {
  const { c, calls } = setup();
  c.loadForScreen("adminorgs"); await settle();
  assert.equal(calls[0]?.[1], "/ledger/orgs", "org landing must request actual rows");
  assert.deepEqual(c.renderVals().adminOrgs.map(o => o.id), ["a", "b"]);
  c.selectOrg("b")();
  assert.equal(c.renderVals().orgSelected.id, "b");
  assert.equal(c.state.orgWeight, "1");
  assert.equal(c.renderVals().isMockScreen, false);
});

test("empty/loading/refused list never shows fixtures; local filtering paginates real rows", async () => {
  const { c, window } = setup();
  let finish;
  window.VeritasAPI.get = () => new Promise(resolve => { finish = resolve; });
  c.loadOrgAdmin();
  assert.equal(c.renderVals().orgListLoading, true);
  assert.equal(c.renderVals().orgEmpty, false);
  finish([]); await settle();
  assert.equal(c.renderVals().orgEmpty, true);
  assert.equal(c.renderVals().adminOrgs.length, 0);
  c.state.orgList.data = Array.from({ length: 23 }, (_, i) => org("row" + i));
  assert.equal(c.renderVals().adminOrgs.length, 20);
  c.nextOrgs(); assert.equal(c.renderVals().adminOrgs.length, 3);
  c.setOrgFilter({ target: { value: "row22" } });
  assert.equal(c.state.orgPage, 0);
  assert.deepEqual(c.renderVals().adminOrgs.map(o => o.id), ["row22"]);
  window.VeritasAPI.get = async () => { throw { status: 403, detail: "operation refused" }; };
  c.loadOrgAdmin(); await settle();
  assert.equal(c.renderVals().adminOrgs.length, 0);
  assert(c.renderVals().orgListErrorText);
});

test("create and reliability show saved results; one-time key is cleared on selection/navigation", async () => {
  const { c, calls } = setup();
  c.loadOrgAdmin(); await settle();
  c.setOrgName({ target: { value: " Synthetic Created " } });
  c.createOrg(); await settle(); await settle();
  assert(calls.some(x => x[0] === "POST" && x[1] === "/ledger/orgs" && x[2].name === "Synthetic Created"));
  assert.equal(c.state.orgKey, "synthetic-new-key");
  assert.equal(c.renderVals().orgKeyType, "password");
  c.toggleOrgKey(); assert.equal(c.renderVals().orgKeyType, "text");
  c.selectOrg("b")(); assert.equal(c.state.orgKey, "");
  c.setOrgWeight({ target: { value: "1.5" } });
  c.saveOrgReliability(); await settle(); await settle();
  assert.equal(c.renderVals().orgSelected.reliability_weight, 1.5);
  c.state.orgKey = "synthetic-key"; c.nav("devices")();
  assert.equal(c.state.orgKey, "");
});

test("invalid names/weights and wrong account planes cannot mutate", async () => {
  for (const kind of ["org", "candidate", "admin"]) {
    const { c, calls } = setup(kind);
    if (kind === "admin") { c.loadOrgAdmin(); await settle(); c.selectOrg("a")(); }
    c.state.orgName = " "; c.createOrg();
    for (const value of ["", "-1", "NaN", "Infinity"]) { c.state.orgWeight = value; c.saveOrgReliability(); }
    if (kind !== "admin") { c.state.orgName = "Unauthorized"; c.createOrg(); c.loadOrgAdmin(); }
    await settle();
    assert.equal(calls.filter(x => x[0] !== "GET").length, 0);
  }
});

test("rotation/deletion are confirmed, target-scoped and duplicate guarded", async () => {
  const { c, window, calls } = setup();
  c.loadOrgAdmin(); await settle(); c.selectOrg("a")();
  c.armOrgRotate(); assert.equal(calls.filter(x => x[0] === "POST").length, 0);
  c.cancelOrgConfirm(); c.confirmOrgAction(); await settle();
  assert.equal(calls.filter(x => x[0] === "POST").length, 0);
  c.armOrgRotate(); c.confirmOrgAction(); await settle(); await settle();
  assert.equal(c.state.orgKey, "synthetic-rotated-key");
  c.armOrgDelete(); c.selectOrg("b")(); c.confirmOrgAction(); await settle();
  assert.equal(calls.filter(x => x[0] === "DELETE").length, 0);
  let finish;
  window.VeritasAPI.del = (p, opts) => { calls.push(["DELETE", p, opts]); return new Promise(resolve => { finish = resolve; }); };
  c.armOrgDelete(); c.confirmOrgAction(); c.confirmOrgAction();
  assert.equal(calls.filter(x => x[0] === "DELETE").length, 1);
  assert.equal(calls.find(x => x[0] === "DELETE")[1], "/ledger/orgs/b");
  finish({ org_id: "b", deleted: true }); await settle();
});

for (const error of [{ status: 409, detail: "organization name already exists" },
    { status: 403, detail: "missing or invalid CSRF token", kind: "csrf" },
    { status: 403, detail: "operation refused", kind: "consent" },
    { status: 0, detail: "Request timed out", kind: "timeout" },
    { status: 503, detail: "Service unavailable" }]) {
  test("failure retains input, settles and avoids success: " + error.status, async () => {
    const { c, window } = setup(); c.loadOrgAdmin(); await settle();
    window.VeritasAPI.post = async () => { throw error; };
    c.state.orgName = "Retry name"; c.createOrg(); await settle();
    assert.equal(c.state.orgBusy, false); assert.equal(c.state.orgName, "Retry name");
    assert.equal(c.state.orgKey, ""); assert.equal(c.state.orgNotice, "");
    assert(c.renderVals().orgActionErrorText);
    if (error.kind === "consent") assert.match(c.renderVals().orgActionErrorText, /not permitted.*administer organisations/i);
    if (error.kind === "timeout" || error.status >= 500) assert.match(c.renderVals().orgActionErrorText, /refresh.*before retry/i);
  });
}

test("session loss clears keys and late list/action cannot alter a new account", async () => {
  const { c, window } = setup(); c.loadOrgAdmin(); await settle();
  let finish;
  window.VeritasAPI.post = () => new Promise(resolve => { finish = resolve; });
  c.state.orgName = "Pending"; c.createOrg(); c.handleSessionLost();
  c.setState({ me: { kind: "admin" }, screen: "adminorgs", orgName: "New account input" });
  finish({ org: org("foreign"), api_key: "old-account-key" }); await settle();
  assert.equal(c.state.orgKey, ""); assert.equal(c.state.orgName, "New account input");
  let list;
  window.VeritasAPI.get = () => new Promise(resolve => { list = resolve; });
  c.loadOrgAdmin(); c.handleSessionLost(); list([org("old")]); await settle();
  assert.equal(c.state.orgList.data, null);
});

test("malformed success and navigation/unmount never advertise a key or mutate a new screen", async () => {
  const { c, window } = setup(); c.loadOrgAdmin(); await settle();
  window.VeritasAPI.post = async () => ({ org: org("new") });
  c.state.orgName = "Name"; c.createOrg(); await settle();
  assert.equal(c.state.orgKey, ""); assert(c.state.orgError);
  let finish;
  window.VeritasAPI.post = () => new Promise(resolve => { finish = resolve; });
  c.createOrg(); c.nav("devices")();
  c.nav("adminorgs")();
  finish({ org: org("new"), api_key: "late-key" }); await settle();
  assert.equal(c.state.screen, "adminorgs"); assert.equal(c.state.orgKey, "");
  c.state.screen = "adminorgs"; c.createOrg(); c.componentWillUnmount();
  finish({ org: org("new"), api_key: "late-key" }); await settle();
  assert.equal(c.state.orgKey, "");
});
