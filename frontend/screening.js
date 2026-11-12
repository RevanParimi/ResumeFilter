/* Screening intake, batches, processing and view values for DCLogic.
 * Shared state, navigation, lifecycle, row cache and file reading stay in the component.
 */
(function (global) {
  "use strict";

  global.VeritasScreening = (Base, {
    API, EVAL_TIMEOUT_MS, errorCopy, IDLE, BATCH_STATUS, ITEM_STATUS, RISK_BAND, BAND,
    SIGNAL_LABEL, SUB_BAND_LABEL, SMALL_MUTED, SMALL_GHOST, GHOST_BTN,
    SMALL_PRIMARY_FLAT, ERROR_BOX, fmtDate, fmtDateTime, gradBar, shortId,
    avatar, chip, num, riskBar, confBarStyle
  }) => class extends Base {
  _batchListRequest = null;
  _batchReadRequest = null;
  _batchPageRequest = null;
  _uploadRequest = null;
  _uploadCheckRequest = null;
  _batchChangeRequests = new Map();

  setBatchChange = (id, patch) => this.setState(s => ({
    batchChanges: Object.assign({}, s.batchChanges, {
      [id]: Object.assign({}, (s.batchChanges || {})[id], patch)
    })
  }));
  batchChangeBlocked = (id) => {
    const change = (this.state.batchChanges || {})[id];
    return this._batchChangeRequests.has(id) || !!(change && (change.busy || change.uncertain));
  };
  forgetBatch = (id) => {
    const selected = this.state.selectedBatch === id;
    if (selected) {
      this._viewBatch = this._batchReadRequest = this._batchPageRequest = null;
      this._driving = false;
    }
    this.setState({
      selectedBatch: selected ? null : this.state.selectedBatch,
      driving: selected ? false : this.state.driving,
      queue: selected ? IDLE : this.state.queue,
      summary: selected ? IDLE : this.state.summary,
      batch: selected ? IDLE : this.state.batch
    });
  };
  changeBatch = async (id, action) => {
    const me = this.state.me;
    if (!id || !me || this._gone || this.batchChangeBlocked(id)) return;
    const token = {};
    this._batchChangeRequests.set(id, token);
    const still = () => !this._gone && this.state.me === me && this._batchChangeRequests.get(id) === token;
    if (this._driveBatch === id) this._halt();
    this.setBatchChange(id, { action, busy: true, uncertain: false, checked: false, error: null, notice: '' });
    try {
      const path = '/screening/batches/' + encodeURIComponent(id);
      const result = await (action === 'delete'
        ? API.del(path, { timeoutMs: EVAL_TIMEOUT_MS })
        : API.post(path + '/retry', {}, { timeoutMs: EVAL_TIMEOUT_MS }));
      if (!still()) return;
      this._batchChangeRequests.delete(id);
      this.setBatchChange(id, { busy: false, notice: action === 'delete' ? 'Batch deleted.'
        : (result.requeued || 0) + ' queued, ' + (result.skipped || 0)
          + ' skipped because fresh input is needed. Check the saved batch, then choose Start screening when ready.' });
      if (action === 'delete') this.forgetBatch(id);
      else if (this.state.selectedBatch === id) this.refreshBatch(id);
      this.loadBatches();
    } catch (error) {
      if (!still()) return;
      this._batchChangeRequests.delete(id);
      if (error && error.kind === 'session_lost') return;
      const refused = error && ['batch_mutation_capacity_exhausted', 'batch_mutation_executor_closed'].includes(error.detail);
      const uncertain = !refused && (!error || !error.status || error.status >= 500);
      this.setBatchChange(id, { busy: false, error, uncertain, checked: false });
    }
  };
  retryFailed = () => {
    const id = this.state.selectedBatch;
    const counts = (this.state.batch.data && this.state.batch.data.counts)
      || (this.state.summary.data && this.state.summary.data.counts);
    if (!id || !counts || !counts.failed) return;
    return this.changeBatch(id, 'retry');
  };
  checkBatchChange = async (id) => {
    const me = this.state.me, change = (this.state.batchChanges || {})[id];
    if (!me || this._gone || !change || !change.uncertain || this._batchChangeRequests.has(id)) return;
    const token = {};
    this._batchChangeRequests.set(id, token);
    const still = () => !this._gone && this.state.me === me && this._batchChangeRequests.get(id) === token;
    this.setBatchChange(id, { checking: true });
    try {
      const saved = await API.get('/screening/batches/' + encodeURIComponent(id), { timeoutMs: EVAL_TIMEOUT_MS });
      if (!still()) return;
      this._batchChangeRequests.delete(id);
      this.setBatchChange(id, { checking: false, checked: true,
        notice: 'Saved batch found. An earlier change may still finish later. Check again before repeating it.' });
      if (this.state.selectedBatch === id) this.refreshBatch(saved.id);
      this.loadBatches();
    } catch (error) {
      if (!still()) return;
      this._batchChangeRequests.delete(id);
      const absent = error && error.status === 404;
      this.setBatchChange(id, { checking: false, checked: !!absent, notice: absent
        ? 'This batch is not visible to this account. An earlier change may still finish later.'
        : 'Saved state could not be checked. Wait, then Check saved state again.' });
      if (absent) { this.forgetBatch(id); this.loadBatches(); }
    }
  };
  allowBatchChange = (id) => {
    const change = (this.state.batchChanges || {})[id];
    if (this._batchChangeRequests.has(id) || !change || !change.checked) return;
    this.setBatchChange(id, { uncertain: false, error: null,
      notice: 'Another change is now allowed. An earlier change may still finish later; nothing was repeated automatically.' });
  };
  // ── screening ─────────────────────────────────────────────────────────────
  // Opening the queue with no batch chosen picks the newest, because the list
  // is newest-first server-side. An org that has uploaded nothing lands on an
  // EMPTY QUEUE, not an error — the first screen every new customer sees
  // (UI.md §9).
  loadScreening = () => {
    if (this.state.selectedBatch) return this.refreshBatch();
    const me = this.state.me, screen = this.state.screen;
    return this.loadBatches().then((page) => {
      if (this._gone || this.state.me !== me || this.state.screen !== screen || this.state.selectedBatch) return;
      const first = page && page.batches && page.batches[0];
      if (first) { this.setState({ selectedBatch: first.id }); return this.refreshBatch(first.id); }
    });
  };

  loadBatches = () => {
    const me = this.state.me, token = this._batchListRequest = {};
    if (this._gone || !me) return Promise.resolve(null);
    this._batchPageRequest = null;
    this.setState({ moreBusy: null });
    return this.load("batchList", () => API.get("/screening/batches", { timeoutMs: EVAL_TIMEOUT_MS }),
      () => !this._gone && this.state.me === me && this._batchListRequest === token);
  };

  // Three reads, one batch: detail carries progress, summary carries the
  // whole-batch band counts the header shows, queue carries the ranked page.
  // The header's numbers come from SUMMARY on purpose (spec 0.6) — over a paged
  // list, "11 elevated" computed from one page would silently mean
  // "11 on this page".
  refreshBatch = (id) => {
    const batchId = id || this.state.selectedBatch;
    const me = this.state.me;
    if (!batchId || this._gone || !me) return Promise.resolve(null);
    // Tracked in an instance field, not state: the guard has to be correct the
    // instant the user clicks, and setState has not flushed by then.
    this._viewBatch = batchId;
    const token = this._batchReadRequest = {};
    this._batchPageRequest = null;
    this.setState({ moreBusy: null });
    const still = () => !this._gone && this.state.me === me && this._viewBatch === batchId
      && this._batchReadRequest === token;
    return Promise.all([
      this.load("batch", () => API.get("/screening/batches/" + batchId, { timeoutMs: EVAL_TIMEOUT_MS }), still),
      this.load("summary", () => API.get("/screening/batches/" + batchId + "/summary", { timeoutMs: EVAL_TIMEOUT_MS }), still),
      this.load("queue", () => API.get("/screening/batches/" + batchId + "/queue", { timeoutMs: EVAL_TIMEOUT_MS }), still)
    ]);
  };
  refresh = () => this.state.selectedBatch ? this.refreshBatch() : this.loadScreening();

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
    const me = this.state.me, batchId = this.state.selectedBatch;
    if (!cursor || this.state[key].loading || this.state.moreBusy === key || this._gone || !me) return;
    const token = this._batchPageRequest = {};
    const still = () => !this._gone && this.state.me === me && this._batchPageRequest === token
      && this.state[key].data === held && (key !== "queue" || this.state.selectedBatch === batchId);
    this.setState({ moreBusy: key });
    API.get(path + (path.indexOf("?") === -1 ? "?" : "&") + "cursor=" + encodeURIComponent(cursor),
      { timeoutMs: EVAL_TIMEOUT_MS }).then(
      (page) => { if (still()) this.setState({
        moreBusy: null,
        [key]: { loading: false, error: null, data: Object.assign({}, page, {
          [field]: (held[field] || []).concat(page[field] || [])
        }) }
      }); },
      (err) => { if (still()) this.setState({ moreBusy: null, [key]: { loading: false, data: held, error: err } }); }
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
    if (err && err.detail === 'batch_admission_pending')
      return 'Screening may still be saving a claim or recovered result. Earlier results may already be saved. Wait, then refresh saved state. Assessment will not continue automatically. If the item is still in progress, wait for its claim to expire before choosing Start screening.';
    if (err && ['batch_admission_capacity_exhausted', 'batch_admission_executor_closed'].includes(err.detail))
      return 'Screening is temporarily unavailable. No new work was accepted at this step. Earlier results may already be saved, and a claim may already exist. Wait, refresh saved state, then choose Start screening when ready.';
    if (err && ['batch_read_pending', 'batch_read_capacity_exhausted', 'batch_read_executor_closed'].includes(err.detail))
      return 'Saved batch views are temporarily unavailable. Wait a moment, then refresh. Refreshing reads saved state and does not start screening.';
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
    if (this._driving || !this.state.selectedBatch || this.batchChangeBlocked(this.state.selectedBatch)) return;
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
    if (this.batchChangeBlocked(id)) return;
    this.setState({ deleteArmed: id });
  };
  cancelDelete = (e) => {
    if (e && e.stopPropagation) e.stopPropagation();
    this.setState({ deleteArmed: null });
  };
  confirmDelete = (id) => (e) => {
    if (e && e.stopPropagation) e.stopPropagation();
    this.setState({ deleteArmed: null });
    return this.changeBatch(id, 'delete');
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

  uploadErrorCopy = (err) => {
    if (this.state.uploadUncertain) {
      const recovery = this.state.uploadBatchId
        ? ' Check saved batch after waiting.' : ' Wait, then open Batches to look for the saved registration.';
      if (err && err.status === 404)
        return 'This batch is not visible yet. That does not prove registration failed.' + recovery;
      return 'Registration may still be saving.' + recovery
        + ' Checking saved state does not start screening. A fresh registration can create a duplicate.';
    }
    if (err && ['batch_registration_capacity_exhausted', 'batch_registration_executor_closed'].includes(err.detail))
      return 'Registration is temporarily unavailable. Nothing was registered by this request. Wait, then try again.';
    return errorCopy(err);
  };
  freshUpload = () => {
    if (this._uploadRequest || this.state.uploadCheckBusy) return;
    this._uploadCheckRequest = null;
    this.setState({ uploadUncertain: false, uploadBatchId: null, uploadError: null });
  };
  checkUploadBatch = async () => {
    const id = this.state.uploadBatchId, me = this.state.me, screen = this.state.screen;
    if (!id || !me || this._gone || this.state.uploadCheckBusy) return;
    const token = this._uploadCheckRequest = {};
    const still = () => !this._gone && this.state.me === me && this._uploadCheckRequest === token
      && this.state.uploadBatchId === id;
    this.setState({ uploadCheckBusy: true });
    try {
      await API.get('/screening/batches/' + encodeURIComponent(id), { timeoutMs: EVAL_TIMEOUT_MS });
      if (!still()) return;
      this.setState({ uploadCheckBusy: false, uploadError: null });
      if (this.state.screen === screen && !token.navigated) this.selectBatch(id)();
    } catch (err) {
      if (still()) this.setState({ uploadCheckBusy: false, uploadError: err });
    }
  };

  submitUpload = () => {
    if (this._gone || !this.state.me || this._uploadRequest || this.state.uploadUncertain) return;
    const files = this.state.files;
    if (!files.length) { this.setState({ uploadError: { detail: "Choose at least one resume." } }); return; }
    const bad = files.filter((f) => f.kind === "unsupported");
    if (bad.length) {
      this.setState({ uploadError: { detail:
        "This API reads PDF and plain text only. Remove: " + bad.map((f) => f.name).join(", ") } });
      return;
    }
    const me = this.state.me, screen = this.state.screen;
    const name = this.state.batchNameInput, domain = this.state.domain;
    const token = this._uploadRequest = {};
    const still = () => !this._gone && this.state.me === me && this._uploadRequest === token;
    this.setState({ uploadBusy: true, uploadError: null, uploadNotice: null });
    let sent = false;
    return Promise.all(files.map(this._readFile))
      .then((items) => {
        if (!still()) return null;
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
        sent = true;
        return API.post("/screening/batches", {
          name: (name || "").trim(),
          domain,
          items
        });
      })
      .then((batch) => {
        if (!still() || !batch) return;
        this._uploadRequest = null;
        if (token.navigated || this.state.screen !== screen || this.state.files !== files
            || this.state.batchNameInput !== name || this.state.domain !== domain) {
          this.setState({ uploadBusy: false, uploadUncertain: true, uploadBatchId: batch.id,
            uploadError: { detail: 'saved_batch_available' } });
          return;
        }
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
        if (!still()) return;
        this._uploadRequest = null;
        // A 401 has already sent the user to login; anything on top of that
        // would be a second explanation for one event.
        if (err && err.kind === "session_lost") { this.setState({ uploadBusy: false }); return; }
        const uncertain = sent && (!err || err.detail === 'batch_registration_pending'
          || !err.status || err.status >= 500) && !(err &&
            ['batch_registration_capacity_exhausted', 'batch_registration_executor_closed'].includes(err.detail));
        this.setState({
          uploadBusy: false,
          uploadUncertain: !!uncertain, uploadBatchId: (err && err.batchId) || null,
          uploadError: err && err.local ? err
            : Object.assign({}, err, { detail: this._nameIndex(err && err.detail, files) })
        });
      });
  };

  /* The five screening screens (S8.5). Every value here is one hop from a route
   * in SCREENING.md, so the mapping can be checked without reading other screens. */
  screeningVals() {
    const st = this.state;
    const batchChanges = st.batchChanges || {};
    const changeRows = Object.entries(batchChanges).map(([id, change]) => {
      const refused = change.error && ['batch_mutation_capacity_exhausted', 'batch_mutation_executor_closed'].includes(change.error.detail);
      return {
        id, message: change.busy ? 'Saving batch change…' : change.uncertain
          ? (change.action === 'delete' ? 'Deletion' : 'Retry') + ' may still be saving. Wait, then Check saved state. No change or screening is repeated automatically.'
          : refused ? 'Batch changes are temporarily unavailable. Nothing was changed by this request. Wait, then try again.'
          : change.error ? errorCopy(change.error) : change.notice,
        notice: change.uncertain ? change.notice : '',
        uncertain: !!change.uncertain, checked: !!change.checked,
        checking: !!change.checking,
        check: this.rowHandler('checkBatchChange', id, () => () => this.checkBatchChange(id)),
        allow: this.rowHandler('allowBatchChange', id, () => () => this.allowBatchChange(id))
      };
    });
    const batch = st.batch.data;
    const sum = st.summary.data;
    const queue = st.queue.data;
    const listed = st.batchList.data;
    const readError = st.queue.error || st.summary.error || st.batch.error || (!st.selectedBatch && st.batchList.error);

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
        deleteLabel: batchChanges[b.id] && batchChanges[b.id].busy ? "Saving…" : "Delete",
        deleteDisabled: this.batchChangeBlocked(b.id),
        deleteBtn: this.batchChangeBlocked(b.id) ? SMALL_MUTED : SMALL_GHOST
      };
    }) : [];

    // -- the selected batch's header ---------------------------------------
    const counts = (batch && batch.counts) || (sum && sum.counts) || null;
    const mutationBlocked = this.batchChangeBlocked(st.selectedBatch);
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
      reloadBatches: this.loadBatches,
      batchReference: st.selectedBatch || "",
      hasBatchReference: !!st.selectedBatch,
      startProcessing: this.startProcessing, stopProcessing: this.stopProcessing,
      moreBatches: this.moreBatches, moreQueue: this.moreQueue,

      // -- batches --------------------------------------------------------
      batchRows,
      batchesLoading: st.batchList.loading,
      batchesEmpty: !!listed && batchRows.length === 0 && !listed.next_cursor,
      batchesError: !!st.batchList.error,
      batchesErrorText: this.screeningErrorCopy(st.batchList.error),
      hasMoreBatches: !!(listed && listed.next_cursor) && !st.batchList.loading,
      moreBatchesLabel: st.moreBusy === "batchList" ? "Loading…" : "Load more batches",

      // -- the selected batch ---------------------------------------------
      hasBatch: !!batch,
      // A brand-new organisation has uploaded nothing. That is the correct
      // resting state and the first screen every customer ever sees (UI.md §9)
      // — an empty queue, never an error.
      noBatch: !st.selectedBatch && !st.batchList.loading && !!listed
        && !(listed.batches || []).length && !listed.next_cursor,
      batchDiscoveryMore: !st.selectedBatch && !st.batchList.loading && !!listed
        && !(listed.batches || []).length && !!listed.next_cursor,
      batchName: batch ? (batch.name || "Untitled batch") : sum ? (sum.name || "Untitled batch")
        : st.selectedBatch ? "Batch details unavailable" : "No batch selected",
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
      queueError: !!readError,
      queueErrorText: this.screeningErrorCopy(readError),

      // -- the driver ------------------------------------------------------
      driving: st.driving,
      driveLabel: st.driving ? "Stop screening" : (settled >= total && total > 0 ? "All screened" : "Start screening"),
      canDrive: !mutationBlocked && !!(counts && counts.pending + counts.processing > 0),
      driveDisabled: !st.driving && (mutationBlocked || !(counts && counts.pending + counts.processing > 0)),
      canRetry: !mutationBlocked && !st.driving && !!(counts && counts.failed),
      retryDisabled: mutationBlocked || st.driving || !(counts && counts.failed),
      retryFailed: this.retryFailed,
      showBatchChanges: ['queue', 'summary', 'batches'].includes(st.screen) && changeRows.length > 0,
      batchChangeRows: changeRows,
      // With nothing left to screen the button is inert rather than firing a
      // call the server answers 0/0/0 to. An affordance that does nothing is
      // the same mistake as one that always fails.
      driveBtn: st.driving ? GHOST_BTN
        : (!mutationBlocked && counts && counts.pending + counts.processing > 0 ? SMALL_PRIMARY_FLAT : SMALL_MUTED),
      driveAction: st.driving ? this.stopProcessing
        : (!mutationBlocked && counts && counts.pending + counts.processing > 0 ? this.startProcessing : this.noop),
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
      hasMoreQueue: !!(queue && queue.next_cursor) && !st.driving && !st.queue.loading,
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
      uploadDisabled: !!(st.uploadBusy || st.uploadUncertain),
      uploadUncertain: !!st.uploadUncertain,
      uploadHasReference: !!st.uploadBatchId,
      uploadReference: st.uploadBatchId || '',
      uploadCheckBusy: !!st.uploadCheckBusy,
      checkUploadBatch: this.checkUploadBatch, freshUpload: this.freshUpload,
      uploadError: !!st.uploadError,
      uploadErrorText: this.uploadErrorCopy(st.uploadError),
      uploadErrorBox: ERROR_BOX
    };
  }
  };
})(window);
