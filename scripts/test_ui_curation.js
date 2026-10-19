/* Offline shipped curation behavior; actual Chrome is a separate gate. */
"use strict";
const assert = require("node:assert/strict");
const { test } = require("node:test");
const { component, settle } = require("./test_ui_evaluate.js");
const term = (key = "synthetic raw", revision = "a".repeat(64)) => ({ norm_key: key,
  display_name: key, source_types: ["linkedin_export"], occurrences: 2,
  first_seen: "2026-10-14T10:00:00Z", last_seen: "2026-10-14T10:00:00Z",
  review_revision: revision, status: "pending" });
const receipt = body => ({ action: body.action, alias: body.alias ?? null,
  canonical: body.canonical ?? null, category: body.category ?? null,
  decided_at: "2026-10-14T10:01:00Z", admin_user_id: "operator" });
function setup(kind = "admin") {
  const { c, calls, window } = component(kind); c.state.screen = "curation";
  let rows = [term()];
  window.VeritasAPI.get = async (p, opts) => { calls.push(["GET", p, opts]); return p === "/auth/sessions" ? [] : { terms: rows, next_cursor: null }; };
  window.VeritasAPI.post = async (p, body, opts) => {
    calls.push(["POST", p, body, opts]); rows = rows.filter(t => t.norm_key !== body.norm_key); return receipt(body);
  };
  return { c, calls, window };
}
async function review(c) {
  await c.reloadCuration(); await settle(); c.renderVals().curation[0].review();
  c.setCurationAlias({ target: { value: "Approved alias" } });
  c.setCurationCanonical({ target: { value: "python" } });
  c.setCurationCategory({ target: { value: "language" } });
}
test("guarded browser decision sends the loaded snapshot revision", async () => {
  const { c, calls } = setup(); await review(c);
  await c.approveCuration(); await settle();
  const post = calls.find(x => x[0] === "POST");
  assert.equal(post[2].expected_revision, "a".repeat(64), "map must bind to the loaded review snapshot");
  assert(post[3].timeoutMs > 0); assert.equal(c.renderVals().curationEmpty, true);
  assert.equal(c.state.curationNotice, "Vocabulary approved.");
});

test("create and ignore use exact revisions; approval starts blank and never infers an alias", async () => {
  for (const action of ["create", "ignore"]) {
    const { c, calls } = setup(); await c.reloadCuration();
    if (action === "ignore") await c.renderVals().curation[0].ignore();
    else {
      c.renderVals().curation[0].review(); assert.equal(c.state.curationAlias, "");
      c.approveCuration(); await settle(); assert.equal(calls.filter(x => x[0] === "POST").length, 0);
      c.setCurationAction({ target: { value: "create" } });
      c.setCurationAlias({ target: { value: " Approved tool " } });
      c.setCurationCanonical({ target: { value: " new_tool " } });
      c.setCurationCategory({ target: { value: "data" } }); await c.approveCuration();
    }
    const posts = calls.filter(x => x[0] === "POST"); assert.equal(posts.length, 1);
    assert.equal(posts[0][2].action, action); assert.equal(posts[0][2].expected_revision, "a".repeat(64));
    if (action === "create") assert.equal(posts[0][2].alias, "Approved tool");
    else assert.equal("alias" in posts[0][2], false);
    assert.equal(c.state.curationSelection, null); assert.equal(c.renderVals().curationEmpty, true);
  }
});

test("actual page/loading/empty counts and overlapping changed rows use server values", async () => {
  const { c, calls, window } = setup(); let finish;
  window.VeritasAPI.get = (p, opts) => { calls.push(["GET", p, opts]); return new Promise(r => { finish = r; }); };
  c.reloadCuration(); c.reloadCuration(); c.moreCuration();
  assert.equal(calls.length, 1); assert(calls[0][1].includes("limit=20")); assert(calls[0][2].timeoutMs > 0);
  assert.equal(c.renderVals().curationLoading, true); assert.equal(c.renderVals().curationEmpty, false);
  finish({ terms: [term()], next_cursor: "cursor +/=?" }); await settle();
  c.renderVals().curation[0].review(); c.state.curationAlias = "Draft";
  c.moreCuration(); assert(calls[1][1].endsWith("cursor=cursor%20%2B%2F%3D%3F"));
  assert.equal(c.renderVals().curationControlsDisabled, true);
  finish({ terms: [term("synthetic raw", "b".repeat(64)), term("second raw")], next_cursor: null }); await settle();
  assert.equal(c.renderVals().curationLoaded, 2); assert.equal(c.state.curationSelection, null);
  assert.equal(c.state.curationAlias, ""); assert.equal(c.renderVals().curation[0].count, 2);
  c.reloadCuration(); finish({ terms: [], next_cursor: null }); await settle();
  assert.equal(c.renderVals().curationEmpty, true); assert.equal(c.renderVals().curationLoaded, 0);
});

