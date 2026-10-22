/* Screening handler characterization; real Chrome runs separately. Reuse the
 * shared composed-component fixture, keeping batch cases in their own area. */
"use strict";
const assert = require("node:assert/strict");
const { test } = require("node:test");
const { component, settle } = require("./test_ui_evaluate.js");
const held = data => ({ loading: false, data, error: null });
const batch = (id, counts = { pending: 2, processing: 0, done: 0, failed: 0 }) =>
  ({ id, name: "Synthetic " + id, domain: "data_eng", status: "pending", counts });
function setup() {
  const ctx = component();
  ctx.c.state.screen = "queue";
  ctx.window.VeritasAPI.get = async p => {
    ctx.calls.push(["GET", p]);
    if (p === "/screening/batches") return { batches: [], next_cursor: null };
    if (p.includes("/summary")) return { n_screened: 0, by_risk_band: {}, top_signals: [] };
    if (p.includes("/queue")) return { rows: [], next_cursor: null };
    return batch(p.split("/").at(-1));
  };
  return ctx;
}
function pick(c, files) {
  const target = { files, value: "selected" };
  c.pickFiles({ target });
  assert.equal(target.value, "");
}

test("screening intake appends files, classifies types and removes/reselects", () => {
  const { c } = setup();
  pick(c, [{ name: "resume.PDF", size: 1048577 }, { name: "notes.md", size: 12 }]);
  pick(c, [{ name: "unsupported.docx", size: 100 }]);
  assert.deepEqual(c.state.files.map(f => f.kind), ["pdf", "text", "unsupported"]);
  let view = c.renderVals();
  assert.equal(view.fileCountLabel, "3 files ready");
  assert.equal(view.files[2].bad, true);
  assert.match(view.files[0].meta, /1.0 MB/);
  view.files[2].remove();
  assert.equal(c.state.files.length, 2);
  view.clearFiles();
  assert.equal(c.renderVals().hasFiles, false);
  pick(c, [{ name: "resume.PDF", size: 1 }]);
  assert.equal(c.state.files.length, 1);
});

test("text/PDF registration reads actual file payloads and alone starts processing", async () => {
  const { c, window, calls } = setup();
  let finish;
  window.VeritasAPI.post = (p, body) => {
    calls.push(["POST", p, body]);
    return p === "/screening/batches" ? Promise.resolve(batch("new"))
      : new Promise(resolve => { finish = resolve; });
  };
  c.state.domain = "data_eng";
  c.setBatchNameInput({ target: { value: "  Synthetic intake  " } });
  pick(c, [{ name: "resume.txt", text: "Synthetic readable resume" }, { name: "resume.pdf", payload: "JVBERi0=" }]);
  c.submitUpload(); await settle();
  assert.deepEqual(calls.find(x => x[0] === "POST"), ["POST", "/screening/batches", {
    name: "Synthetic intake", domain: "data_eng", items: [
      { resume_text: "Synthetic readable resume" }, { resume_pdf_b64: "JVBERi0=" }
    ]
  }]);
  assert.equal(c.state.selectedBatch, "new");
  assert.equal(c.state.screen, "queue");
  assert.equal(c.state.files.length, 0);
  assert.equal(c.state.uploadBusy, false);
  assert.equal(c.state.driving, true);
  finish({ processed: 2, failed: 0, remaining: 0 }); await settle();
  assert.equal(c.state.driveDone, 2);
  assert.equal(c.state.driving, false);
});

test("empty, unsupported and blank text refuse without HTTP registration", async () => {
  const { c, calls } = setup();
  c.submitUpload();
  assert.match(c.renderVals().uploadErrorText, /Choose at least one/);
  pick(c, [{ name: "bad.docx" }]); c.submitUpload();
  assert.match(c.renderVals().uploadErrorText, /bad.docx/);
  c.clearFiles(); pick(c, [{ name: "blank.txt", text: " \n " }]);
  c.submitUpload(); await settle();
  assert.match(c.renderVals().uploadErrorText, /Nothing to screen in: blank.txt/);
  assert.equal(c.state.files.length, 1);
  assert.equal(c.state.uploadBusy, false);
  assert.equal(calls.filter(x => x[0] === "POST").length, 0);
});

