"use strict";
const assert = require("node:assert/strict");
const { test } = require("node:test");
const { component, settle } = require("./test_ui_evaluate");
const question = { id: "q_saved", text: "Describe the work you did and why.", sequence: 1, source: "profile" };
const saved = { id: "iv_saved", status: "in_progress", domain: "genai", questions: [question], turns: [],
  started_at: "2026-10-15T10:00:00Z", expires_at: "2026-10-15T11:00:00Z", assessment: null };
function fixture(post) {
  const f = component("candidate", post || (async () => ({ session: saved, next_question: question })));
  f.c.state.screen = "interview";
  f.window.VeritasAPI.get = async p => { f.calls.push(["GET", p]); return p === "/portal/interviews"
    ? { interviews: [{ ...saved, questions_planned: 1, questions_answered: 0 }] } : { session: saved, next_question: question }; };
  return f;
}
test("interview entry reads saved candidate sessions and resumes the server question", async () => {
  const { c, calls } = fixture();
  c.loadForScreen("interview"); await settle(); await settle();
  assert(calls.some(x => x[1] === "/portal/interviews"), "entry must list saved interviews");
  assert.equal(c.renderVals().interviewQuestion, question.text);
  assert.equal(c.state.interviewBody.session.id, saved.id);
  assert.equal(c.renderVals().isMockScreen, false);
});
module.exports = { fixture, saved, question };

const score = { insufficient: true, codes: ["insufficient_answer"], scorer_version: "s73.2" };
const assessment = { band: "insufficient_signal", overall: 0, confidence: 0, coverage: 1, scorer_version: "s73.2" };
const completed = { ...saved, status: "completed", turns: [{ id: "t_saved", question_id: question.id,
  question_text: question.text, transcript: "A brief saved answer.", score }], assessment };
async function loaded(post) { const f = fixture(post); await f.c.refreshInterviews(); return f; }

test("empty history starts once with selected domain and loads the saved session", async () => {
  let resolve, started = false;
  const { c, calls, window } = fixture(() => new Promise(r => { resolve = r; }));
  window.VeritasAPI.get = async p => p === "/portal/interviews" ? { interviews: started ? [saved] : [] } : { session: saved, next_question: question };
  await c.refreshInterviews();
  assert.equal(c.renderVals().interviewEmpty, true);
  c.setDataEng();
  c.startInterview(); c.startInterview(); await settle();
  assert.equal(calls.length, 1);
  assert.deepEqual(calls[0].slice(1, 3), ["/portal/interviews", { domain: "data_eng" }]);
  assert(calls[0][3].timeoutMs > 0);
  started = true; resolve({ session: saved, next_question: question }); await settle();
  assert.equal(c.state.interviewBody.session.id, saved.id);
  assert.equal(c.state.interviewBusy, false);
});

test("typed answer sends the loaded question once and displays only saved completion", async () => {
  let resolve;
  const { c, calls, window } = await loaded(() => new Promise(r => { resolve = r; }));
  c.setInterviewDraft({ target: { value: "My actual answer" } });
  c.submitInterviewAnswer(); c.submitInterviewAnswer(); await settle();
  assert.equal(calls.filter(x => x[0] === "POST").length, 1);
  assert.deepEqual(calls.at(-1).slice(1, 3), ["/portal/interviews/iv_saved/answers", { question_id: question.id, text: "My actual answer" }]);
  assert.equal(c.renderVals().interviewHasAssessment, false);
  window.VeritasAPI.get = async p => p === "/portal/interviews" ? { interviews: [completed] } : { session: completed, next_question: null };
  resolve({ session: completed, next_question: null }); await settle();
  assert.equal(c.state.interviewDraft, "");
  assert.equal(c.renderVals().interviewHasAssessment, true);
  assert.equal(c.renderVals().interviewActive, false);
  assert(c.renderVals().interviewAssessmentText.includes("No ability conclusion"));
  assert.equal(c.renderVals().interviewTurns[0].transcript, completed.turns[0].transcript);
});

for (const error of [{ status: 409 }, { status: 404 }, { status: 422 }, { status: 503 },
    { kind: "csrf", status: 403 }, { kind: "timeout" }, { kind: "network" }]) {
  test("failed write requires successful read before another submission: " + JSON.stringify(error), async () => {
    const { c, calls, window } = await loaded(async () => { throw error; });
    c.setInterviewDraft({ target: { value: "Keep this uncertain draft" } });
    await c.submitInterviewAnswer();
    assert.equal(c.state.interviewBusy, false);
    assert.equal(c.state.interviewNeedsRefresh, true);
    assert.equal(c.state.interviewDraft, "Keep this uncertain draft");
    assert(c.renderVals().interviewErrorText);
    await c.submitInterviewAnswer();
    assert.equal(calls.filter(x => x[0] === "POST").length, 1);
    window.VeritasAPI.get = async () => { throw { kind: "network" }; };
    await c.refreshInterviews();
    assert.equal(c.state.interviewDraft, "Keep this uncertain draft");
    assert.equal(c.renderVals().interviewWriteDisabled, true);
    window.VeritasAPI.get = async p => p === "/portal/interviews" ? { interviews: [saved] } : { session: saved, next_question: question };
    await c.refreshInterviews();
    assert.equal(c.state.interviewNeedsRefresh, false);
    assert.equal(c.state.interviewDraft, "");
    assert.equal(calls.filter(x => x[0] === "POST").length, 1, "refresh never replays an answer");
  });
}

