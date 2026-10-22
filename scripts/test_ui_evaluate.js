/* Offline behavioral checks of the shipped logic and API client. Chrome remains
 * a separate gate: this executes handlers, not the template/runtime renderer. */
"use strict";
const assert = require("node:assert/strict");
const { test } = require("node:test");
const fs = require("node:fs");
const path = require("node:path");
const ROOT = path.join(__dirname, "..");
const html = fs.readFileSync(path.join(ROOT, "frontend/Veritas.dc.html"), "utf8");
const open = html.indexOf('<script type="text/x-dc"');
const start = html.indexOf(">", open) + 1;
const logic = html.slice(start, html.indexOf("</script>", start));
const operatorAccountsSource = fs.readFileSync(path.join(ROOT, "frontend/operator-accounts.js"), "utf8");
const organizationAdminSource = fs.readFileSync(path.join(ROOT, "frontend/organization-admin.js"), "utf8");
const curationSource = fs.readFileSync(path.join(ROOT, "frontend/curation.js"), "utf8");
const evaluationReportSource = fs.readFileSync(path.join(ROOT, "frontend/evaluation-report.js"), "utf8");
const screeningSource = fs.readFileSync(path.join(ROOT, "frontend/screening.js"), "utf8");
const apiSource = fs.readFileSync(path.join(ROOT, "frontend/api.js"), "utf8");
const settle = () => new Promise(resolve => setImmediate(resolve));
const report = { id: "rep_server_123", domain: "genai", verdicts: [] };

function component(kind = "org", post) {
  const calls = [];
  const window = { location: { hash: "", pathname: "/ui/", search: "" },
    history: { replaceState(_a, _b, url) { window.location.hash = url.includes("#") ? url.slice(url.indexOf("#")) : ""; } },
    scrollTo() {}, VeritasAPI: {
      base: () => "", MOCK_NOTE: "mock", onSessionLost() {},
      get: async p => { calls.push(["GET", p]); return p.endsWith("/outcomes") ? { outcomes: [] } : report; },
      post: (p, b, opts) => { calls.push(["POST", p, b, opts]); return post ? post(p, b, opts) : Promise.resolve(kind === "org" ? { report } : report); }
    } };
  class DCLogic { props = {}; setState(update, callback) { Object.assign(this.state, typeof update === "function" ? update(this.state) : update); if (callback) callback(); } }
  class Reader {
    readAsDataURL(file) { this.result = "data:application/pdf;base64," + file.payload; queueMicrotask(() => this.onload()); }
    readAsText(file) { this.result = file.text; queueMicrotask(() => this.onload()); }
  }
  new Function("window", operatorAccountsSource)(window);
  new Function("window", organizationAdminSource)(window);
  new Function("window", curationSource)(window);
  new Function("window", evaluationReportSource)(window);
  new Function("window", screeningSource)(window);
  const C = new Function("DCLogic", "window", "document", "navigator", "FileReader",
    "setTimeout", "clearTimeout", "setInterval", "clearInterval", logic + "\nreturn Component;")(
    DCLogic, window, window.document = {}, {}, Reader, setTimeout, clearTimeout, () => 0, () => {});
  const c = new C();
  Object.assign(c.state, { screen: "evaluate", me: { kind }, plane: kind === "admin" ? "operator" : kind,
    evalText: "Synthetic resume with specific work and dated experience", domain: "genai" });
  return { c, calls, window };
}

test("employer board consumes ranked candidates and nested skill coverage", () => {
  const { c } = component();
  c.state.board = { loading: false, error: null, data: { match: {
    ranked: [{ candidate_id: "subject-server-id", score: 0.75, coverage: 0.93,
      skill: { coverage: 0.5, matched: ["python"], missing_must_have: ["django"] } }],
    pool_size: 1, reason: null
  } } };
  const view = c.renderVals();
  assert.equal(view.shortlist.length, 1);
  assert.equal(view.shortlist[0].name, "subject-server-id");
  assert.equal(view.shortlist[0].score, "0.75");
  assert.equal(view.shortlist[0].cover, "coverage 0.50");
  assert.equal(view.boardEmptyPool, false);
});

