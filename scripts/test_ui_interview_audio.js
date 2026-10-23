"use strict";
const assert = require("node:assert/strict");
const { test } = require("node:test");
const { fixture, saved, question } = require("./test_ui_interview");
const { settle } = require("./test_ui_evaluate");

async function audioFixture(post) {
  const f = fixture(post);
  const timers = new Map(), tracks = [], recorders = [], permissions = [];
  let timerId = 0;
  f.window.Blob = Blob;
  f.window.setTimeout = (fn, ms) => { const id = ++timerId; timers.set(id, { fn, ms }); return id; };
  f.window.clearTimeout = id => timers.delete(id);
  f.window.setInterval = f.window.setTimeout;
  f.window.clearInterval = f.window.clearTimeout;
  f.window.navigator = { mediaDevices: { getUserMedia: async constraints => {
    permissions.push(constraints);
    const track = { readyState: "live", stops: 0, stop() { this.readyState = "ended"; this.stops++; }, onended: null };
    tracks.push(track); return { getTracks: () => [track] };
  } } };
  f.window.MediaRecorder = class {
    static isTypeSupported = mime => mime.startsWith("audio/webm");
    constructor(stream, opts) { this.stream = stream; this.mimeType = opts.mimeType; this.state = "inactive"; recorders.push(this); }
    start() { this.state = "recording"; }
    stop() { this.state = "inactive"; queueMicrotask(() => {
      this.ondataavailable?.({ data: new Blob(["synthetic encoded audio"], { type: this.mimeType }) }); this.onstop?.();
    }); }
  };
  f.window.FileReader = class {
    readAsDataURL(blob) { blob.arrayBuffer().then(b => { this.result = "data:" + blob.type + ";base64," + Buffer.from(b).toString("base64"); this.onload?.(); }); }
    abort() { this.onabort?.(); }
  };
  await f.c.refreshInterviews();
  return { ...f, tracks, recorders, permissions, timers, fire: ms => {
    const item = [...timers].find(([, t]) => t.ms === ms); assert(item, "missing timer " + ms);
    timers.delete(item[0]); item[1].fn();
  } };
}

test("an explicit voice recording action requests only microphone input", async () => {
  const { c, permissions } = await audioFixture();
  assert.equal(permissions.length, 0);
  c.selectInterviewAudio?.(); c.renderVals().startInterviewRecording?.(); await settle();
  assert.equal(permissions.length, 1, "candidate action must request a real microphone stream");
  assert.deepEqual(permissions[0], { audio: true, video: false });
});
module.exports = { audioFixture };

async function record(f) {
  f.c.selectInterviewAudio(); await f.c.startInterviewRecording();
  f.c.stopInterviewRecording(); await settle();
  assert.equal(f.c.state.interviewAudioStatus, "ready");
}
test("record/stop sends nothing; explicit submit encodes the bound question once and releases media", async () => {
  let resolve;
  const f = await audioFixture(() => new Promise(r => { resolve = r; }));
  f.c.state.interviewDraft = "typed fallback draft";
  f.c.selectInterviewAudio(); f.c.startInterviewRecording(); f.c.startInterviewRecording(); await settle();
  assert.equal(f.permissions.length, 1);
  assert.equal(f.c.renderVals().interviewAudioStatus, "recording");
  f.c.stopInterviewRecording(); await settle();
  assert(f.tracks.every(t => t.readyState === "ended"));
  assert.equal(f.c.state.interviewDraft, "typed fallback draft");
  assert.equal(f.calls.filter(x => x[0] === "POST").length, 0);
  f.c.submitInterviewAnswer(); f.c.submitInterviewAnswer(); await settle();
  const writes = f.calls.filter(x => x[0] === "POST");
  assert.equal(writes.length, 1);
  assert.deepEqual(writes[0][2], { question_id: question.id,
    audio_b64: Buffer.from("synthetic encoded audio").toString("base64"), mime: "audio/webm;codecs=opus" });
  assert.equal(f.c._interviewAudio, null);
  assert.equal(f.c._interviewReader, null);
  resolve({ session: saved, next_question: question }); await settle();
  assert.equal(f.c.state.interviewAnswerMode, "text");
  assert.equal(f.c.state.interviewDraft, "");
});

