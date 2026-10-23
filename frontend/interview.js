/* Candidate interview text/audio handlers and view values for DCLogic.
 * Shared state, navigation and boot/session/pagehide/unmount callers stay in the component.
 */
(function (global) {
  "use strict";

  global.VeritasInterview = (Base, {
    API, EVAL_TIMEOUT_MS, IDLE, CSRF_COPY, NOTICE_BOX, fmtDateTime
  }) => class extends Base {
  clearInterview = () => {
    this.clearInterviewAudio();
    this._interviewAction = null;
    this._interviewLoad = null;
    this.setState({ interviewList: IDLE, interviewBody: null, interviewDraft: "",
      interviewBusy: false, interviewError: null, interviewNeedsRefresh: false, interviewConfirm: false,
      interviewAnswerMode: "text", interviewAudioStatus: "idle", interviewAudioError: "", interviewAudioSize: 0, interviewAudioSeconds: 0 });
  };
  stopInterviewTracks = (stream) => {
    for (const track of stream?.getTracks() || []) {
      track.onended = null;
      try { track.stop(); } catch (_err) { /* still release the other tracks */ }
    }
  };
  clearInterviewAudio = () => {
    const capture = this._interviewCapture;
    this._interviewCapture = null;
    this._interviewAudio = null;
    if (capture) {
      window.clearTimeout(capture.timer); window.clearInterval(capture.interval);
      if (capture.recorder) {
        capture.recorder.ondataavailable = capture.recorder.onstop = capture.recorder.onerror = null;
        try { if (capture.recorder.state !== "inactive") capture.recorder.stop(); } catch (_err) { /* release tracks below */ }
      }
      this.stopInterviewTracks(capture.stream);
      capture.chunks = [];
    }
    if (this._interviewReader) {
      try { this._interviewReader.abort(); } catch (_err) { /* pending read has its own deadline */ }
      this._interviewReader = null;
    }
  };
  discardInterviewRecording = () => {
    this.clearInterviewAudio();
    this.setState({ interviewAudioStatus: "idle", interviewAudioError: "", interviewAudioSeconds: 0, interviewAudioSize: 0 });
  };
  selectInterviewMode = (mode) => {
    if (this._interviewAction || this.state.interviewNeedsRefresh || this.state.interviewList.loading) return;
    this.discardInterviewRecording();
    this.setState({ interviewAnswerMode: mode, interviewConfirm: false });
  };
  selectInterviewText = () => this.selectInterviewMode("text");
  selectInterviewAudio = () => this.selectInterviewMode("audio");
  startInterviewRecording = async () => {
    const st = this.state, me = st.me, body = st.interviewBody;
    if (!this.interviewCurrent(me) || this._interviewCapture || this._interviewAction || st.interviewList.loading
      || st.interviewNeedsRefresh || st.interviewAnswerMode !== "audio" || body?.session.status !== "in_progress" || !body.next_question) return;
    this.discardInterviewRecording();
    const recorderType = window.MediaRecorder;
    const devices = window.navigator?.mediaDevices;
    const mime = ["audio/webm;codecs=opus", "audio/ogg;codecs=opus", "audio/mp4"].find(m => recorderType?.isTypeSupported?.(m));
    if (!devices?.getUserMedia || !mime) {
      this.setState({ interviewAudioError: "Microphone recording is unavailable in this browser or page. Use Type answer." }); return;
    }
    const token = this._interviewCapture = { me, sid: body.session.id, qid: body.next_question.id, chunks: [], bytes: 0 };
    const current = () => this._interviewCapture === token && this.interviewCurrent(me)
      && this.state.interviewBody?.session.id === token.sid && this.state.interviewBody?.next_question?.id === token.qid;
    const fail = message => {
      if (!current()) return;
      this.clearInterviewAudio();
      this.setState({ interviewAudioStatus: "idle", interviewAudioSize: 0, interviewAudioError: message });
    };
    token.fail = fail;
    this.setState({ interviewAudioStatus: "requesting", interviewAudioError: "" });
    token.timer = window.setTimeout(() => fail("Microphone permission timed out. You can record again or use Type answer."), 20000);
    try {
      const stream = await devices.getUserMedia({ audio: true, video: false });
      if (!current()) { this.stopInterviewTracks(stream); return; }
      window.clearTimeout(token.timer);
      token.stream = stream;
      if (!stream.getTracks().length || stream.getTracks().some(t => t.readyState === "ended")) {
        fail("The microphone is disconnected. Record again or use Type answer."); return;
      }
      const recorder = token.recorder = new recorderType(stream, { mimeType: mime, audioBitsPerSecond: 64000 });
      token.mime = recorder.mimeType || mime;
      if (!["audio/webm", "audio/ogg", "audio/mp4"].includes(token.mime.split(";")[0].toLowerCase())) {
        fail("This recording format is unsupported. Use Type answer."); return;
      }
      recorder.ondataavailable = event => {
        if (!current() || !event.data?.size) return;
        token.bytes += event.data.size;
        if (token.bytes > 5000000) { fail("Recording exceeded 5 MB and was discarded. Record a shorter answer or type it."); return; }
        token.chunks.push(event.data);
      };
      recorder.onerror = () => fail("Recording failed. Record again or use Type answer.");
      recorder.onstop = () => {
        if (!current()) return;
        if (this.state.interviewAudioStatus !== "stopping") { fail("Recording ended unexpectedly. Record again or use Type answer."); return; }
        const blob = new window.Blob(token.chunks, { type: token.mime });
        const clip = { blob, mime: token.mime, me, sid: token.sid, qid: token.qid };
        this.clearInterviewAudio();
        if (!blob.size || blob.size > 5000000) {
          this.setState({ interviewAudioStatus: "idle", interviewAudioError: "No usable recording was captured. Record again or type your answer." }); return;
        }
        this._interviewAudio = clip;
        this.setState({ interviewAudioStatus: "ready", interviewAudioSize: blob.size });
      };
      for (const track of stream.getTracks()) track.onended = () => {
        if (this.state.interviewAudioStatus !== "stopping") fail("The microphone disconnected. Record again or use Type answer.");
      };
      recorder.start(500);
      token.started = Date.now();
      this.setState({ interviewAudioStatus: "recording" });
      token.interval = window.setInterval(() => {
        if (current()) this.setState({ interviewAudioSeconds: Math.floor((Date.now() - token.started) / 1000) });
      }, 1000);
      token.timer = window.setTimeout(() => { if (current()) this.stopInterviewRecording(); }, 120000);
    } catch (err) {
      fail(err?.name === "NotAllowedError" || err?.name === "SecurityError"
        ? "Microphone permission was denied. Allow it in your browser or use Type answer."
        : "Could not open the microphone. Check your device or use Type answer.");
    }
  };
  stopInterviewRecording = () => {
    const token = this._interviewCapture;
    if (!token?.recorder || this.state.interviewAudioStatus !== "recording") return;
    this.setState({ interviewAudioStatus: "stopping" });
    window.clearTimeout(token.timer); window.clearInterval(token.interval);
    token.timer = window.setTimeout(() => token.fail("Recording could not finish. Record again or use Type answer."), 5000);
    try { token.recorder.stop(); this.stopInterviewTracks(token.stream); }
    catch (_err) { token.fail("Recording could not finish. Record again or use Type answer."); }
  };
  encodeInterviewAudio = (clip) => new Promise((resolve, reject) => {
    const reader = this._interviewReader = new window.FileReader();
    const finish = (error) => {
      window.clearTimeout(timer);
      const result = reader.result;
      reader.onload = reader.onerror = reader.onabort = null;
      if (this._interviewReader === reader) this._interviewReader = null;
      if (error || typeof result !== "string" || !result.includes(";base64,")) reject({ kind: "audio_encoding" });
      else resolve({ audio_b64: result.split(";base64,")[1], mime: clip.mime });
    };
    const timer = window.setTimeout(() => { finish(true); reader.abort(); }, 20000);
    reader.onload = () => finish(false);
    reader.onerror = reader.onabort = () => finish(true);
    try { reader.readAsDataURL(clip.blob); } catch (_err) { finish(true); }
  });
  interviewCurrent = (me) => !this._gone && this.state.screen === "interview"
    && this.state.me === me && me?.kind === "candidate";
  validInterviewBody = (body, id) => {
    const s = body?.session, q = body?.next_question;
    if (!s || typeof s.id !== "string" || !s.id || (id && s.id !== id)
      || !["in_progress", "completed", "abandoned"].includes(s.status)
      || !Array.isArray(s.questions) || !Array.isArray(s.turns)
      || !s.questions.every(q => q && typeof q.id === "string" && typeof q.text === "string")
      || !s.turns.every(t => t && typeof t.id === "string" && typeof t.transcript === "string"
        && t.score && typeof t.score.insufficient === "boolean" && Array.isArray(t.score.codes)
        && t.score.codes.every(c => typeof c === "string"))
      || new Set(s.questions.map(q => q.id)).size !== s.questions.length
      || new Set(s.turns.map(t => t.question_id)).size !== s.turns.length
      || s.turns.some((t, i) => t.question_id !== s.questions[i]?.id)) return false;
    const expected = s.status === "in_progress" ? s.questions[s.turns.length] : null;
    const a = s.assessment;
    if (a && (!["insufficient_signal", "superficial", "emerging", "solid", "deep"].includes(a.band)
      || ![a.overall, a.confidence, a.coverage].every(n => Number.isFinite(n) && n >= 0 && n <= 1)
      || typeof a.scorer_version !== "string")) return false;
    return s.status === "in_progress" ? !!expected && q?.id === expected.id && q?.text === expected.text
      : q === null && (s.status !== "completed" || !!a);
  };
  interviewErrorCopy = (err) => {
    if (!err) return "";
    if (err?.kind === "csrf") return CSRF_COPY;
    if (err?.status === 409) return "Saved interview state changed or expired. Refresh saved interviews before continuing.";
    if (err?.status === 404) return "This interview is unavailable to this account. Refresh saved interviews.";
    if (err?.status === 403) return "This account is not permitted to perform this interview action.";
    if (String(err?.detail || "").startsWith("speech_unavailable")) return "Speech transcription is unavailable. No answer was saved. Refresh saved interviews, then use Type answer.";
    if (String(err?.detail || "").startsWith("speech_failed")) return "Speech transcription failed. No answer was saved. Refresh saved interviews, then record again or use Type answer.";
    if (err?.status === 429) return "The transcription request limit was reached. Refresh saved state and use Type answer, or wait before recording again.";
    if (String(err?.detail || "").startsWith("audio exceeds")) return "Audio exceeds this server's size limit. Refresh saved state, then record a shorter answer or use Type answer.";
    if (err?.status === 422) return "The interview request was refused. Check the selected domain, saved profile and answer length, then refresh.";
    if (err?.kind === "invalid_response") return "The server response could not be read safely. Refresh saved interviews.";
    return "The interview request could not be confirmed. Refresh saved interviews before trying again.";
  };
  refreshInterviews = () => this.loadInterviews();
  openInterview = (id) => () => {
    if (this._interviewAction || this.state.interviewList.loading) return;
    this.setState({ interviewDraft: "", interviewConfirm: false, interviewBody: null });
    return this.loadInterviews(id);
  };
  loadInterviews = async (preferredId) => {
    const me = this.state.me;
    if (!this.interviewCurrent(me) || this._interviewAction) return;
    this.discardInterviewRecording();
    this.setState({ interviewAnswerMode: "text" });
    const token = this._interviewLoad = {};
    const current = () => this.interviewCurrent(me) && this._interviewLoad === token;
    const previous = this.state.interviewBody;
    this.setState({ interviewList: { ...this.state.interviewList, loading: true, error: null },
      interviewNeedsRefresh: true, interviewConfirm: false, interviewError: null });
    try {
      const data = await API.get("/portal/interviews", { timeoutMs: EVAL_TIMEOUT_MS });
      if (!current()) return;
      if (!Array.isArray(data?.interviews) || !data.interviews.every(i => i && typeof i.id === "string" && i.id
        && ["in_progress", "completed", "abandoned"].includes(i.status))
        || new Set(data.interviews.map(i => i.id)).size !== data.interviews.length)
        throw { kind: "invalid_response" };
      const rows = data.interviews.slice().sort((a, b) => String(b.started_at).localeCompare(String(a.started_at)));
      const requested = preferredId || previous?.session.id;
      const id = rows.find(i => i.id === requested)?.id || rows.find(i => i.status === "in_progress")?.id || rows[0]?.id;
      const body = id ? await API.get("/portal/interviews/" + encodeURIComponent(id), { timeoutMs: EVAL_TIMEOUT_MS }) : null;
      if (!current()) return;
      if (body && !this.validInterviewBody(body, id)) throw { kind: "invalid_response" };
      this.setState({ interviewList: { loading: false, data: rows, error: null }, interviewBody: body,
        interviewDraft: "", interviewNeedsRefresh: false, interviewError: null });
    } catch (err) {
      if (!current() || err?.kind === "session_lost") return;
      this.setState({ interviewList: { ...this.state.interviewList, loading: false, error: err },
        interviewNeedsRefresh: true, interviewError: err });
    }
  };
  setInterviewDraft = (e) => {
    if (!this._interviewAction && !this.state.interviewNeedsRefresh && !this.state.interviewList.loading)
      this.setState({ interviewDraft: e.target.value, interviewConfirm: false });
  };
  startInterview = () => this.writeInterview("start");
  submitInterviewAnswer = () => this.writeInterview("answer");
  armInterviewFinish = () => {
    if (!this._interviewCapture && !this.state.interviewBusy && !this.state.interviewNeedsRefresh) this.setState({ interviewConfirm: true });
  };
  cancelInterviewFinish = () => this.setState({ interviewConfirm: false });
  finishInterview = () => { if (this.state.interviewConfirm) return this.writeInterview("finish"); };
  writeInterview = async (action) => {
    const me = this.state.me, st = this.state, body = st.interviewBody;
    if (!this.interviewCurrent(me) || this._interviewAction || st.interviewNeedsRefresh || st.interviewList.loading
      || this._interviewCapture || !st.interviewList.data) return;
    if (action === "start" && st.interviewList.data.some(i => i.status === "in_progress")) return;
    if (action !== "start" && (body?.session.status !== "in_progress" || !body.next_question)) return;
    const voice = action === "answer" && st.interviewAnswerMode === "audio";
    const clip = voice ? this._interviewAudio : null;
    if (voice && (st.interviewAudioStatus !== "ready" || !clip || clip.me !== me || clip.sid !== body.session.id || clip.qid !== body.next_question.id)) return;
    if (action === "answer" && !voice && (!st.interviewDraft.trim() || st.interviewDraft.length > 20000)) {
      this.setState({ interviewError: { status: 422 } }); return;
    }
    const token = this._interviewAction = {};
    this._interviewLoad = null;
    const current = () => this.interviewCurrent(me) && this._interviewAction === token;
    const path = "/portal/interviews" + (action === "start" ? "" : "/" + encodeURIComponent(body.session.id)
      + (action === "answer" ? "/answers" : "/finish"));
    let payload = action === "start" ? { domain: st.domain } : action === "answer"
      ? { question_id: body.next_question.id, text: st.interviewDraft } : {};
    this.setState({ interviewBusy: true, interviewError: null, interviewConfirm: false });
    try {
      if (voice) {
        this._interviewAudio = null;
        this.setState({ interviewAudioStatus: "idle", interviewAudioSize: 0 });
        let encoded;
        try { encoded = await this.encodeInterviewAudio(clip); } catch (_err) { throw { kind: "audio_encoding" }; }
        if (!current()) return;
        payload = { question_id: body.next_question.id, ...encoded };
      }
      const result = await API.post(path, payload, { timeoutMs: EVAL_TIMEOUT_MS });
      if (!current()) return;
      if (!this.validInterviewBody(result, action === "start" ? null : body.session.id)) throw { kind: "invalid_response" };
      this.setState({ interviewBody: result, interviewDraft: "" });
      this._interviewAction = null;
      this.setState({ interviewBusy: false });
      await this.loadInterviews(result.session.id);
    } catch (err) {
      if (!current() || err?.kind === "session_lost") return;
      if (err?.kind === "audio_encoding") this.setState({ interviewAudioError: "The recording could not be prepared. Record again or use Type answer." });
      else this.setState({ interviewError: err, interviewNeedsRefresh: true });
    } finally {
      if (current()) { this._interviewAction = null; this.setState({ interviewBusy: false }); }
    }
  };
  interviewValues = () => {
    const st = this.state, body = st.interviewBody, session = body?.session, a = session?.assessment;
    const rows = st.interviewList.data || [], active = session?.status === "in_progress";
    const working = st.interviewBusy || st.interviewList.loading;
    const disabled = working || st.interviewNeedsRefresh || !active;
    const voice = st.interviewAnswerMode === "audio";
    const capturing = ["requesting", "recording", "stopping"].includes(st.interviewAudioStatus);
    const version = a?.scorer_version || "unknown";
    const comparable = ["s73.1", "s73.2"].includes(version) && a?.band !== "insufficient_signal";
    const band = comparable ? String(a.band) : "Insufficient evidence";
    const status = s => s === "abandoned" ? "Expired" : s === "completed" ? "Completed" : "In progress";
    return {
      pageSub: { fontSize: "12.5px", lineHeight: 1.6, color: "var(--muted)", marginTop: "10px", maxWidth: "75ch" },
      fieldLabel: { display: "block", fontSize: "12px", color: "var(--heading)", marginTop: "12px" },
      noticeBox: NOTICE_BOX,
      interviewAllowed: st.me?.kind === "candidate", interviewDenied: st.me?.kind !== "candidate",
      interviewWorking: working, interviewNeedsRefresh: st.interviewNeedsRefresh,
      interviewErrorText: this.interviewErrorCopy(st.interviewError),
      interviewEmpty: !!st.interviewList.data && !rows.length && !working,
      interviewStartDisabled: working || st.interviewNeedsRefresh || !st.interviewList.data || rows.some(i => i.status === "in_progress"),
      refreshInterviews: this.refreshInterviews, startInterview: this.startInterview,
      interviewHistory: rows.map(i => ({ id: i.id, label: status(i.status) + " · " + i.domain + " · " + fmtDateTime(i.started_at), open: this.openInterview(i.id) })),
      interviewHasSession: !!session, interviewId: session?.id || "", interviewStatus: session ? status(session.status) + " · " + session.domain : "",
      interviewProgress: session ? session.turns.length + " of " + session.questions.length + " saved answers" : "",
      interviewExpiry: "Expires: " + fmtDateTime(session?.expires_at), interviewActive: active,
      interviewExpired: session?.status === "abandoned", interviewQuestion: body?.next_question?.text || "",
      interviewQuestionId: body?.next_question?.id || "", interviewDraft: st.interviewDraft,
      interviewDraftCount: st.interviewDraft.length, setInterviewDraft: this.setInterviewDraft,
      interviewWriteDisabled: disabled, interviewSubmitDisabled: disabled || capturing || (voice
        ? st.interviewAudioStatus !== "ready" : !st.interviewDraft.trim() || st.interviewDraft.length > 20000),
      interviewSubmitLabel: voice ? "Submit voice answer" : "Submit answer",
      interviewTextMode: !voice, interviewAudioMode: voice,
      selectInterviewAudio: this.selectInterviewAudio, selectInterviewText: this.selectInterviewText,
      interviewAudioStatus: st.interviewAudioStatus, interviewAudioError: st.interviewAudioError,
      interviewAudioLabel: st.interviewAudioStatus === "requesting" ? "Waiting for microphone permission…"
        : st.interviewAudioStatus === "recording" ? "Microphone on · Recording " + st.interviewAudioSeconds + " seconds"
        : st.interviewAudioStatus === "stopping" ? "Microphone off · Finishing recording…"
        : st.interviewAudioStatus === "ready" ? "Microphone off · Ready to submit · " + st.interviewAudioSize + " bytes recorded"
        : "Microphone off · No recording",
      interviewRecordDisabled: disabled || capturing, interviewStopDisabled: st.interviewAudioStatus !== "recording",
      interviewFinishDisabled: disabled || capturing,
      startInterviewRecording: this.startInterviewRecording, stopInterviewRecording: this.stopInterviewRecording,
      discardInterviewRecording: this.discardInterviewRecording,
      submitInterviewAnswer: this.submitInterviewAnswer, armInterviewFinish: this.armInterviewFinish,
      interviewConfirm: st.interviewConfirm, finishInterview: this.finishInterview, cancelInterviewFinish: this.cancelInterviewFinish,
      interviewHasAssessment: !!a,
      interviewAssessmentText: a ? band + (comparable ? " · Saved index " + a.overall : " · No ability conclusion")
        + " · Confidence " + a.confidence + " · Coverage " + a.coverage + " (answered fraction, not evidence quality)" : "",
      interviewVersionText: "Saved scorer version: " + version + ". " + (version === "s73.2"
        ? "Current bounded English content heuristic; not calibrated assessment quality."
        : version === "s73.1" ? "Historical v1 rubric. Original values are preserved and cannot be compared directly with v2."
        : "Mixed or unknown rubric versions cannot support a comparable assessment. No confident blend is available."),
      interviewEvidenceText: "Missing or limited evidence is not poor ability. Unconfirmed relevance is excluded from current assessment evidence; human clarification may be needed.",
      interviewTurns: (session?.turns || []).map(t => ({ id: t.id, question: t.question_text, transcript: t.transcript,
        evidence: "Saved rubric: " + (t.score.scorer_version || "historical v1 / unknown") + ". "
          + (t.score.insufficient ? "Insufficient evidence; no ability conclusion. " : "")
          + ((t.score.codes || []).includes("limited_content") ? "Limited content evidence. " : "")
          + ((t.score.codes || []).includes("relevance_unconfirmed") ? "Relevance unconfirmed; excluded from current assessment evidence. " : "")
          + ((t.score.codes || []).includes("ownership_unknown") ? "Individual ownership is unconfirmed. " : "")
          + ((t.score.codes || []).includes("depth_unknown") ? "No confirmed depth yardstick. " : "")
          + ((t.score.codes || []).includes("transcript_truncated") ? "Saved transcript was truncated to the server's text limit. " : "") }))
    };
  };
  };
})(window);