test("successful empty employer pool differs from a failed read and recovers", async () => {
  const { c, window } = component();
  c.state.board = { loading: false, error: null, data: {
    match: { ranked: [], pool_size: 0, reason: "no_materialized_candidates" }
  } };
  assert.equal(c.renderVals().boardEmptyPool, true);
  assert.equal(c.renderVals().boardError, false);
  assert.equal(c.renderVals().shortlist.length, 0);
  window.VeritasAPI.get = async () => { throw { status: 503, detail: "Temporary board failure" }; };
  c.selectJob("job-owned")(); await settle();
  assert.equal(c.renderVals().boardEmptyPool, false);
  assert.equal(c.renderVals().boardError, true);
  assert.equal(c.renderVals().shortlist.length, 0);
  assert.equal(c.renderVals().boardErrorText, "Temporary board failure");
  window.VeritasAPI.get = async () => ({ match: { ranked: [
    { candidate_id: "restored-subject", score: 0.8, skill: { coverage: 0 } }
  ], pool_size: 1, reason: null } });
  c.selectJob("job-owned")(); await settle();
  assert.equal(c.renderVals().boardError, false);
  assert.equal(c.renderVals().boardEmptyPool, false);
  assert.equal(c.renderVals().shortlist[0].name, "restored-subject");
  assert.equal(c.renderVals().shortlist[0].cover, "coverage 0.00");
  c.state.board = { loading: false, data: null, error: { kind: "unprocessable", detail: "Invalid board request" } };
  assert.equal(c.renderVals().boardError, true);
  assert.equal(c.renderVals().boardEmptyPool, false);
  c.state.board.error = { kind: "consent" };
  assert.equal(c.renderVals().boardConsentBlocked, true);
  assert.equal(c.renderVals().boardError, false);
});

test("organisation submits once to its own plane and opens the saved server report", async () => {
  let resolve;
  const { c, calls, window } = component("org", () => new Promise(r => { resolve = r; }));
  c.runEvaluate(); c.runEvaluate();
  await settle();
  assert.equal(calls.filter(x => x[0] === "POST").length, 1);
  assert.equal(calls[0][1], "/screening/candidates");
  assert.equal(calls[0][2].resume_text, c.state.evalText);
  assert.equal(calls[0][2].domain, "genai");
  assert.equal(calls[0][2].evaluate, true);
  assert.equal(c.renderVals().evalRunning, true);
  resolve({ report }); await settle();
  assert.equal(c.state.screen, "report");
  assert.deepEqual(c.state.report.data, report);
  assert(calls.some(x => x[1] === "/screening/reports/" + report.id));
  assert(window.location.hash.includes(report.id));
  assert.equal(c.renderVals().isMockScreen, false);
});

test("operator PDF uses ad-hoc and admin report/outcome routes", async () => {
  const { c, calls } = component("admin");
  c.state.evalText = "";
  c.state.evalFile = { name: "resume.pdf", payload: "JVBERi0=" };
  c.state.domain = "data_eng";
  c.runEvaluate(); await settle(); await settle();
  assert.equal(calls[0][1], "/evaluate");
  assert.equal(calls[0][2].resume_pdf_b64, "JVBERi0=");
  assert.equal(calls[0][2].domain, "data_eng");
  assert(calls.some(x => x[1] === "/report/" + report.id));
  c.recordOutcome("verified_genuine")(); await settle();
  assert(calls.some(x => x[0] === "POST" && x[1] === "/report/" + report.id + "/outcome"));
});

test("empty input and candidate plane do not submit", async () => {
  for (const kind of ["org", "candidate"]) {
    const { c, calls } = component(kind);
    if (kind === "org") c.state.evalText = " \n ";
    c.runEvaluate(); await settle();
    assert.equal(calls.length, 0);
    assert.equal(c.renderVals().evalRunning, false);
    assert(c.renderVals().evalErrorText);
  }
});