for (const name of ["NotAllowedError", "NotFoundError", "NotReadableError"]) {
  test("permission/device failure retains typed fallback and saved question: " + name, async () => {
    const f = await audioFixture(); f.c.state.interviewDraft = "keep my draft";
    f.window.navigator.mediaDevices.getUserMedia = async () => { throw { name, message: "sensitive device details" }; };
    f.c.selectInterviewAudio(); await f.c.startInterviewRecording();
    assert.equal(f.c.state.interviewAudioStatus, "idle");
    assert(f.c.state.interviewAudioError && !f.c.state.interviewAudioError.includes("sensitive"));
    assert.equal(f.c.state.interviewNeedsRefresh, false);
    f.c.selectInterviewText();
    assert.equal(f.c.state.interviewDraft, "keep my draft");
    assert.equal(f.c.state.interviewBody.next_question.id, question.id);
    assert.equal(f.calls.filter(x => x[0] === "POST").length, 0);
  });
}

test("unsupported capture refuses before permission; recorder constructor failure releases tracks", async () => {
  const f = await audioFixture(); f.c.selectInterviewAudio();
  f.window.MediaRecorder.isTypeSupported = () => false;
  await f.c.startInterviewRecording();
  assert.equal(f.permissions.length, 0); assert(f.c.state.interviewAudioError);
  f.window.MediaRecorder = class { static isTypeSupported = () => true; constructor() { throw new Error("device detail"); } };
  await f.c.startInterviewRecording();
  assert(f.tracks.every(t => t.readyState === "ended"));
  assert.equal(f.c.state.interviewAudioStatus, "idle");
});

test("late permission after its deadline releases the device without restoring capture", async () => {
  const f = await audioFixture(); let resolve;
  f.window.navigator.mediaDevices.getUserMedia = () => new Promise(r => { resolve = r; });
  f.c.selectInterviewAudio(); f.c.startInterviewRecording(); f.fire(20000);
  assert(f.c.state.interviewAudioError.includes("timed out"));
  const track = { readyState: "live", stop() { this.readyState = "ended"; } };
  resolve({ getTracks: () => [track] }); await settle();
  assert.equal(track.readyState, "ended");
  assert.equal(f.recorders.length, 0);
  assert.equal(f.c.state.interviewAudioStatus, "idle");
});

for (const leave of [c => c.selectInterviewText(), c => c.refreshInterviews(), c => c.nav("devices")(),
    c => c.handleSessionLost(), c => c.componentWillUnmount(), c => c.clearInterview()]) {
  test("every exit discards capture and rejects late permission/recorder events: " + leave.toString(), async () => {
    const f = await audioFixture(); f.c.selectInterviewAudio(); await f.c.startInterviewRecording();
    const late = f.recorders[0].ondataavailable, stop = f.recorders[0].onstop;
    leave(f.c); await settle();
    const before = JSON.stringify(f.c.state);
    late({ data: new Blob(["late audio"]) }); stop(); await settle();
    assert.equal(JSON.stringify(f.c.state), before);
    assert(f.tracks.every(t => t.readyState === "ended")); assert.equal(f.c._interviewAudio, null);
    assert.equal(f.timers.size, 0);
  });
}

test("recording bytes, empty clips, stop deadline and duration limit never auto-submit", async () => {
  const f = await audioFixture(); f.c.selectInterviewAudio(); await f.c.startInterviewRecording();
  f.recorders[0].ondataavailable({ data: new Blob([new Uint8Array(5000001)]) });
  assert(f.c.state.interviewAudioError.includes("5 MB"));
  assert(f.tracks.every(t => t.readyState === "ended"));
  await f.c.startInterviewRecording();
  f.recorders.at(-1).stop = function() { this.state = "inactive"; queueMicrotask(() => this.onstop?.()); };
  f.c.stopInterviewRecording(); await settle();
  assert.equal(f.c.state.interviewAudioStatus, "idle"); assert(f.c.state.interviewAudioError.includes("No usable"));
  await f.c.startInterviewRecording();
  f.recorders.at(-1).stop = function() { this.state = "inactive"; };
  f.c.stopInterviewRecording(); f.fire(5000);
  assert(f.c.state.interviewAudioError.includes("could not finish"));
  await f.c.startInterviewRecording(); f.fire(120000); await settle();
  assert.equal(f.c.state.interviewAudioStatus, "ready");
  assert.equal(f.calls.filter(x => x[0] === "POST").length, 0);
});