test("local disk and indexed API failures retain files and name the failing PDF", async () => {
  const { c, window, calls } = setup();
  pick(c, [{ name: "broken.pdf", payload: "broken" }]);
  const read = c._readFile;
  c._readFile = async () => { throw { local: true, detail: "Could not read broken.pdf from disk." }; };
  c.submitUpload(); await settle();
  assert.match(c.renderVals().uploadErrorText, /Could not read broken.pdf from disk/);
  assert.equal(calls.length, 0);
  c._readFile = read;
  window.VeritasAPI.post = async () => { throw { status: 422, detail: "item 0: unreadable_pdf" }; };
  c.submitUpload(); await settle();
  assert.match(c.renderVals().uploadErrorText, /broken.pdf.*unreadable_pdf.*nothing was registered/);
  assert.equal(c.state.files.length, 1);
  assert.equal(c.state.selectedBatch, null);
  assert.equal(c.state.uploadBusy, false);
});

test("opening a newest or explicit batch never starts billable processing", async () => {
  const { c, window, calls } = setup();
  const get = window.VeritasAPI.get;
  window.VeritasAPI.get = async p => p === "/screening/batches"
    ? { batches: [batch("newest")] } : get(p);
  c.loadScreening(); await settle();
  assert.equal(c.state.selectedBatch, "newest");
  assert.equal(c.state.batch.data.id, "newest");
  c.selectBatch("other")(); await settle();
  assert.equal(c.state.batch.data.id, "other");
  assert.equal(calls.filter(x => x[0] === "POST").length, 0);
});

test("switching batches discards all three late reads from the previous batch", async () => {
  const { c, window } = setup();
  const pending = [];
  const get = window.VeritasAPI.get;
  window.VeritasAPI.get = p => p.includes("/old")
    ? new Promise(resolve => pending.push({ p, resolve })) : get(p);
  c.selectBatch("old")();
  c.selectBatch("new")(); await settle();
  assert.equal(pending.length, 3);
  pending.forEach(x => x.resolve({ id: "old", rows: [{ item_id: "old" }] })); await settle();
  assert.equal(c.state.selectedBatch, "new");
  assert.equal(c.state.batch.data.id, "new");
  assert.deepEqual(c.state.queue.data.rows, []);
  assert.equal(c.state.summary.data.n_screened, 0);
});

test("driver starts once, runs sequentially, accumulates counts and stops at zero", async () => {
  const { c, window, calls } = setup();
  const pending = [];
  window.VeritasAPI.post = p => {
    calls.push(["POST", p]);
    return new Promise(resolve => pending.push(resolve));
  };
  c.state.selectedBatch = "owned";
  const start = c.startProcessing;
  start(); start();
  assert.equal(pending.length, 1);
  pending[0]({ processed: 1, failed: 1, remaining: 1 }); await settle();
  assert.equal(pending.length, 2);
  assert.equal(c.state.driveDone, 1); assert.equal(c.state.driveFailed, 1);
  pending[1]({ processed: 1, failed: 0, remaining: 0 }); await settle();
  assert.equal(pending.length, 2);
  assert.equal(c.state.driveDone, 2); assert.equal(c.state.driving, false);
  assert(calls.filter(x => x[0] === "POST").every(x => x[1] === "/screening/batches/owned/process"));
});

test("process failure stops without replay and allows an explicit restart", async () => {
  const { c, window } = setup();
  let count = 0;
  window.VeritasAPI.post = async () => { count++; throw { status: 503, detail: "Synthetic process refusal" }; };
  c.state.selectedBatch = "owned";
  c.startProcessing(); await settle(); await settle();
  assert.equal(count, 1); assert.equal(c.state.driving, false);
  assert.match(c.renderVals().driveErrorText, /Synthetic process refusal/);
  window.VeritasAPI.post = async () => { count++; return { processed: 1, remaining: 0 }; };
  c.startProcessing(); await settle();
  assert.equal(count, 2); assert.equal(c.state.driveError, null);
});