for (const err of [{ status: 422, detail: "resume_pdf_unreadable", kind: "unprocessable" },
    { status: 403, detail: "missing or invalid CSRF token", kind: "csrf" },
    { status: 403, detail: "operation refused", kind: "consent" },
    { status: 503, detail: "Service unavailable", kind: "http" },
    { status: 0, detail: "Request timed out. The server may have saved this run.", kind: "timeout" },
    { status: 0, detail: "Connection lost", kind: "network" }]) {
  test("failure settles and manual retry retains input: " + err.kind + "/" + err.status, async () => {
    let fail = true;
    const { c, calls } = component("org", () => fail ? Promise.reject(err) : Promise.resolve({ report }));
    const input = c.state.evalText;
    c.runEvaluate(); await settle();
    assert.equal(c.renderVals().evalRunning, false);
    assert.equal(c.state.screen, "evaluate");
    assert.equal(c.state.evalText, input);
    assert(c.renderVals().evalErrorText);
    fail = false; c.runEvaluate(); await settle();
    assert.equal(c.state.report.data.id, report.id);
    assert.equal(calls.filter(x => x[0] === "POST").length, 2);
  });
}

test("late completion after navigation stays available without switching screens", async () => {
  let resolve;
  const { c } = component("org", () => new Promise(r => { resolve = r; }));
  c.runEvaluate(); await settle(); c.nav("devices")();
  resolve({ report }); await settle();
  assert.equal(c.state.screen, "devices");
  assert.equal(c.state.evalReportId, report.id);
  c.goEvaluate(); c.viewEvaluation(); await settle();
  assert.equal(c.state.report.data.id, report.id);
});

test("session loss discards sensitive input and ignores late evaluation/report responses", async () => {
  let resolve;
  const { c, window } = component("org", () => new Promise(r => { resolve = r; }));
  c.runEvaluate(); await settle(); c.handleSessionLost();
  resolve({ report }); await settle();
  assert.equal(c.state.screen, "login");
  assert.equal(c.state.evalText, "");
  assert.equal(c.state.evalReportId, null);
  assert.equal(c.renderVals().evalRunning, false);
  assert.equal(window.location.hash, "");
});

test("authorized reload reads URL report without resubmitting; session loss prevents late reads", async () => {
  const { c, window, calls } = component("org");
  const me = c.state.me;
  window.location.hash = "#report=" + report.id + "&from=evaluate";
  window.VeritasAPI.get = async p => { calls.push(["GET", p]); return p === "/auth/me" ? me : p.endsWith("outcomes") ? { outcomes: [] } : report; };
  c.componentDidMount(); await settle();
  assert.equal(c.state.report.data.id, report.id);
  assert.equal(c.state.reportOrigin, "evaluate");
  assert.equal(calls.filter(x => x[0] === "POST").length, 0);
  const resolvers = [];
  window.VeritasAPI.get = () => new Promise(r => { resolvers.push(r); });
  c.openReport(report.id, "evaluate")(); c.handleSessionLost();
  resolvers[0](report); resolvers[1]([report]); await settle();
  assert.equal(c.state.report.data, null);
  assert.equal(c.state.outcomes.data, null);
});

test("PDF selection replaces text; text editing clears the selected PDF", () => {
  const { c } = component("org");
  const file = { name: "synthetic.pdf", payload: "JVBERi0=" };
  c.pickEvalFile({ target: { files: [file], value: "file" } });
  assert.equal(c.state.evalText, "");
  assert.equal(c.state.evalFile, file);
  c.setEvalText({ target: { value: "New pasted resume" } });
  assert.equal(c.state.evalFile, null);
  assert.equal(c.state.evalText, "New pasted resume");
});

test("unmounted evaluation never changes state when a response lands", async () => {
  let resolve;
  const { c } = component("org", () => new Promise(r => { resolve = r; }));
  c.runEvaluate(); await settle(); c.componentWillUnmount();
  resolve({ report }); await settle();
  assert.equal(c.state.evalReportId, null);
  assert.equal(c.state.screen, "evaluate");
});

test("signout clears Instant check immediately while logout HTTP is pending", async () => {
  let finishLogout;
  const { c } = component("org", p => new Promise(resolve => { if (p === "/auth/logout") finishLogout = resolve; }));
  c.runEvaluate(); await settle(); c.signOut();
  assert.equal(c.state.screen, "login");
  assert.equal(c.state.evalText, "");
  assert.equal(c.state.evalBusy, false);
  assert.equal(c.state.report.data, null);
  c.setState({ me: { kind: "admin" }, screen: "adminorgs" });
  finishLogout({ logged_out: true }); await settle();
  assert.equal(c.state.screen, "adminorgs");
  assert.equal(c.state.me.kind, "admin");
});