test("malformed queue data and nonadvancing pages refuse safely and hide stale data", async () => {
  for (const page of [{}, { terms: null }, { terms: [term()], next_cursor: 5 },
    { terms: [{ ...term(), review_revision: null }], next_cursor: null },
    { terms: [{ ...term(), occurrences: -1 }], next_cursor: null },
    { terms: [term(), term()], next_cursor: null },
    { terms: [{ ...term(), first_seen: "invalid" }], next_cursor: null },
    { terms: [{ ...term(), display_name: "x".repeat(129) }], next_cursor: null },
    { terms: [{ ...term(), status: "resolved" }], next_cursor: null },
    { terms: [{ ...term(), source_types: ["github", "github"] }], next_cursor: null },
    { terms: [], next_cursor: "impossible" }]) {
    const { c, window } = setup(); window.VeritasAPI.get = async () => page;
    await c.reloadCuration(); assert.equal(c.renderVals().curation.length, 0);
    assert(c.renderVals().curationError); assert.equal(c.renderVals().curationControlsDisabled, true);
  }
  const { c, window } = setup(); window.VeritasAPI.get = async () => ({ terms: [term()], next_cursor: "same" });
  await c.reloadCuration(); await c.moreCuration(); assert(c.state.curationList.error);
  assert.equal(c.renderVals().curation.length, 0);
});

for (const error of [{ status: 422, kind: "unprocessable", detail: "category does not match canonical" },
  { status: 403, kind: "csrf", detail: "missing or invalid CSRF token" },
  { status: 403, kind: "consent", detail: "refused" },
  { status: 409, kind: "conflict", detail: "approved alias already exists" }]) {
  test("known refusal settles retaining draft: " + error.kind, async () => {
    const { c, calls, window } = setup(); await review(c);
    window.VeritasAPI.post = async () => { throw error; }; await c.approveCuration();
    assert.equal(c.state.curationAlias, "Approved alias"); assert.equal(c.state.curationBusy, false);
    assert.equal(c.state.curationNotice, ""); assert.equal(c.state.curationNeedsRefresh, false);
    assert.equal(calls.filter(x => x[0] === "GET").length, 1);
    if (error.kind === "consent") assert.match(c.renderVals().curationErrorText, /not permitted.*curation queue/);
    else if (error.kind === "csrf") assert.match(c.renderVals().curationErrorText, /Sign in again/);
    else assert.match(c.renderVals().curationErrorText, new RegExp(error.detail));
  });
}

for (const error of [{ status: 0, kind: "timeout", detail: "Request timed out" },
  { status: 0, kind: "network", detail: "Network unavailable" }, { status: 503, kind: "http", detail: "Unavailable" }]) {
  test("uncertain write requires successful read before explicit retry: " + error.kind, async () => {
    const { c, calls, window } = setup(); await review(c); let posts = 0;
    window.VeritasAPI.post = async () => { posts++; throw error; };
    await c.approveCuration(); await c.approveCuration(); await c.renderVals().curation[0].ignore();
    c.setCurationAlias({ target: { value: "changed during uncertainty" } });
    assert.equal(posts, 1); assert.equal(c.state.curationAlias, "Approved alias");
    assert(c.renderVals().curationNeedsRefresh); assert.match(c.renderVals().curationErrorText, /may have completed.*Refresh queue/);
    const nativeGet = window.VeritasAPI.get; window.VeritasAPI.get = async () => { throw { kind: "network", detail: "read failed" }; };
    await c.reloadCuration(); assert(c.renderVals().curationNeedsRefresh); assert(c.renderVals().curationControlsDisabled);
    assert.equal(c.state.curationAlias, "Approved alias"); assert(c.state.curationSelection);
    window.VeritasAPI.get = nativeGet; await c.reloadCuration(); assert.equal(c.state.curationNeedsRefresh, false);
    assert.equal(c.state.curationAlias, "Approved alias");
    assert.equal(posts, 1); assert.equal(calls.filter(x => x[0] === "GET").length, 2);
  });
}

test("duplicate writes, refresh and draft edits cannot race a pending decision", async () => {
  const { c, calls, window } = setup(); await review(c); let finish;
  window.VeritasAPI.post = (p, b, o) => { calls.push(["POST", p, b, o]); return new Promise(r => { finish = () => r(receipt(b)); }); };
  const pending = c.approveCuration(); c.approveCuration(); c.reloadCuration(); c.moreCuration(); c.cancelCuration();
  c.setCurationAlias({ target: { value: "new text" } });
  assert.equal(calls.filter(x => x[0] === "POST").length, 1); assert.equal(calls.filter(x => x[0] === "GET").length, 1);
  assert.equal(c.state.curationAlias, "Approved alias"); assert(c.state.curationBusy);
  finish(); await pending; assert.equal(c.state.curationBusy, false);
});