test("blank and oversize answers never post; early finish requires explicit confirmation", async () => {
  const { c, calls } = await loaded();
  for (const text of [" \n ", "x".repeat(20001)]) { c.state.interviewDraft = text; await c.submitInterviewAnswer(); }
  await c.finishInterview();
  assert.equal(calls.filter(x => x[0] === "POST").length, 0);
  c.state.interviewDraft = "unsent";
  c.armInterviewFinish(); await c.finishInterview();
  assert.equal(calls.find(x => x[0] === "POST")[1], "/portal/interviews/iv_saved/finish");
});

test("expired reads keep saved answers and cannot submit or finish", async () => {
  const { c, calls, window } = fixture();
  window.VeritasAPI.get = async p => p === "/portal/interviews" ? { interviews: [{ ...saved, status: "abandoned" }] }
    : { session: { ...saved, status: "abandoned" }, next_question: null };
  await c.refreshInterviews();
  assert.equal(c.renderVals().interviewExpired, true);
  assert(c.renderVals().interviewStatus.includes("Expired"));
  c.state.interviewDraft = "stale"; c.armInterviewFinish(); await c.finishInterview(); await c.submitInterviewAnswer();
  assert.equal(calls.filter(x => x[0] === "POST").length, 0);
});

for (const leave of [c => c.nav("portal")(), c => c.handleSessionLost(), c => c.componentWillUnmount()]) {
  test("late writes cannot restore interview data after navigation/session loss/unmount: " + leave.toString(), async () => {
    let resolve;
    const { c } = await loaded(() => new Promise(r => { resolve = r; }));
    c.state.interviewDraft = "private unsent text"; c.submitInterviewAnswer(); await settle();
    leave(c); await settle(); const snapshot = JSON.stringify(c.state);
    resolve({ session: completed, next_question: null }); await settle();
    assert.equal(JSON.stringify(c.state), snapshot);
    if (!c._gone) { assert.equal(c.state.interviewDraft, ""); assert.equal(c.state.interviewBody, null); }
  });
}

test("late reads are ignored after navigation and a newer refresh wins", async () => {
  let resolve;
  const { c, window } = fixture();
  window.VeritasAPI.get = () => new Promise(r => { resolve = r; });
  c.refreshInterviews(); await settle(); c.nav("devices")(); resolve({ interviews: [saved] }); await settle();
  assert.equal(c.state.interviewBody, null);
  c.state.screen = "interview";
  c.refreshInterviews(); await settle(); const first = resolve;
  c.refreshInterviews(); await settle(); resolve({ interviews: [] }); await settle();
  first({ interviews: [saved] }); await settle();
  assert.deepEqual(c.state.interviewList.data, []);
});

test("wrong plane and malformed or mismatched replies cannot display a saved success", async () => {
  for (const kind of ["org", "admin"]) {
    const { c, calls } = fixture(); c.state.me = { kind };
    await c.refreshInterviews(); await c.startInterview();
    assert.equal(calls.length, 0); assert.equal(c.renderVals().interviewDenied, true);
  }
  for (const result of [{}, { session: { ...saved, id: "foreign" }, next_question: question },
      { session: saved, next_question: { ...question, id: "future" } },
      { session: { ...completed, assessment: { ...assessment, overall: "1" } }, next_question: null }]) {
    const { c } = await loaded(async () => result);
    c.state.interviewDraft = "valid text"; await c.submitInterviewAnswer();
    assert.equal(c.state.interviewNeedsRefresh, true);
    assert.equal(c.state.interviewBody.session.status, "in_progress");
  }
});

test("saved versions and evidence warnings distinguish history, mixed, limited and unconfirmed", async () => {
  const { c } = await loaded();
  for (const [version, expected] of [["s73.1", "Historical v1"], ["s73.2", "English"], ["mixed/unknown", "No confident blend"], ["", "unknown"]]) {
    c.state.interviewBody = { session: { ...completed, assessment: { ...assessment, scorer_version: version },
      turns: [{ ...completed.turns[0], score: { ...score, codes: ["limited_content", "relevance_unconfirmed", "ownership_unknown", "depth_unknown"] } }] }, next_question: null };
    assert(c.renderVals().interviewVersionText.includes(expected));
    assert(c.renderVals().interviewEvidenceText.includes("not poor ability"));
    assert(c.renderVals().interviewTurns[0].evidence.includes("Relevance unconfirmed"));
    assert(c.renderVals().interviewTurns[0].evidence.includes("Limited content"));
  }
});

test("an unknown saved rubric cannot advertise a confident band or comparable index", async () => {
  const { c } = await loaded();
  c.state.interviewBody = { next_question: null, session: { ...completed,
    assessment: { ...assessment, scorer_version: "future/unknown", band: "deep", confidence: .9, overall: .99 } } };
  assert(!c.renderVals().interviewAssessmentText.includes("Saved index"));
  assert(!c.renderVals().interviewAssessmentText.includes("deep"));
  assert(c.renderVals().interviewAssessmentText.includes("No ability conclusion"));
});