test("a successful response without a report ID does not fabricate success", async () => {
  const { c } = component("org", async () => ({}));
  c.runEvaluate(); await settle();
  assert.equal(c.state.screen, "evaluate");
  assert(c.renderVals().evalErrorText);
  assert.equal(c.renderVals().evalRunning, false);
});

test("a report read failure allows read-only retry without another upload", async () => {
  const { c, calls, window } = component("org");
  let fail = true;
  window.VeritasAPI.get = async p => { calls.push(["GET", p]); if (fail) throw { status: 404, detail: "report not found" }; return p.endsWith("outcomes") ? { outcomes: [] } : report; };
  c.runEvaluate(); await settle();
  assert.equal(c.state.report.error.status, 404);
  fail = false; c.retryReport(); await settle();
  assert.equal(c.state.report.data.id, report.id);
  assert.equal(calls.filter(x => x[0] === "POST").length, 1);
});

test("API timeout covers body reading, keeps credentials/CSRF, and clears its timer", async () => {
  const window = { location: { search: "" }, localStorage: { getItem: () => null },
    document: { cookie: "dee_csrf=synthetic-token" } };
  let init, aborted = false;
  window.fetch = async (_p, i) => {
    init = i;
    return { ok: true, headers: { get: () => "application/json" }, json: () => new Promise((_r, reject) => {
      i.signal.addEventListener("abort", () => { aborted = true; reject(new Error("aborted")); });
    }) };
  };
  new Function("window", apiSource)(window);
  await assert.rejects(window.VeritasAPI.post("/evaluate", {}, { timeoutMs: 15 }), e => e.kind === "timeout");
  assert.equal(aborted, true);
  assert.equal(init.credentials, "include");
  assert.equal(init.headers["X-CSRF-Token"], "synthetic-token");
});

test("API success cancels the deadline; 401 invokes session loss once without retry", async () => {
  let signal, requests = 0, lost = 0;
  const window = { location: { search: "" }, localStorage: { getItem: () => null },
    document: { cookie: "" }, fetch: async (_p, init) => {
      signal = init.signal; requests++;
      return { ok: requests === 1, status: requests === 1 ? 200 : 401,
        headers: { get: () => "application/json" }, json: async () => requests === 1 ? report : { detail: "expired" } };
    } };
  new Function("window", apiSource)(window);
  window.VeritasAPI.onSessionLost(() => { lost++; });
  assert.deepEqual(await window.VeritasAPI.post("/evaluate", {}, { timeoutMs: 10 }), report);
  await new Promise(r => setTimeout(r, 20));
  assert.equal(signal.aborted, false);
  await assert.rejects(window.VeritasAPI.post("/evaluate", {}, { timeoutMs: 10 }), e => e.kind === "session_lost");
  assert.equal(lost, 1); assert.equal(requests, 2);
});

test("feedback deadline settles stalled HTTP and retains reviewer notes", async () => {
  const { c, window } = component("org");
  c.openReport(report.id)(); await settle();
  c.state.outcomeNotes = "Synthetic reviewer clarification";
  const capturedAPI = window.VeritasAPI;
  window.document.cookie = "dee_csrf=synthetic-token";
  let rejectTransport;
  window.fetch = (_path, init) => new Promise((_resolve, reject) => {
    rejectTransport = reject;
    if (init.signal) init.signal.addEventListener("abort", () => reject(new Error("synthetic stall")));
  });
  new Function("window", apiSource)(window);
  const realPost = window.VeritasAPI.post;
  capturedAPI.post = (p, b, opts) => realPost(p, b, opts ? { timeoutMs: 15 } : undefined);
  c.recordOutcome("verified_genuine")();
  try {
    await new Promise(resolve => setTimeout(resolve, 40));
    assert.equal(c.state.outcomeBusy, null, "a stalled feedback mutation must settle");
    assert.equal(c.state.outcomeNotes, "Synthetic reviewer clarification");
    assert.equal(c.state.outcomeError.kind, "timeout");
    assert.match(c.renderVals().outcomeErrorText, /reload.*before recording again/i);
  } finally { rejectTransport(new Error("synthetic cleanup")); await settle(); }
});