test("recorder/device failure and discard release the device without consuming the question", async () => {
  const f = await audioFixture(); f.c.selectInterviewAudio(); await f.c.startInterviewRecording();
  f.tracks[0].onended(); await settle();
  assert(f.c.state.interviewAudioError.includes("disconnected"));
  await f.c.startInterviewRecording(); f.recorders.at(-1).onerror(); await settle();
  assert(f.c.state.interviewAudioError.includes("Recording failed"));
  await record(f); f.c.discardInterviewRecording();
  assert.equal(f.c.state.interviewAudioStatus, "idle"); assert.equal(f.c._interviewAudio, null);
  assert.equal(f.c.state.interviewBody.next_question.id, question.id);
});

test("encoding deadline/local error and navigation before encoding cannot upload", async () => {
  const f = await audioFixture(); await record(f);
  f.window.FileReader = class { readAsDataURL() {} abort() { this.onabort?.(); } };
  f.c.submitInterviewAnswer(); f.fire(20000); await settle();
  assert.equal(f.c.state.interviewBusy, false); assert.equal(f.c.state.interviewNeedsRefresh, false);
  assert(f.c.state.interviewAudioError.includes("prepared"));
  assert.equal(f.calls.filter(x => x[0] === "POST").length, 0);
  await record(f); f.c.submitInterviewAnswer(); f.c.nav("devices")(); await settle();
  assert.equal(f.c._interviewReader, null);
  assert.equal(f.calls.filter(x => x[0] === "POST").length, 0);
});

for (const detail of ["speech_failed", "speech_unavailable", "audio exceeds interview_max_audio_b64_chars"]) {
  test("server audio refusal offers read-only recovery and typed fallback without raw replay: " + detail, async () => {
    const f = await audioFixture(async () => { throw { status: 422, detail }; }); await record(f);
    await f.c.submitInterviewAnswer();
    assert.equal(f.c._interviewAudio, null); assert.equal(f.c.state.interviewNeedsRefresh, true);
    assert(f.c.renderVals().interviewErrorText.includes("Type answer"));
    await f.c.submitInterviewAnswer(); assert.equal(f.calls.filter(x => x[0] === "POST").length, 1);
    await f.c.refreshInterviews(); assert.equal(f.c.state.interviewAnswerMode, "text");
    assert.equal(f.c.state.interviewBody.next_question.id, question.id);
    assert.equal(f.calls.filter(x => x[0] === "POST").length, 1);
  });
}

test("capture blocks finish and a recorded clip cannot be rebound to another question", async () => {
  const f = await audioFixture(); f.c.selectInterviewAudio(); await f.c.startInterviewRecording();
  f.c.armInterviewFinish(); await f.c.finishInterview(); assert.equal(f.c.state.interviewConfirm, false);
  f.c.stopInterviewRecording(); await settle();
  f.c.state.interviewBody = { session: saved, next_question: { ...question, id: "other_question" } };
  await f.c.submitInterviewAnswer();
  assert.equal(f.calls.filter(x => x[0] === "POST").length, 0);
});

test("late microphone permission after actor loss stops its stream", async () => {
  const f = await audioFixture(); let resolve;
  f.window.navigator.mediaDevices.getUserMedia = () => new Promise(r => { resolve = r; });
  f.c.selectInterviewAudio(); f.c.startInterviewRecording(); f.c.handleSessionLost();
  const track = { readyState: "live", stop() { this.readyState = "ended"; } };
  resolve({ getTracks: () => [track] }); await settle();
  assert.equal(track.readyState, "ended"); assert.equal(f.c.state.interviewBody, null);
  assert.equal(f.c._interviewAudio, null);
});

