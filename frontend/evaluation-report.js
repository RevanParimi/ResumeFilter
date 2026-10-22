/* Evaluation, report and feedback logic for the existing DCLogic component.
 * Shared state, navigation, PDF reading and lifecycle remain in the component.
 */
(function (global) {
  "use strict";

  global.VeritasEvaluationReport = (Base, {
    API, EVAL_TIMEOUT_MS, errorCopy, IDLE, navigator, setTimeout, clearTimeout,
    navBtn, TEXT_AREA, NOTICE_BOX, ERROR_BOX, RISK_BAND, BAND, SUB_BAND_LABEL,
    SIGNAL_LABEL, STATUS, DEPTH_LABEL, OUTCOME_LABELS, OUTCOME_BY_VALUE,
    OUTCOME_NOTES_MAX, SMALL_GHOST, avatar, chip, initials, gradBar, num, pct,
    confWord, fmtDateTime
  }) => class extends Base {
  reportPath = (reportId) => (this.state.me && this.state.me.kind === "admin"
    ? "/report/" : "/screening/reports/") + encodeURIComponent(reportId);
  clearReportLocation = () => {
    if (window.location.hash.indexOf("report=") !== -1) {
      window.history.replaceState(null, "", window.location.pathname + window.location.search);
    }
  };
  openReport = (reportId, origin = "queue") => () => {
    const me = this.state.me;
    if (!me || (me.kind !== "org" && me.kind !== "admin")) return;
    if (me.kind === "admin") origin = "evaluate";
    this.setState({
      screen: "report", report: IDLE, outcomes: IDLE, reportOrigin: origin,
      // Notes belong to the report you were looking at. Carrying them onto the
      // next candidate is how a sentence about one person ends up filed
      // against another.
      outcomeNotes: "", outcomeError: null, outcomeBusy: null
    });
    this._recording = null;
    // Same late-reply guard as the batch reads: two quick clicks must not leave
    // the slower report rendered under the faster one's heading.
    this._viewReport = reportId;
    window.history.replaceState(null, "", window.location.pathname + window.location.search
      + "#report=" + encodeURIComponent(reportId) + "&from=" + origin);
    const path = this.reportPath(reportId);
    const still = () => !this._gone && this.state.me === me && this._viewReport === reportId;
    this.load("report", () => API.get(path, { timeoutMs: EVAL_TIMEOUT_MS }), still);
    // The report and its judgments are two reads because they are two routes;
    // both carry the SAME guard, or a late outcome list lands on the report you
    // navigated to next.
    this.load("outcomes",
              () => API.get(path + "/outcomes", { timeoutMs: EVAL_TIMEOUT_MS }), still);
    window.scrollTo(0, 0);
  };
  retryReport = () => { if (this._viewReport) this.openReport(this._viewReport, this.state.reportOrigin)(); };
  backFromReport = () => this.nav(this.state.reportOrigin === "evaluate" ? "evaluate" : "queue")();
  openReportKey = (reportId) => (e) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); this.openReport(reportId)(); }
  };

  setOutcomeNotes = (e) => this.setState({ outcomeNotes: e.target.value });

  // One click records one judgment. Deliberately NOT armed-then-confirmed like
  // the batch delete: this appends a row, it destroys nothing, and a reviewer
  // who changes their mind records that too (the list is append-only and shown
  // in order). A confirm step on a reversible, additive action just teaches
  // people to click through confirms.
  recordOutcome = (label) => () => {
    const reportId = this._viewReport;
    const me = this.state.me;
    // The in-flight guard is an INSTANCE FIELD rather than state — but be
    // precise about why, because the obvious reason is WRONG and was measured
    // to be wrong. The process driver needs a field because its loop consults
    // the flag on the tick that starts it, before setState has flushed. A
    // click handler is different: React flushes discrete events synchronously,
    // so `state.outcomeBusy` IS already set by the time a second click runs,
    // and a state-based guard was probed in a real browser and held (two
    // clicks in one synchronous block still recorded one judgement).
    //
    // The field stays because it does not depend on that flushing behaviour
    // holding — this list is append-only, so a double-record is permanent —
    // and because it is the same spelling as `_driving` and `_viewReport`
    // beside it. It is belt-and-braces, not a bug fix, and the check in
    // scripts/check_ui_screening_browser.py says so.
    if (this._gone || !reportId || this._recording || !me || !["org", "admin"].includes(me.kind)) return;
    const token = this._recording = {};
    const path = this.reportPath(reportId);
    const current = () => !this._gone && this.state.me === me && this._viewReport === reportId;
    this.setState({ outcomeBusy: label, outcomeError: null });
    API.post(path + "/outcome",
             { outcome: label, notes: this.state.outcomeNotes }, { timeoutMs: EVAL_TIMEOUT_MS }).then(
      () => {
        // Released whatever happened next, including a navigation away: a
        // guard that only clears on the path the user stayed on would leave
        // the next report unable to record anything at all.
        if (this._recording !== token) return;
        this._recording = null;
        if (!current()) return;
        this.setState({ outcomeBusy: null, outcomeNotes: "" });
        this.load("outcomes",
                  () => API.get(path + "/outcomes", { timeoutMs: EVAL_TIMEOUT_MS }), current);
      },
      (err) => {
        if (this._recording !== token) return;
        this._recording = null;
        if (err && err.kind === "session_lost") return;
        if (!current()) return;
        // The notes are NOT cleared on failure: they are the thing that was
        // just refused, and retyping them is the user paying for our error.
        this.setState({ outcomeBusy: null, outcomeError: err });
      }
    );
  };

  setEvalText = (e) => { if (!this._evaluating) this.setState({ evalText: e.target.value, evalFile: null, evalError: null }); };
  setEvalGithub = (e) => { if (!this._evaluating) this.setState({ evalGithub: e.target.value }); };
  setEvalPortfolio = (e) => { if (!this._evaluating) this.setState({ evalPortfolio: e.target.value }); };
  pickEvalFile = (e) => {
    const file = e.target.files && e.target.files[0];
    e.target.value = "";
    if (!file || this._evaluating) return;
    if (!/\.pdf$/i.test(file.name)) {
      this.setState({ evalError: { detail: "Choose a PDF, or paste plain text." } });
      return;
    }
    this.setState({ evalFile: file, evalText: "", evalError: null });
  };
  clearEvalFile = () => { if (!this._evaluating) this.setState({ evalFile: null, evalError: null }); };
  viewEvaluation = () => { if (this.state.evalReportId) this.openReport(this.state.evalReportId, "evaluate")(); };
  runEvaluate = async () => {
    if (this._evaluating || this._gone) return;
    const st = this.state, me = st.me;
    if (!me || (me.kind !== "org" && me.kind !== "admin")) {
      this.setState({ evalError: { detail: "Instant check requires an organisation or operator session." } });
      return;
    }
    if (!st.evalFile && !st.evalText.trim()) {
      this.setState({ evalError: { detail: "Paste readable resume text or attach a PDF." } });
      return;
    }
    const token = this._evaluating = {};
    const current = () => !this._gone && this._evaluating === token && this.state.me === me;
    this.setState({ evalBusy: true, evalError: null, evalReportId: null,
      evalProgress: st.evalFile ? "Reading the selected PDF…" : "Waiting for the server assessment…" });
    try {
      const source = st.evalFile ? await this._readFile({ file: st.evalFile, name: st.evalFile.name, kind: "pdf" })
        : { resume_text: st.evalText };
      if (!current()) return;
      this.setState({ evalProgress: "Waiting for the server assessment. No stage progress is available." });
      const body = Object.assign({}, source, { domain: st.domain,
        github_url: st.evalGithub.trim() || null, portfolio_url: st.evalPortfolio.trim() || null });
      if (me.kind === "org") body.evaluate = true;
      const result = await API.post(me.kind === "org" ? "/screening/candidates" : "/evaluate",
        body, { timeoutMs: EVAL_TIMEOUT_MS });
      if (!current()) return;
      const report = me.kind === "org" ? result && result.report : result;
      if (!report || typeof report.id !== "string" || !report.id) {
        throw { detail: "The server returned no report reference. This run may have been saved; check before submitting again." };
      }
      this.setState({ evalReportId: report.id });
      if (this.state.screen === "evaluate") this.openReport(report.id, "evaluate")();
    } catch (err) {
      if (!current() || err.kind === "session_lost") return;
      this.setState({ evalError: err });
    } finally {
      if (current()) {
        this._evaluating = null;
        this.setState({ evalBusy: false, evalProgress: "" });
      }
    }
  };

  _copyHandlers = {};
  copyProbes = (key, probes) => () => {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(probes.join("\n")).catch(() => {});
    }
    this.setState({ copied: key });
    clearTimeout(this._copyTimer);
    this._copyTimer = setTimeout(() => this.setState({ copied: null }), 2000);
  };
  evaluationValues() {
    const st = this.state;
    const s = st.screen;
    return {
      isEvaluate: s === "evaluate",
      navEvaluate: navBtn(s === "evaluate"),
      goEvaluate: this.goEvaluate,
      runEvaluate: this.runEvaluate,
      textArea: TEXT_AREA,
      evaluateAction: st.evalBusy ? "Evaluating…" : st.evalError ? "Retry evaluation" : "Evaluate this resume",
      evalRunning: st.evalBusy, evalBusy: st.evalBusy, evalProgress: st.evalProgress,
      evalNoticeBox: NOTICE_BOX, evalErrorBox: ERROR_BOX,
      evalText: st.evalText, evalGithub: st.evalGithub, evalPortfolio: st.evalPortfolio,
      setEvalText: this.setEvalText, setEvalGithub: this.setEvalGithub, setEvalPortfolio: this.setEvalPortfolio,
      pickEvalFile: this.pickEvalFile, clearEvalFile: this.clearEvalFile,
      hasEvalFile: !!st.evalFile, evalFileLabel: st.evalFile ? st.evalFile.name : "PDF or pasted text; selecting one replaces the other.",
      evalError: !!st.evalError,
      evalErrorText: st.evalError ? (st.evalError.status === 403 && st.evalError.kind !== "csrf"
        ? "This account is not permitted to evaluate this resume."
        : errorCopy(st.evalError)) + (["network", "timeout"].includes(st.evalError.kind) || st.evalError.status >= 500
          ? " The server may have saved the run. Retrying may create another saved evaluation; retry only when ready." : "") : "",
      hasEvalReport: !!st.evalReportId, evalReportId: st.evalReportId || "", viewEvaluation: this.viewEvaluation,
      evalStorageCopy: st.me && st.me.kind === "admin"
        ? "Paste text or attach a PDF. This operator check saves a report, without creating a candidate or fingerprinting the resume."
        : "Paste text or attach a PDF. This saves a candidate, resume and report for your organisation, outside a batch.",
      backFromReport: this.backFromReport, retryReport: this.retryReport,
      reportBackLabel: st.reportOrigin === "evaluate" ? "← Back to Instant check" : "← Back to screening queue",

    };
  }

  reportValues() {
    const st = this.state;
    const rep = st.report.data;
    // -- report ------------------------------------------------------------
    const ctx = (rep && rep.candidate_context) || {};
    const fab = (rep && rep.fabrication_risk) || null;
    const version = fab ? (fab.scorer_version == null ? 1 : fab.scorer_version) : null;
    const repBand = (fab && (version === 1 || version === 2) && RISK_BAND[fab.band]) || BAND.insufficient;
    const assessable = fab && (version === 1 || version === 2) && fab.band !== "insufficient_data";
    const deg = Math.round((assessable ? fab.score : 0) * 360);
    const subs = rep ? {
      cross_field: { title: "Timeline / structure", a: rep.cross_field,
        help: "Extracted dates and structure may be incomplete. Ask about date precision, concurrent or part-time roles and the context of each finding." },
      resume_farm: { title: "Content overlap", a: rep.resume_farm,
        help: "Similarity estimates text overlap in the stored comparison corpus. Shared templates are legitimate; ask which contributions and results are the candidate's own." }
    } : {};
    // Always show missing factual checks, even when fusion excluded them.
    // Historical contributors are documented separately without recomputing.
    const reportComponents = Object.keys(subs).map((id) => {
      const s = subs[id];
      const a = s.a;
      const c = fab && (fab.components || []).find((x) => x.id === id);
      const usable = a && a.band !== "insufficient_data";
      return {
        title: s.title,
        band: usable ? (SUB_BAND_LABEL[a.band] || a.band) : "Insufficient data",
        meta: usable ? "Check confidence " + num(a.confidence) + (c ? " · fusion weight " + num(c.weight) : " · excluded from index") : "Excluded from index: check unavailable",
        detail: ((a && a.reasoning) || "No assessment was recorded for this check.") + " " + s.help
      };
    });
    const timeline = rep && rep.cross_field;
    const reportTimelineFindings = ((timeline && timeline.findings) || []).map((f) => ({
      title: f.id.replace(/_/g, " ") + " · " + f.severity + " observation",
      detail: f.detail,
      clarify: f.id === "timeline_overlap"
        ? "Clarify the dates and whether the roles were concurrent, contract or part-time; an overlap alone does not establish dishonesty."
        : "Confirm the extracted dates and role context with the candidate before drawing a conclusion."
    }));
    const style = rep && rep.ai_generation;
    const styleSignals = ((style && style.signals) || []).filter((s) => s.source === "deterministic");
    const modelStyleCount = ((style && style.signals) || []).filter((s) => s.source === "llm").length;
    const farm = rep && rep.resume_farm;
    const matches = (farm && farm.matches) || [];
    // Similarity and count only. The org plane nulls the ids before they leave
    // the API (Phase A); this screen never reads them either, so a regression
    // there could not surface here.
    const topSimilarity = matches.length
      ? matches.reduce((m, x) => Math.max(m, x.similarity || 0), 0) : null;

    const verdicts = rep ? (rep.verdicts || []).map((v, i) => {
      const key = rep.id + ":" + i;
      if (!this._copyHandlers[key]) this._copyHandlers[key] = this.copyProbes(key, v.probes || []);
      return {
        claim: v.claim_text,
        status: v.status,
        chip: chip(STATUS[v.status] || BAND.insufficient),
        meta: v.claim_type + " · coherence " + num(v.coherence_score),
        reasoning: v.reasoning || "No reasoning was recorded for this claim.",
        missing: (v.missing_signals || []).length
          ? v.missing_signals
          : ["None — a genuine version of this claim would look like this one."],
        evidence: (v.evidence || []).length
          ? v.evidence.map((e) => ({ source: e.source, detail: e.detail }))
          : [{ source: "—", detail: "No evidence either way." }],
        probes: v.probes || [],
        hasProbes: (v.probes || []).length > 0,
        confBar: gradBar(v.confidence),
        coherenceLabel: "coherence " + num(v.coherence_score) + " · confidence " + num(v.confidence),
        copy: this._copyHandlers[key],
        copyLabel: st.copied === key ? "Copied" : ((v.probes || []).length > 1 ? "Copy questions" : "Copy question")
      };
    }) : [];

    // -- the outcome loop (S8.5) -------------------------------------------
    // The four buttons the design carried from the start, finally callable:
    // POST /screening/reports/{id}/outcome landed on the ORG plane this sprint.
    // Handlers are cached per label so a re-render does not hand the template a
    // new function every frame — the same reason `_copyHandlers` exists above.
    if (!this._outcomeHandlers) {
      this._outcomeHandlers = OUTCOME_LABELS.reduce(
        (m, o) => Object.assign(m, { [o.value]: this.recordOutcome(o.value) }), {}
      );
    }
    const outcomeButtons = OUTCOME_LABELS.map((o) => ({
      label: st.outcomeBusy === o.value ? "Recording…" : o.label,
      record: this._outcomeHandlers[o.value],
      // Busy is per-BUTTON, not global: a spinner on all four would be lying
      // about which judgment is in flight.
      style: Object.assign({}, SMALL_GHOST, {
        padding: "9px 12px", textAlign: "left",
        opacity: st.outcomeBusy && st.outcomeBusy !== o.value ? 0.5 : 1,
        cursor: st.outcomeBusy ? "default" : "pointer"
      })
    }));
    const outcomeRows = ((st.outcomes.data && st.outcomes.data.outcomes) || []).map((o) => {
      const meta = OUTCOME_BY_VALUE[o.outcome];
      return {
        label: meta ? meta.label : o.outcome,
        chip: chip(meta ? meta.band : BAND.insufficient),
        // An em dash rather than an empty node: a row whose notes were blank
        // would otherwise render as a chip floating over nothing.
        notes: o.notes || "—",
        when: fmtDateTime(o.recorded_at)
      };
    });

    return {
      // -- report ----------------------------------------------------------
      reportLoading: st.report.loading,
      reportError: !!st.report.error,
      reportErrorText: errorCopy(st.report.error),
      reportReference: rep ? rep.id : "",
      hasReport: !!rep,
      reportName: ctx.full_name || "Name not extracted",
      reportRole: [ctx.role_title, ctx.seniority, rep && rep.domain].filter(Boolean).join(" · ") || "—",
      reportSummary: rep ? (rep.summary || "No summary was generated for this report.") : "",
      reportSummaryLabel: version === 1 ? "Stored historical summary (original wording)" : "Assessment summary",
      reportVersionNote: version === 2
        ? "Current factual review context · v2. Timeline and content overlap only; writing style is excluded. The review index is a heuristic, not a fraud probability."
        : version === 1
          ? "Historical assessment · v1. This stored index included writing style. Its original score and wording are retained; it is not comparable to current factual context v2 and cannot establish authorship or dishonesty."
          : fab ? "Unsupported scorer version " + version + ". Stored data is retained; its index cannot be interpreted by this UI."
            : "No factual review assessment was recorded. No index is available.",
      reportRiskExplanation: !assessable
        ? "Cannot assess factual risk: insufficient data or unsupported assessment. This is not a low score. Review the unavailable checks below and request missing dates or comparison context."
        : "This advisory index is based on the checks available when the report was created. Low means few concerns were observed, not verified experience. Confidence describes available check coverage, not the probability of dishonesty.",
      reportComponentHelp: version === 1
        ? "Historical fusion contributors: " + (fab.components || []).map((c) => SIGNAL_LABEL[c.id] || c.id).join(", ") + ". The original index is preserved; these factual observations and style notes are shown separately for clarification."
        : "Timeline and content-overlap checks contribute only when assessable. Missing coverage can prevent an assessment. Writing-style observations are shown separately and never supply factual evidence.",
      reportDepth: rep
        ? (DEPTH_LABEL[rep.depth_band] || rep.depth_band) + " · depth " + num(rep.depth_score)
        : "—",
      reportInitials: ctx.full_name ? initials(ctx.full_name) : "··",
      reportAvatar: avatar(repBand, 36),
      reportScore: assessable ? num(fab.score) : "—",
      reportIndexLabel: assessable ? "Advisory review index " + num(fab.score) : "Review index unavailable",
      reportBandLabel: version && version !== 1 && version !== 2 ? "Unsupported version" : repBand.label,
      reportChip: Object.assign(chip(repBand), { marginTop: "9px" }),
      gaugeRing: {
        width: "108px", height: "108px", borderRadius: "50%", display: "grid", placeItems: "center",
        background: assessable ? "conic-gradient(from 180deg, " + repBand.c + " 0deg, " + repBand.c + " " + deg + "deg, var(--track) " + deg + "deg)" : "var(--track)"
      },
      reportConfBar: gradBar(assessable ? fab.confidence : 0),
      reportConfLabel: assessable ? num(fab.confidence) + " · " + confWord(fab.confidence) : "insufficient coverage",
      reportComponents,
      reportTimelineFindings,
      reportStyleStatus: !style ? "No style assessment was recorded."
        : style.band === "insufficient_text" ? "Insufficient text for style observations."
          : styleSignals.length ? styleSignals.length + " text pattern(s) recorded." : "No deterministic style patterns were recorded; this does not verify authorship.",
      reportStyleSignals: styleSignals.map((s) => "Text observation: " + s.detail).concat(modelStyleCount
        ? [modelStyleCount + " model suggestion(s) were also recorded, unverified; model opinions do not establish authorship."] : []),
      reportFarmLine: matches.length
        ? matches.length + " content match(es) in a corpus of " + (farm.corpus_size || 0)
          + "; highest estimated text overlap " + pct(topSimilarity) + ". Match identities are withheld. Similarity is not proof of copied experience."
        : "",
      reportFarmMatches: matches.map((m, i) => "Content match " + (i + 1) + ": " + pct(m.similarity) + " estimated text overlap."),
      hasFarmMatches: matches.length > 0,
      reportVerdicts: verdicts,
      hasVerdicts: verdicts.length > 0,
      noVerdicts: !!rep && verdicts.length === 0,
      reportThinReason: rep
        ? "The engine found no claims on this resume worth reasoning about — not enough dated, specific or anchored material to extract."
        : "",

      // -- the outcome loop (S8.5) -----------------------------------------
      outcomeNotes: st.outcomeNotes,
      setOutcomeNotes: this.setOutcomeNotes,
      outcomeNotesMax: OUTCOME_NOTES_MAX,
      outcomeNotesCount: st.outcomeNotes.length + " / " + OUTCOME_NOTES_MAX,
      outcomeButtons,
      outcomeError: !!st.outcomeError,
      outcomeErrorText: errorCopy(st.outcomeError) + (st.outcomeError &&
        (["network", "timeout"].includes(st.outcomeError.kind) || st.outcomeError.status >= 500)
        ? " Your judgement may have been saved. Reload saved feedback before recording again." : ""),
      // The RECORD action and the LIST read fail separately and are shown
      // separately. A failed list used to render nothing at all — no history,
      // no empty state, no error — which invites recording the same judgement
      // twice onto an append-only list.
      outcomesError: !!st.outcomes.error,
      outcomesErrorText: errorCopy(st.outcomes.error),
      outcomeRows,
      hasOutcomes: outcomeRows.length > 0,
      // NOT `!hasOutcomes`: an empty list and a list that has not arrived are
      // different states, and the empty-state copy must not flash while the
      // read is still in flight (the same rule the queue's empty state follows).
      noOutcomes: !!st.outcomes.data && outcomeRows.length === 0,
      outcomeHistoryNote: outcomeRows.length === 1
        ? "One judgement recorded. Nothing here is visible to the candidate."
        : outcomeRows.length + " judgements, oldest first. Nothing here is visible to the candidate.",

    };
  }
  };
})(window);