test("late feedback cannot clear notes or block recording in a new account", async () => {
  let oldResolve, newResolve;
  const { c, window, calls } = component("org", () => new Promise(resolve => { oldResolve = resolve; }));
  c.openReport(report.id)(); await settle();
  c.recordOutcome("verified_genuine")();
  c.handleSessionLost();
  c.setState({ me: { kind: "admin" }, screen: "evaluate" });
  c.openReport(report.id)(); await settle();
  c.state.outcomeNotes = "New operator notes";
  window.VeritasAPI.post = () => new Promise(resolve => { newResolve = resolve; });
  c.recordOutcome("inconclusive")();
  assert.equal(typeof newResolve, "function", "old HTTP must not block the new account");
  oldResolve({}); await settle();
  assert.equal(c.state.outcomeNotes, "New operator notes", "old feedback must not mutate a new account");
  assert.equal(c.state.outcomeBusy, "inconclusive", "old feedback must not release a newer request");
  const reads = calls.filter(call => call[0] === "GET").length;
  newResolve({}); await settle();
  assert.equal(c.state.outcomeBusy, null);
  assert.equal(c.state.outcomeNotes, "");
  assert.equal(calls.filter(call => call[0] === "GET").length, reads + 1);
});

test("late 401 from a replaced session cannot sign out the new account", async () => {
  let resolve, lost = 0;
  const window = { location: { search: "" }, localStorage: { getItem: () => null },
    document: { cookie: "dee_csrf=old-synthetic-session" },
    fetch: () => new Promise(r => { resolve = r; }) };
  new Function("window", apiSource)(window);
  window.VeritasAPI.onSessionLost(() => { lost++; });
  const pending = window.VeritasAPI.get("/portal/me");
  window.document.cookie = "dee_csrf=new-synthetic-session";
  const expired = { ok: false, status: 401, headers: { get: () => "application/json" },
    json: async () => ({ detail: "expired" }) };
  resolve(expired);
  await assert.rejects(pending, e => e.kind === "session_lost");
  assert.equal(lost, 0, "old HTTP must not sign out a newly established session");
  window.fetch = async () => expired;
  const current = window.VeritasAPI.get("/portal/me");
  window.document.cookie = ""; // Cookie expiry during the current request must still clear the UI.
  await assert.rejects(current, e => e.kind === "session_lost");
  assert.equal(lost, 1);
});

test("detached evaluation and feedback callbacks retain receiver and separate factory state", async () => {
  const first = component(), second = component();
  const view = first.c.renderVals();
  assert.notEqual(view.runEvaluate, second.c.renderVals().runEvaluate);
  view.setEvalText({ target: { value: "Detached synthetic resume" } });
  view.setEvalGithub({ target: { value: "https://github.com/synthetic" } });
  await view.runEvaluate(); await settle();
  assert.equal(first.calls.find(row => row[0] === "POST")[2].resume_text, "Detached synthetic resume");
  assert.equal(first.c.state.evalReportId, report.id);
  assert.equal(second.c.state.evalReportId, null);
  assert.equal(second.calls.length, 0);
  assert.equal(first.c.renderVals().runEvaluate, view.runEvaluate);
  const reportView = first.c.renderVals();
  reportView.setOutcomeNotes({ target: { value: "Detached human review" } });
  reportView.outcomeButtons[0].record(); reportView.outcomeButtons[0].record(); await settle();
  const writes = first.calls.filter(row => row[0] === "POST" && row[1].endsWith("/outcome"));
  assert.equal(writes.length, 1);
  assert.equal(writes[0][2].notes, "Detached human review");
  assert.equal(second.c.state.outcomeNotes, "");
  assert.equal(first.c.renderVals().outcomeButtons[0].record, reportView.outcomeButtons[0].record);
});

