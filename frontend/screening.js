/* Screening intake, batches, processing and view values for DCLogic.
 * Shared state, navigation, lifecycle, row cache and file reading stay in the component.
 */
(function (global) {
  "use strict";

  global.VeritasScreening = (Base, {
    API, errorCopy, IDLE, BATCH_STATUS, ITEM_STATUS, RISK_BAND, BAND,
    SIGNAL_LABEL, SUB_BAND_LABEL, SMALL_MUTED, SMALL_GHOST, GHOST_BTN,
    SMALL_PRIMARY_FLAT, ERROR_BOX, fmtDate, fmtDateTime, gradBar, shortId,
    avatar, chip, num, riskBar, confBarStyle
  }) => class extends Base {
  // ── screening ─────────────────────────────────────────────────────────────
  // Opening the queue with no batch chosen picks the newest, because the list
  // is newest-first server-side. An org that has uploaded nothing lands on an
  // EMPTY QUEUE, not an error — the first screen every new customer sees
  // (UI.md §9).
  loadScreening = () => {
    if (this.state.selectedBatch) { this.refreshBatch(); return; }
    this.load("batchList", () => API.get("/screening/batches")).then((page) => {
      const first = page && page.batches && page.batches[0];
      if (first) { this.setState({ selectedBatch: first.id }); this.refreshBatch(first.id); }
    });
  };

  loadBatches = () => this.load("batchList", () => API.get("/screening/batches"));

  // Three reads, one batch: detail carries progress, summary carries the
  // whole-batch band counts the header shows, queue carries the ranked page.
  // The header's numbers come from SUMMARY on purpose (spec 0.6) — over a paged
  // list, "11 elevated" computed from one page would silently mean
  // "11 on this page".
  refreshBatch = (id) => {
    const batchId = id || this.state.selectedBatch;
    if (!batchId) return Promise.resolve(null);
    // Tracked in an instance field, not state: the guard has to be correct the
    // instant the user clicks, and setState has not flushed by then.
    this._viewBatch = batchId;
    const still = () => this._viewBatch === batchId;
    return Promise.all([
      this.load("batch", () => API.get("/screening/batches/" + batchId), still),
      this.load("summary", () => API.get("/screening/batches/" + batchId + "/summary"), still),
      this.load("queue", () => API.get("/screening/batches/" + batchId + "/queue"), still)
    ]);
  };
  refresh = () => { this.refreshBatch(); };

  selectBatch = (id) => () => {
    // Switching batches must not leave the previous one's rows on screen while
    // the new ones load — a queue showing another batch's people is the one
    // mistake this screen cannot make. It also stops the driver: the loop is
    // pinned to one batch id and nothing else may inherit it.
    this._driving = false;
    this.setState({ selectedBatch: id, screen: "queue", queue: IDLE, summary: IDLE, batch: IDLE,
      driving: false, driveError: null, driveDone: 0, driveFailed: 0 });
    this.refreshBatch(id);
    window.scrollTo(0, 0);
  };

  // Keyset pagination: hand `next_cursor` straight back as `cursor` and APPEND.
  // Replacing would lose everything above it; the cursor is a position, not a
  // page number, so there is no going back.
  loadMore = (key, path, field) => () => {
    const held = this.state[key].data;
    const cursor = held && held.next_cursor;
    if (!cursor || this.state.moreBusy === key) return;
    this.setState({ moreBusy: key });
    API.get(path + (path.indexOf("?") === -1 ? "?" : "&") + "cursor=" + encodeURIComponent(cursor)).then(
      (page) => this.setState((s) => ({
        moreBusy: null,
        [key]: { loading: false, error: null, data: Object.assign({}, page, {
          [field]: ((s[key].data && s[key].data[field]) || []).concat(page[field] || [])
        }) }
      })),
      (err) => this.setState((s) => ({ moreBusy: null, [key]: { loading: false, data: s[key].data, error: err } }))
    );
  };
  moreBatches = this.loadMore("batchList", "/screening/batches", "batches");
  moreQueue = () => {
    const id = this.state.selectedBatch;
    if (!id) return;
    this.loadMore("queue", "/screening/batches/" + id + "/queue", "rows")();
  };

  // ── the process driver ────────────────────────────────────────────────────
  screeningErrorCopy = (err) => {
    const recovery = ' Wait and refresh the batch. When the row says not screened yet, choose Start screening. Earlier results may already be saved.';
    if (err && err.detail === 'candidate_ingest_pending')
      return 'This upload may still be saving.' + recovery;
    if (err && ['candidate_ingest_capacity_exhausted', 'candidate_ingest_executor_closed'].includes(err.detail))
      return 'Screening uploads are temporarily unavailable.' + recovery;
    return errorCopy(err);
  };

  // POST .../process does at most `screening_max_items_per_call` items, each a
  // full nine-node graph run, so the client loops. Sequential by construction:
  // the server's conditional claim stops two callers double-billing the SAME
  // item, and nothing at all stops a client fanning out across DIFFERENT ones.
  //
  // Any error STOPS the loop. There is still no rate limiting server-side
  // (S8.3), so a retrying driver is caught nowhere.
  // `_driving` is the loop's control flag and `state.driving` is what renders.
  // They cannot be the same field: setState is asynchronous, so a driver that
  // consulted state would read the PREVIOUS value on the tick it starts and
  // stop before its first call.
  _drive = (batchId) => {
    this._driving = true;
    this._driveBatch = batchId;
    this.setState({ driving: true, driveError: null, driveDone: 0, driveFailed: 0 });
    this._tick(batchId);
  };
  startProcessing = () => {
    if (this._driving || !this.state.selectedBatch) return;
    this._drive(this.state.selectedBatch);
  };

  _halt = (extra) => {
    this._driving = false;
    this.setState(Object.assign({ driving: false }, extra || {}));
  };
  stopProcessing = () => this._halt();

  _tick = (batchId) => {
    // Stopped, unmounted, or the user moved to another batch — all three mean
    // "do not start another call".
    if (!this._driving || this._gone || this._driveBatch !== batchId) return;
    API.post("/screening/batches/" + batchId + "/process").then(
      (res) => {
        if (this._gone || !this._driving || this._driveBatch !== batchId) return;
        this.setState((s) => ({
          driveDone: s.driveDone + (res.processed || 0),
          driveFailed: s.driveFailed + (res.failed || 0)
        }));
        // The call IS the tick (spec 0.4): refresh from what just changed
        // rather than polling a queue nothing else is working on.
        this.refreshBatch(batchId);
        if (!res.remaining) { this._halt(); return; }
        this._tick(batchId);
      },
      (err) => {
        // A 401 has already sent the user to login; anything else stops the
        // loop and says why. Never retry (there is no rate limiter, S8.3).
        if (this._gone) return;
        if (err && err.kind === "session_lost") { this._driving = false; return; }
        this._halt({ driveError: err });
      }
    );
  };

  // Two clicks, because this is a real delete of real personal data:
  // batch_items.raw_text has no candidate to cascade from, and this route is
  // the only path that removes it (SCREENING.md §7).
  // The Delete button sits INSIDE the row, and the row is itself a click
  // target that opens the batch. Without stopPropagation, arming a delete also
  // navigates away from the list you armed it on — which a browser click-through
  // caught and no unit test could have.
  armDelete = (id) => (e) => {
    if (e && e.stopPropagation) e.stopPropagation();
    this.setState({ deleteArmed: id });
  };
  cancelDelete = (e) => {
    if (e && e.stopPropagation) e.stopPropagation();
    this.setState({ deleteArmed: null });
  };
  confirmDelete = (id) => (e) => {
    if (e && e.stopPropagation) e.stopPropagation();
    this.setState({ busyId: id, deleteArmed: null });
    if (this._driveBatch === id) this._driving = false;
    API.del("/screening/batches/" + id).then(
      () => {
        const wasSelected = this.state.selectedBatch === id;
        // Drop the view token too, or an in-flight refresh of the batch that
        // was just deleted lands afterwards and repopulates the screen.
        if (wasSelected) this._viewBatch = null;
        this.setState({
          busyId: null,
          selectedBatch: wasSelected ? null : this.state.selectedBatch,
          driving: wasSelected ? false : this.state.driving,
          queue: wasSelected ? IDLE : this.state.queue,
          summary: wasSelected ? IDLE : this.state.summary,
          batch: wasSelected ? IDLE : this.state.batch
        });
        this.loadBatches();
      },
      (err) => this.setState({ busyId: null, batchList: { loading: false, data: this.state.batchList.data, error: err } })
    );
  };

  // ── upload ────────────────────────────────────────────────────────────────
  setBatchNameInput = (e) => this.setState({ batchNameInput: e.target.value });

  // The API accepts resume_text or resume_pdf_b64 and nothing else, so a .docx
  // is refused HERE, naming the file, rather than sent to be refused as
  // "item 12" (spec 1.E).
  pickFiles = (e) => {
    const picked = Array.from((e.target && e.target.files) || []);
    if (!picked.length) return;
    this.setState((s) => ({
      files: s.files.concat(picked.map((f) => ({
        name: f.name, size: f.size, file: f,
        kind: /\.pdf$/i.test(f.name) ? "pdf" : /\.(txt|md|text)$/i.test(f.name) ? "text" : "unsupported"
      }))),
      uploadError: null, uploadNotice: null
    }));
    // Let the same file be chosen again after it is removed.
    if (e.target) e.target.value = "";
  };
  removeFile = (i) => () => this.setState((s) => ({ files: s.files.filter((_f, k) => k !== i), uploadError: null }));
  clearFiles = () => this.setState({ files: [], uploadError: null, uploadNotice: null });

  // A corrupt PDF refuses the WHOLE registration, naming the failing item's
  // INDEX. "Item 37" means nothing to somebody looking at 400 filenames, so the
  // index is translated back into the name it came from.
  _nameIndex = (detail, files) => {
    const m = /^item (\d+):\s*(.*)$/.exec(String(detail || ""));
    if (!m) return detail;
    const f = files[Number(m[1])];
    return (f ? "“" + f.name + "”" : "item " + m[1]) + ": " + m[2]
      + " — nothing was registered. Fix or remove that file and upload again.";
  };

  submitUpload = () => {
    const files = this.state.files;
    if (!files.length) { this.setState({ uploadError: { detail: "Choose at least one resume." } }); return; }
    const bad = files.filter((f) => f.kind === "unsupported");
    if (bad.length) {
      this.setState({ uploadError: { detail:
        "This API reads PDF and plain text only. Remove: " + bad.map((f) => f.name).join(", ") } });
      return;
    }
    this.setState({ uploadBusy: true, uploadError: null, uploadNotice: null });
    Promise.all(files.map(this._readFile))
      .then((items) => {
        // An EMPTY text file passes every check above and then fails Pydantic's
        // "at least one of resume_text/resume_pdf_b64" as a VALIDATION error —
        // a list-shaped detail carrying a field path, not the readable
        // "item N:" refusal. Cheaper and clearer to name the file here.
        const empties = items
          .map((it, i) => (it.resume_text !== undefined && !it.resume_text.trim() ? files[i].name : null))
          .filter(Boolean);
        if (empties.length) {
          throw { local: true, detail: "Nothing to screen in: " + empties.join(", ") };
        }
        return API.post("/screening/batches", {
          name: (this.state.batchNameInput || "").trim(),
          domain: this.state.domain,
          items
        });
      })
      .then((batch) => {
        // Registering N resumes is an unambiguous instruction to screen them,
        // so the driver starts here — and ONLY here. Merely opening a batch
        // with pending items must never trigger billed work (spec 0.3).
        this.setState({
          uploadBusy: false, files: [], batchNameInput: "",
          selectedBatch: batch.id, screen: "queue",
          queue: IDLE, summary: IDLE, batch: IDLE
        });
        this.refreshBatch(batch.id);
        this._drive(batch.id);
        window.scrollTo(0, 0);
      })
      .catch((err) => {
        // A 401 has already sent the user to login; anything on top of that
        // would be a second explanation for one event.
        if (err && err.kind === "session_lost") { this.setState({ uploadBusy: false }); return; }
        this.setState({
          uploadBusy: false,
          uploadError: err && err.local ? err
            : Object.assign({}, err, { detail: this._nameIndex(err && err.detail, files) })
        });
      });
  };

  /* The five screening screens (S8.5). Every value here is one hop from a route
   * in SCREENING.md, so the mapping can be checked without reading other screens. */
  screeningVals() {
    const st = this.state;
    const batch = st.batch.data;
    const sum = st.summary.data;
    const queue = st.queue.data;
    const listed = st.batchList.data;

    // -- batches -----------------------------------------------------------
    const batchRows = listed && listed.batches ? listed.batches.map((b) => {
      const c = b.counts || {};
      const total = (c.pending || 0) + (c.processing || 0) + (c.done || 0) + (c.failed || 0);
      const settled = (c.done || 0) + (c.failed || 0);
      const frac = total ? settled / total : 0;
      return {
        id: b.id,
        name: b.name || "Untitled batch",
        // BatchView carries counts by ITEM STATUS only — there is no per-band
        // count here and no route that gives one without a summary call per
        // row, so the column says done/total instead of inventing "elevated"
        // (spec 0.7).
        meta: fmtDate(b.created_at) + " · " + total + (total === 1 ? " resume" : " resumes") + " · " + b.domain,
        statusLabel: BATCH_STATUS[b.status] || b.status,
        progressLabel: settled + " of " + total + " screened",
        progressBar: gradBar(frac),
        failedLabel: c.failed ? c.failed + " failed" : "",
        current: b.id === st.selectedBatch,
        open: this.rowHandler("open", b.id, () => this.selectBatch(b.id)),
        openKey: this.rowHandler("openKey", b.id, () => (e) => {
          if (e.key === "Enter" || e.key === " ") { e.preventDefault(); this.selectBatch(b.id)(); }
        }),
        armed: st.deleteArmed === b.id,
        arm: this.rowHandler("arm", b.id, () => this.armDelete(b.id)),
        confirm: this.rowHandler("del", b.id, () => this.confirmDelete(b.id)),
        cancel: this.cancelDelete,
        deleteLabel: st.busyId === b.id ? "Deleting…" : "Delete",
        deleteBtn: st.busyId === b.id ? SMALL_MUTED : SMALL_GHOST
      };
    }) : [];

    // -- the selected batch's header ---------------------------------------
    const counts = (batch && batch.counts) || null;
    const total = counts ? counts.pending + counts.processing + counts.done + counts.failed : 0;
    const settled = counts ? counts.done + counts.failed : 0;
    const byBand = (sum && sum.by_risk_band) || {};
    const nScreened = (sum && sum.n_screened) || 0;
    // A share of what has been SCREENED, never of what was uploaded: at 20%
    // processed the other 80% is unknown, not "insufficient" (spec 1.C).
    const share = (n) => (nScreened ? Math.round((n / nScreened) * 100) + "%" : "—");

    const queueRows = queue && queue.rows ? queue.rows.map((r) => {
      const sig = r.signals || null;
      const b = (sig && RISK_BAND[sig.risk_band]) || BAND.insufficient;
      const scored = r.risk_score !== null && r.risk_score !== undefined;
      const assessable = scored && sig && sig.risk_band !== "insufficient_data";
      const loud = sig && sig.loudest_signal
        ? (SIGNAL_LABEL[sig.loudest_signal] || sig.loudest_signal)
            + (sig.loudest_band ? " — " + (SUB_BAND_LABEL[sig.loudest_band] || sig.loudest_band).toLowerCase() : "")
        : (r.status === "done" ? "None — nothing dominated" : "—");
      return {
        // The queue holds no names, by design: candidate_id is SET NULL on
        // erasure, so anything stored beside it would outlive the person
        // (SCREENING.md §5). The name lives on the report, one click away.
        name: shortId(r.candidate_id || r.item_id),
        role: r.status === "done" ? "screened " + fmtDateTime(r.processed_at) : ITEM_STATUS[r.status] || r.status,
        initials: r.status === "done" ? "··" : "—",
        avatar: avatar(b, 30),
        chip: chip(b), bandLabel: scored ? b.label : "Not screened",
        reason: r.reason,
        loudest: loud,
        scoreLabel: assessable ? num(r.risk_score) : "—",
        riskBar: riskBar(assessable ? r.risk_score : 0, b),
        confBar: confBarStyle(sig ? sig.risk_confidence : 0),
        confLabel: sig ? "conf " + num(sig.risk_confidence) : "conf —",
        // A row with no report has nothing to open — an affordance that always
        // fails is worse than none.
        openable: !!r.report_id,
        open: r.report_id ? this.rowHandler("rep", r.report_id, () => this.openReport(r.report_id)) : this.noop,
        openKey: r.report_id ? this.rowHandler("repKey", r.report_id, () => this.openReportKey(r.report_id)) : this.noop
      };
    }) : [];

    // -- upload ------------------------------------------------------------
    const files = st.files.map((f, i) => ({
      name: f.name,
      meta: (f.size > 1024 * 1024 ? (f.size / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(f.size / 1024)) + " KB")
        + " · " + (f.kind === "pdf" ? "PDF" : f.kind === "text" ? "text" : "unsupported"),
      bad: f.kind === "unsupported",
      remove: this.removeFile(i)
    }));

    return {
      // -- navigation + shared -------------------------------------------
      refresh: this.refresh,
      startProcessing: this.startProcessing, stopProcessing: this.stopProcessing,
      moreBatches: this.moreBatches, moreQueue: this.moreQueue,

      // -- batches --------------------------------------------------------
      batchRows,
      batchesLoading: st.batchList.loading,
      batchesEmpty: !!listed && batchRows.length === 0,
      batchesError: !!st.batchList.error,
      batchesErrorText: errorCopy(st.batchList.error),
      hasMoreBatches: !!(listed && listed.next_cursor),
      moreBatchesLabel: st.moreBusy === "batchList" ? "Loading…" : "Load more batches",

      // -- the selected batch ---------------------------------------------
      hasBatch: !!batch,
      // A brand-new organisation has uploaded nothing. That is the correct
      // resting state and the first screen every customer ever sees (UI.md §9)
      // — an empty queue, never an error.
      noBatch: !st.selectedBatch && !st.batchList.loading && !!listed,
      batchName: batch ? (batch.name || "Untitled batch") : "No batch selected",
      batchMeta: batch
        ? fmtDateTime(batch.created_at) + " · " + batch.domain + " · " + total + (total === 1 ? " resume" : " resumes")
        : "",
      batchStatusLabel: batch ? (BATCH_STATUS[batch.status] || batch.status) : "—",
      batchProgressLabel: settled + " of " + total + " screened",
      batchProgressBar: gradBar(total ? settled / total : 0),
      batchPending: counts ? counts.pending + counts.processing : 0,
      hasPending: !!(counts && counts.pending + counts.processing > 0),
      batchFailed: counts ? counts.failed : 0,
      hasFailed: !!(counts && counts.failed > 0),
      queueLoading: st.queue.loading || st.summary.loading,
      queueError: !!(st.queue.error || st.summary.error || st.batch.error),
      queueErrorText: errorCopy(st.queue.error || st.summary.error || st.batch.error),

      // -- the driver ------------------------------------------------------
      driving: st.driving,
      driveLabel: st.driving ? "Stop screening" : (settled >= total && total > 0 ? "All screened" : "Start screening"),
      canDrive: !!(counts && counts.pending + counts.processing > 0),
      // With nothing left to screen the button is inert rather than firing a
      // call the server answers 0/0/0 to. An affordance that does nothing is
      // the same mistake as one that always fails.
      driveBtn: st.driving ? GHOST_BTN
        : (counts && counts.pending + counts.processing > 0 ? SMALL_PRIMARY_FLAT : SMALL_MUTED),
      driveAction: st.driving ? this.stopProcessing
        : (counts && counts.pending + counts.processing > 0 ? this.startProcessing : this.noop),
      driveStatus: st.driving
        ? "Screening from this browser — " + st.driveDone + " done, " + st.driveFailed
          + " failed this run. Leave the page and the batch pauses; it resumes where it stopped."
        : (counts && counts.pending + counts.processing > 0
            ? (counts.pending + counts.processing) + " not screened yet. Nothing runs until you start it — each resume is a full evaluation."
            : "Nothing left to screen."),
      driveError: !!st.driveError,
      driveErrorText: this.screeningErrorCopy(st.driveError),

      // -- queue -----------------------------------------------------------
      candidates: queueRows,
      queueEmpty: !!queue && queueRows.length === 0,
      // No paging WHILE screening runs. The queue's sort key is
      // COALESCE(risk_score, -1) and processing an item moves it from null to
      // a score, so during a run the key is MUTABLE — the same limitation
      // SCREENING.md §6 states for the curation queue, and keyset paging is
      // stable against inserts, not against re-observation. Each tick reloads
      // page one anyway.
      hasMoreQueue: !!(queue && queue.next_cursor) && !st.driving,
      moreQueueLabel: st.moreBusy === "queue" ? "Loading…" : "Load more",
      bandElevated: byBand.elevated || 0,
      bandModerate: byBand.moderate || 0,
      bandLow: byBand.low || 0,
      bandInsufficient: byBand.insufficient_data || 0,

      // -- summary ---------------------------------------------------------
      hasSummary: !!sum,
      summaryScreened: nScreened,
      summaryHeadline: sum
        ? "What we found in " + nScreened + (nScreened === 1 ? " screened resume" : " screened resumes")
        : "Nothing screened yet",
      summaryMeta: sum
        ? (BATCH_STATUS[sum.status] || sum.status) + " · " + settled + " of " + total
          + " processed. Advisory throughout: every one of these is a reason to look closer, not a decision."
        : "",
      shareElevated: share(byBand.elevated || 0),
      shareModerate: share(byBand.moderate || 0),
      shareLow: share(byBand.low || 0),
      shareInsufficient: share(byBand.insufficient_data || 0),
      // top_signals holds the three fixed component ids and a count each —
      // never a name, never a row (SCREENING.md §5).
      topSignals: sum && sum.top_signals.length
        ? sum.top_signals.map((s) => ({
            label: SIGNAL_LABEL[s.signal] || s.signal,
            count: s.count,
            bar: gradBar(sum.top_signals[0].count ? s.count / sum.top_signals[0].count : 0)
          }))
        : [],
      noSignals: !!sum && sum.top_signals.length === 0,

      ...this.reportValues(),

      // -- upload ----------------------------------------------------------
      files,
      hasFiles: files.length > 0,
      fileCountLabel: files.length + (files.length === 1 ? " file ready" : " files ready"),
      pickFiles: this.pickFiles, clearFiles: this.clearFiles, submitUpload: this.submitUpload,
      batchNameInput: st.batchNameInput, setBatchNameInput: this.setBatchNameInput,
      uploadLabel: st.uploadBusy ? "Registering…" : "Register batch and start screening",
      uploadError: !!st.uploadError,
      uploadErrorText: errorCopy(st.uploadError),
      uploadErrorBox: ERROR_BOX
    };
  }
  };
})(window);