test("stale conflict clears raw draft and never silently rebinds to a fresh revision", async () => {
  const { c, calls, window } = setup(); await review(c); let posts = 0;
  window.VeritasAPI.post = async () => { posts++; throw { status: 409, kind: "conflict", detail: "review snapshot changed; refresh before deciding" }; };
  window.VeritasAPI.get = async () => ({ terms: [term("synthetic raw", "b".repeat(64))], next_cursor: null });
  await c.approveCuration(); await c.approveCuration();
  assert.equal(posts, 1); assert.equal(c.state.curationSelection, null); assert.equal(c.state.curationAlias, "");
  assert.match(c.renderVals().curationErrorText, /review changed.*Select the term again/);
  assert.equal(c.state.curationNotice, ""); assert.equal(calls.filter(x => x[0] === "GET").length, 1);
  c.renderVals().curation[0].review(); assert.equal(c.state.curationSelection.review_revision, "b".repeat(64));
  assert.equal(c.state.curationAlias, "");
});

test("missing/expired term refreshes to empty and discards stale editor", async () => {
  const { c, window } = setup(); await review(c);
  window.VeritasAPI.post = async () => { throw { status: 404, kind: "not_found" }; };
  window.VeritasAPI.get = async () => ({ terms: [], next_cursor: null });
  await c.approveCuration(); assert(c.renderVals().curationEmpty);
  assert.equal(c.state.curationSelection, null); assert.match(c.renderVals().curationErrorText, /no longer available/);
});

test("invalid receipts never report success and require a read before another decision", async () => {
  for (const result of [null, {}, { action: "ignore" },
    { ...receipt({ action: "map", alias: "Approved alias", canonical: "python", category: "language" }), norm_key: "private" }]) {
    const { c, window } = setup(); await review(c); window.VeritasAPI.post = async () => result;
    await c.approveCuration(); assert.equal(c.state.curationNotice, ""); assert(c.state.curationNeedsRefresh);
    assert.equal(c.state.curationAlias, "Approved alias"); assert.equal(c.state.curationBusy, false);
  }
});

test("wrong planes neither fetch nor render cached raw queue/editor/errors", async () => {
  for (const kind of ["org", "candidate"]) {
    const { c, calls } = setup(kind);
    Object.assign(c.state, { curationList: { loading: false, data: { terms: [term()], next_cursor: null }, error: null },
      curationSelection: term(), curationAlias: "Private draft", curationError: { detail: "Private error" } });
    await c.reloadCuration(); c.selectCuration(term())(); c.ignoreCuration(term())(); c.approveCuration();
    const vals = c.renderVals(); assert(vals.curationDenied); assert.equal(vals.curation.length, 0);
    assert.equal(vals.curationAlias, ""); assert.equal(vals.curationSelectedName, ""); assert.equal(vals.curationErrorText, "");
    assert.equal(calls.length, 0);
  }
});

test("navigation clears raw state and ignores late list responses after returning", async () => {
  const { c, window } = setup(); let finish;
  window.VeritasAPI.get = () => new Promise(r => { finish = r; });
  c.reloadCuration(); const old = finish;
  c.nav("devices")(); assert.equal(c.state.curationList.data, null); assert.equal(c.state.curationAlias, "");
  c.nav("curation")(); finish({ terms: [term("new raw")], next_cursor: null }); await settle();
  old({ terms: [term("private old raw")], next_cursor: null }); await settle();
  assert.equal(c.renderVals().curation[0].term, "new raw");
});

test("late old-view decision cannot clear a newer draft or busy token", async () => {
  const { c, window } = setup(); await review(c); const pending = [];
  window.VeritasAPI.post = (_p, b) => new Promise(r => { pending.push(() => r(receipt(b))); });
  c.approveCuration(); c.nav("devices")(); c.nav("curation")(); await settle();
  c.renderVals().curation[0].review(); c.state.curationAlias = "New alias";
  c.state.curationCanonical = "python"; c.state.curationCategory = "language"; c.approveCuration();
  pending[0](); await settle(); assert.equal(c.state.curationAlias, "New alias"); assert(c.state.curationBusy);
  pending[1](); await settle(); assert.equal(c.state.curationBusy, false); assert.equal(c.state.curationNotice, "Vocabulary approved.");
});

test("session loss and unmount invalidate stale success/error reads and writes", async () => {
  for (const event of ["session", "unmount"]) {
    const { c, window } = setup(); await review(c); let fail;
    window.VeritasAPI.post = () => new Promise((_r, reject) => { fail = reject; });
    c.approveCuration();
    if (event === "session") { c.handleSessionLost(); assert.equal(c.state.curationList.data, null); assert.equal(c.state.curationAlias, ""); }
    else c.componentWillUnmount();
    c.state.curationAlias = "New session draft"; c.state.curationBusy = true;
    fail({ status: 503 }); await settle(); assert.equal(c.state.curationAlias, "New session draft"); assert(c.state.curationBusy);
    assert.equal(c.state.curationError, null);
  }
  const { c, window } = setup(); let finish;
  window.VeritasAPI.get = () => new Promise(r => { finish = r; }); c.reloadCuration(); c.handleSessionLost();
  finish({ terms: [term("old account raw")], next_cursor: null }); await settle(); assert.equal(c.state.curationList.data, null);
});