test("same-class instances isolate pending evaluations and cached feedback callbacks", async () => {
  const { c, window } = component();
  const sibling = new c.constructor();
  Object.assign(sibling.state, { screen: "evaluate", plane: "org", me: { kind: "org" },
    evalText: "Sibling synthetic resume" });
  const pending = [];
  window.VeritasAPI.post = (_path, body) => new Promise(resolve => { pending.push({ body, resolve }); });
  window.VeritasAPI.get = async path => path.endsWith("/outcomes") ? { outcomes: [] }
    : { ...report, id: decodeURIComponent(path.split("/").at(-1)) };
  const firstRun = c.runEvaluate(), siblingRun = sibling.runEvaluate();
  assert.equal(pending.length, 2); assert.notEqual(c._evaluating, sibling._evaluating);
  c.handleSessionLost();
  c.setState({ me: { kind: "admin" }, screen: "evaluate", evalText: "New account draft" });
  pending[0].resolve({ report: { ...report, id: "stale-report" } }); await firstRun;
  assert.equal(c.state.evalReportId, null); assert.equal(c.state.evalText, "New account draft");
  assert.equal(sibling.state.evalBusy, true);
  pending[1].resolve({ report: { ...report, id: "sibling-report" } }); await siblingRun; await settle();
  assert.equal(sibling.state.report.data.id, "sibling-report");
  c.openReport("operator-report")(); await settle();
  const firstView = c.renderVals(), siblingView = sibling.renderVals();
  assert.notEqual(firstView.outcomeButtons[0].record, siblingView.outcomeButtons[0].record);
  assert.notEqual(c._outcomeHandlers, sibling._outcomeHandlers);
  assert.notEqual(c._copyHandlers, sibling._copyHandlers);
  firstView.setOutcomeNotes({ target: { value: "First human notes" } });
  siblingView.setOutcomeNotes({ target: { value: "Sibling human notes" } });
  firstView.outcomeButtons[0].record(); siblingView.outcomeButtons[0].record();
  c.handleSessionLost(); c.state.outcomeNotes = "New session notes";
  pending[2].resolve({}); await settle();
  assert.equal(c.state.outcomeNotes, "New session notes"); assert(sibling.state.outcomeBusy);
  assert.equal(sibling.state.outcomeNotes, "Sibling human notes");
  pending[3].resolve({}); await settle();
  assert.equal(sibling.state.outcomeBusy, null); assert.equal(sibling.state.outcomeNotes, "");
  assert.equal(c.state.outcomeNotes, "New session notes");
});

test("report values retain advisory versions, withheld identities and cached probe state", () => {
  const { c } = component();
  const saved = { ...report, summary: "Stored assessment wording", depth_band: "deep", depth_score: 0.8,
    candidate_context: { full_name: "Synthetic Reviewer" },
    fabrication_risk: { scorer_version: 2, band: "low", score: 0.1, confidence: 0.9, components: [] },
    ai_generation: { band: "likely", signals: [{ source: "llm", detail: "Synthetic opinion" }] },
    resume_farm: { corpus_size: 2, matches: [{ similarity: 0.5, candidate_id: "private-subject", resume_id: "private-resume" }] },
    verdicts: [{ claim_text: "Dated contribution", status: "supported", claim_type: "experience",
      coherence_score: 0.8, confidence: 0.8, probes: ["Clarify contribution"] }] };
  c.state.report = { data: saved, loading: false, error: null };
  const view = c.renderVals();
  assert.match(view.reportVersionNote, /writing style is excluded/);
  assert.match(view.reportRiskExplanation, /not the probability of dishonesty/);
  assert.match(view.reportStyleSignals[0], /unverified/);
  assert.equal(view.reportScore, "0.10");
  assert(!JSON.stringify(view.reportFarmMatches).includes("private-"));
  assert.match(view.reportFarmLine, /Match identities are withheld/);
  assert.equal(c.renderVals().reportVerdicts[0].copy, view.reportVerdicts[0].copy);
  view.reportVerdicts[0].copy();
  assert.equal(c.renderVals().reportVerdicts[0].copyLabel, "Copied");
  c.componentWillUnmount(); // Release the existing copy-notice timer.
  saved.fabrication_risk = { ...saved.fabrication_risk, scorer_version: 1, score: 0.72 };
  assert.match(c.renderVals().reportVersionNote, /Historical assessment/);
  assert.equal(c.renderVals().reportScore, "0.72");
  assert.equal(c.renderVals().reportSummary, "Stored assessment wording");
  saved.fabrication_risk.scorer_version = 99;
  assert.equal(c.renderVals().reportBandLabel, "Unsupported version");
  assert.equal(c.renderVals().reportIndexLabel, "Review index unavailable");
  saved.fabrication_risk = null;
  assert.equal(c.renderVals().reportScore, "—");
  assert.match(c.renderVals().reportVersionNote, /No factual review assessment/);
});

module.exports = { component, settle };