test("voice HTTP timeout never replays and late completion cannot restore another actor's view", async () => {
  const f = await audioFixture(async () => { throw { kind: "timeout" }; }); await record(f);
  await f.c.submitInterviewAnswer();
  assert.equal(f.c.state.interviewNeedsRefresh, true); assert.equal(f.c._interviewAudio, null);
  await f.c.submitInterviewAnswer(); assert.equal(f.calls.filter(x => x[0] === "POST").length, 1);
  let resolve;
  const g = await audioFixture(() => new Promise(r => { resolve = r; })); await record(g);
  g.c.submitInterviewAnswer(); await settle(); g.c.handleSessionLost();
  g.c.state.me = { kind: "candidate" }; g.c.state.screen = "interview";
  resolve({ session: saved, next_question: question }); await settle();
  assert.equal(g.c.state.interviewBody, null); assert.equal(g.c._interviewAudio, null);
});

test("page exit handler clears recording and is removed on unmount", async () => {
  const f = await audioFixture(); const events = new Map();
  f.window.addEventListener = (name, callback) => events.set(name, callback);
  f.window.removeEventListener = (name, callback) => { if (events.get(name) === callback) events.delete(name); };
  f.window.VeritasAPI.get = async p => p === "/auth/me" ? f.c.state.me : { interviews: [] };
  f.c.componentDidMount(); await settle(); f.c.state.screen = "interview";
  await record(f); assert(f.c._interviewAudio);
  events.get("pagehide")();
  assert.equal(f.c._interviewAudio, null); assert.equal(f.c.state.interviewBody, null);
  assert(f.tracks.every(t => t.readyState === "ended"));
  f.c.componentWillUnmount(); assert.equal(events.has("pagehide"), false);
});

test("same-class microphone instances keep separate captures, tracks, timers and clips", async () => {
  const f = await audioFixture();
  const sibling = new f.c.constructor(); sibling.props = {};
  Object.assign(sibling.state, { me: { kind: "candidate" }, screen: "interview",
    interviewList: { loading: false, data: [saved], error: null },
    interviewBody: { session: saved, next_question: question } });
  f.c.selectInterviewAudio(); sibling.selectInterviewAudio();
  await f.c.startInterviewRecording(); await sibling.startInterviewRecording();
  assert.equal(f.tracks.length, 2); assert.equal(f.recorders.length, 2);
  assert.notEqual(f.c._interviewCapture, sibling._interviewCapture);
  assert.notEqual(f.c._interviewCapture.chunks, sibling._interviewCapture.chunks);
  const stop = sibling.renderVals().stopInterviewRecording;
  assert.equal(stop, sibling.renderVals().stopInterviewRecording);
  f.c.componentWillUnmount();
  assert.equal(f.tracks[0].readyState, "ended"); assert.equal(f.tracks[1].readyState, "live");
  assert.equal(sibling.state.interviewAudioStatus, "recording");
  stop(); await settle();
  assert.equal(sibling.state.interviewAudioStatus, "ready");
  assert.equal(sibling._interviewAudio.me, sibling.state.me);
  assert.equal(f.c._interviewAudio, null); assert.equal(f.timers.size, 0);
  const discard = sibling.renderVals().discardInterviewRecording; discard();
  assert.equal(sibling._interviewAudio, null); assert.equal(sibling.state.interviewAudioStatus, "idle");
});

test("one instance's late permission after unmount cannot cancel a sibling recording", async () => {
  const f = await audioFixture();
  let finish;
  const get = f.window.navigator.mediaDevices.getUserMedia;
  f.window.navigator.mediaDevices.getUserMedia = () => new Promise(resolve => { finish = resolve; });
  f.c.selectInterviewAudio(); const waiting = f.c.startInterviewRecording();
  const sibling = new f.c.constructor(); sibling.props = {};
  Object.assign(sibling.state, { me: { kind: "candidate" }, screen: "interview",
    interviewList: { loading: false, data: [saved], error: null },
    interviewBody: { session: saved, next_question: question } });
  f.window.navigator.mediaDevices.getUserMedia = get;
  sibling.selectInterviewAudio(); await sibling.startInterviewRecording();
  f.c.componentWillUnmount();
  const lateTrack = { readyState: "live", stop() { this.readyState = "ended"; } };
  finish({ getTracks: () => [lateTrack] }); await waiting;
  assert.equal(lateTrack.readyState, "ended"); assert.equal(f.tracks[0].readyState, "live");
  assert.equal(sibling.state.interviewAudioStatus, "recording");
  sibling.clearInterview(); assert.equal(f.tracks[0].readyState, "ended"); assert.equal(f.timers.size, 0);
});