for (const action of ["stop", "switch", "session", "unmount"]) {
  test(`late successful process result is ignored after ${action}`, async () => {
    const { c, window } = setup();
    let finish;
    window.VeritasAPI.post = () => new Promise(resolve => { finish = resolve; });
    c.state.selectedBatch = "old"; c.startProcessing();
    if (action === "stop") c.stopProcessing();
    if (action === "switch") c.selectBatch("new")();
    if (action === "session") c.handleSessionLost();
    if (action === "unmount") c.componentWillUnmount();
    await settle(); // Let the newly selected batch's own reads finish first.
    const snapshot = JSON.stringify(c.state);
    finish({ processed: 9, failed: 2, remaining: 1 }); await settle();
    assert.equal(JSON.stringify(c.state), snapshot);
    assert.equal(c._driving, false);
  });
}

test("batch and queue cursor paging appends with encoded cursors and keeps data on refusal", async () => {
  const { c, window, calls } = setup();
  c.state.batchList = held({ batches: [batch("first")], next_cursor: "a+/=" });
  window.VeritasAPI.get = async p => { calls.push(["GET", p]); return { batches: [batch("second")], next_cursor: null }; };
  const more = c.moreBatches; more(); await settle();
  assert.equal(calls[0][1], "/screening/batches?cursor=a%2B%2F%3D");
  assert.deepEqual(c.state.batchList.data.batches.map(b => b.id), ["first", "second"]);
  c.state.selectedBatch = "owned";
  c.state.queue = held({ rows: [{ item_id: "first" }], next_cursor: "cursor" });
  window.VeritasAPI.get = async () => { throw { detail: "Synthetic paging refusal" }; };
  c.moreQueue(); await settle();
  assert.equal(c.state.queue.data.rows.length, 1); assert.equal(c.state.moreBusy, null);
  assert.match(c.state.queue.error.detail, /paging refusal/);
  window.VeritasAPI.get = async p => { assert.equal(p, "/screening/batches/owned/queue?cursor=cursor"); return { rows: [{ item_id: "second" }], next_cursor: null }; };
  c.moreQueue(); await settle();
  assert.deepEqual(c.state.queue.data.rows.map(r => r.item_id), ["first", "second"]);
  assert.equal(c.state.queue.error, null);
});

test("confirmed deletion stops propagation, drops selected data and invalidates pending refresh", async () => {
  const { c, window } = setup();
  c.state.selectedBatch = "delete";
  const pending = [];
  window.VeritasAPI.get = () => new Promise(resolve => { pending.push(resolve); });
  c.refreshBatch("delete");
  let stopped = 0;
  const event = { stopPropagation() { stopped++; } };
  c.armDelete("delete")(event); assert.equal(c.state.deleteArmed, "delete");
  c.cancelDelete(event); assert.equal(c.state.deleteArmed, null);
  let deletes = 0;
  window.VeritasAPI.del = async p => { deletes++; assert.equal(p, "/screening/batches/delete"); };
  const oldReads = pending.slice();
  c.confirmDelete("delete")(event); await settle();
  assert.equal(deletes, 1); assert.equal(stopped, 3);
  assert.equal(c.state.selectedBatch, null); assert.equal(c._viewBatch, null);
  oldReads.forEach(resolve => resolve({ rows: [{ item_id: "deleted" }] })); await settle();
  assert.equal(c.state.queue.data, null); assert.equal(c.state.batch.data, null);
});

test("in-app summary navigation retains the current driver without changing screens on completion", async () => {
  const { c, window } = setup();
  let finish;
  window.VeritasAPI.post = () => new Promise(resolve => { finish = resolve; });
  c.state.selectedBatch = "owned"; c.startProcessing();
  c.goSummary(); await settle();
  assert.equal(c.state.screen, "summary"); assert.equal(c.state.driving, true);
  finish({ processed: 1, remaining: 0 }); await settle();
  assert.equal(c.state.screen, "summary"); assert.equal(c.state.driving, false);
  assert.equal(c.state.driveDone, 1);
});

test("batch read and delete errors render server failures and recover without deleting data locally", async () => {
  const { c, window } = setup();
  const get = window.VeritasAPI.get;
  c.state.selectedBatch = "owned";
  window.VeritasAPI.get = async () => { throw { status: 503, detail: "Synthetic read refusal" }; };
  c.refresh(); await settle();
  assert.equal(c.renderVals().queueError, true);
  assert.match(c.renderVals().queueErrorText, /Synthetic read refusal/);
  window.VeritasAPI.get = get;
  c.refresh(); await settle();
  assert.equal(c.renderVals().queueError, false);
  window.VeritasAPI.del = async () => { throw { status: 403, detail: "Synthetic delete refusal" }; };
  c.confirmDelete("owned")(); await settle();
  assert.equal(c.state.selectedBatch, "owned");
  assert.equal(c.state.batch.data.id, "owned");
  assert.equal(c.state.busyId, null);
  assert.match(c.renderVals().batchesErrorText, /Synthetic delete refusal/);
});

test("screening mappings use whole-batch bands, screened shares and stable report callbacks", () => {
  const { c } = setup();
  c.state.selectedBatch = "owned";
  c.state.batch = held(batch("owned", { pending: 6, processing: 0, done: 3, failed: 1 }));
  c.state.batchList = held({ batches: [c.state.batch.data] });
  c.state.summary = held({ n_screened: 3, by_risk_band: { low: 2, insufficient_data: 1 }, top_signals: [] });
  c.state.queue = held({ rows: [
    { item_id: "pending", status: "pending", risk_score: null, reason: "not screened yet" },
    { item_id: "insufficient", status: "done", report_id: "rep_owned", risk_score: 0,
      signals: { risk_band: "insufficient_data", risk_confidence: 0 }, reason: "Insufficient evidence" }
  ], next_cursor: "next" });
  const first = c.renderVals(), second = c.renderVals();
  assert.equal(first.batchProgressLabel, "4 of 10 screened");
  assert.equal(first.bandLow, 2); assert.equal(first.shareLow, "67%");
  assert.equal(first.shareInsufficient, "33%");
  assert.match(first.summaryMeta, /Advisory throughout/);
  assert.equal(first.candidates[0].openable, false);
  assert.equal(first.candidates[0].open, c.noop);
  assert.equal(first.candidates[0].bandLabel, "Not screened");
  assert.equal(first.candidates[1].scoreLabel, "—");
  assert.equal(first.candidates[1].open, second.candidates[1].open);
  assert.equal(first.batchRows[0].open, second.batchRows[0].open);
  assert.equal(first.startProcessing, c.startProcessing);
  first.candidates[1].open();
  assert.equal(c.state.screen, "report"); assert.equal(c._viewReport, "rep_owned");
  c.state.driving = true;
  assert.equal(c.renderVals().hasMoreQueue, false);
});

test("same-class screening instances isolate files, callbacks and pending drivers", async () => {
  const { c, window } = setup();
  const sibling = new c.constructor();
  sibling.props = {};
  sibling.state.me = c.state.me;
  const pending = [];
  window.VeritasAPI.post = p => new Promise(resolve => pending.push({ p, resolve }));
  for (const instance of [c, sibling]) {
    instance.state.selectedBatch = "owned";
    instance.state.batchList = held({ batches: [batch("owned")] });
    instance.startProcessing();
  }
  assert.equal(pending.length, 2);
  assert.notEqual(c.state.files, sibling.state.files);
  assert.notEqual(c._rowHandlers, sibling._rowHandlers);
  assert.notEqual(c.moreBatches, sibling.moreBatches);
  assert.notEqual(c.renderVals().batchRows[0].open, sibling.renderVals().batchRows[0].open);
  pick(c, [{ name: "first.txt", text: "Synthetic" }]);
  assert.equal(sibling.state.files.length, 0);
  c.stopProcessing(); pending[0].resolve({ processed: 7, remaining: 0 });
  pending[1].resolve({ processed: 2, remaining: 0 }); await settle();
  assert.equal(c.state.driveDone, 0); assert.equal(sibling.state.driveDone, 2);
});
