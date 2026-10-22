/* Curation handlers and values for the existing DCLogic component.
 * Shared state, navigation and lifecycle remain in the composed component.
 */
(function (global) {
  "use strict";

  global.VeritasCuration = (Base, { API, EVAL_TIMEOUT_MS, errorCopy, IDLE }) => class extends Base {
  // Source-owned curation snapshots and explicit reviewer vocabulary.
  validCurationTerm = (t) => t && typeof t.norm_key === "string" && t.norm_key
    && Array.from(t.norm_key).length <= 128
    && typeof t.display_name === "string" && t.display_name && Array.from(t.display_name).length <= 128
    && typeof t.review_revision === "string" && /^[0-9a-f]{64}$/.test(t.review_revision)
    && Number.isSafeInteger(t.occurrences) && t.occurrences > 0
    && Array.isArray(t.source_types) && t.source_types.length > 0
    && t.source_types.every(s => typeof s === "string" && s && s.length <= 64)
    && new Set(t.source_types).size === t.source_types.length && t.status === "pending"
    && typeof t.first_seen === "string" && Number.isFinite(Date.parse(t.first_seen))
    && typeof t.last_seen === "string" && Number.isFinite(Date.parse(t.last_seen))
    && Date.parse(t.first_seen) <= Date.parse(t.last_seen);
  curationReady = () => !this._gone && this.state.me?.kind === "admin" && this.state.screen === "curation"
    && !this._curationReview && !this.state.curationList.loading && !this.state.curationList.error
    && !!this.state.curationList.data && !this.state.curationNeedsRefresh;
  curationErrorCopy = (err) => err?.status === 403 && err.kind !== "csrf"
    ? "This account is not permitted to review the shared curation queue."
    : errorCopy(err) + (err?.ambiguous ? " The decision may have completed. Refresh queue before reviewing again." : "");
  clearCuration = () => {
    const pending = !!this._curationReview;
    this._curationLoad = null; this._curationReview = null;
    this.setState({ curationList: IDLE, curationSelection: null, curationAction: "map",
      curationAlias: "", curationCanonical: "", curationCategory: "", curationBusy: false,
      curationError: null, curationNeedsRefresh: false,
      curationNotice: pending ? "A prior decision may have completed. Refresh queue before reviewing again." : "" });
  };
  reloadCuration = () => {
    if (this._curationReview || this.state.curationList.loading) return;
    this.setState({ curationError: null });
    return this.loadCuration(false);
  };
  moreCuration = () => this.loadCuration(true);
  loadCuration = async (append) => {
    const st = this.state, me = st.me;
    if (this._gone || me?.kind !== "admin" || st.screen !== "curation"
        || this._curationReview || st.curationList.loading) return;
    const old = append ? st.curationList.data : null;
    if (append && (!old?.next_cursor || st.curationNeedsRefresh)) return;
    const token = this._curationLoad = {};
    const current = () => !this._gone && this._curationLoad === token && this.state.me === me
      && this.state.screen === "curation";
    this.setState({ curationList: { loading: true, data: old, error: null } });
    const path = "/curation/skills/unmapped?status=pending&limit=20"
      + (old ? "&cursor=" + encodeURIComponent(old.next_cursor) : "");
    try {
      const page = await API.get(path, { timeoutMs: EVAL_TIMEOUT_MS });
      if (!current()) return;
      if (!page || !Array.isArray(page.terms) || page.terms.length > 20 || !page.terms.every(this.validCurationTerm)
          || new Set(page.terms.map(t => t.norm_key)).size !== page.terms.length
          || !(page.next_cursor === null || typeof page.next_cursor === "string" && page.next_cursor && page.next_cursor.length <= 2048)
          || !page.terms.length && page.next_cursor !== null
          || old && page.next_cursor === old.next_cursor)
        throw { detail: "The server returned invalid review data. Refresh queue before deciding." };
      const terms = [...new Map((old ? old.terms.concat(page.terms) : page.terms).map(t => [t.norm_key, t])).values()];
      const selected = this.state.curationSelection;
      const retained = selected && terms.find(t => t.norm_key === selected.norm_key && t.review_revision === selected.review_revision);
      this.setState({ curationList: { loading: false, data: { terms, next_cursor: page.next_cursor }, error: null },
        curationNeedsRefresh: false,
        ...(selected && !retained ? { curationSelection: null, curationAlias: "", curationCanonical: "", curationCategory: "" }
          : retained ? { curationSelection: retained } : {}) });
    } catch (err) {
      if (!current() || err?.kind === "session_lost") return;
      this.setState({ curationList: { loading: false, data: null, error: err },
        ...(!this.state.curationNeedsRefresh ? { curationSelection: null, curationAlias: "", curationCanonical: "", curationCategory: "" } : {}) });
    } finally { if (current()) this._curationLoad = null; }
  };
  selectCuration = (term) => () => {
    if (!this.curationReady() || !this.state.curationList.data.terms.includes(term)) return;
    this.setState({ curationSelection: term, curationAction: "map", curationAlias: "", curationCanonical: "",
      curationCategory: "", curationError: null, curationNotice: "" });
  };
  cancelCuration = () => {
    if (this._curationReview) return;
    this.setState({ curationSelection: null, curationAlias: "", curationCanonical: "", curationCategory: "" });
  };
  setCurationAction = (e) => { if (this.curationReady()) this.setState({ curationAction: e.target.value }); };
  setCurationAlias = (e) => { if (this.curationReady()) this.setState({ curationAlias: e.target.value }); };
  setCurationCanonical = (e) => { if (this.curationReady()) this.setState({ curationCanonical: e.target.value }); };
  setCurationCategory = (e) => { if (this.curationReady()) this.setState({ curationCategory: e.target.value }); };
  approveCuration = () => {
    const st = this.state;
    if (!st.curationSelection) return;
    return this.decideCuration({ norm_key: st.curationSelection.norm_key,
      expected_revision: st.curationSelection.review_revision, action: st.curationAction,
      alias: st.curationAlias.trim(), canonical: st.curationCanonical.trim(), category: st.curationCategory.trim() });
  };
  ignoreCuration = (term) => () => this.decideCuration({ norm_key: term.norm_key,
    expected_revision: term.review_revision, action: "ignore" });
  decideCuration = async (body) => {
    const me = this.state.me;
    if (!this.curationReady() || !this.state.curationList.data.terms.some(t =>
        t.norm_key === body.norm_key && t.review_revision === body.expected_revision && this.validCurationTerm(t))) return;
    if (!["map", "create", "ignore"].includes(body.action) || body.action !== "ignore"
        && (!body.alias || !body.canonical || !body.category)) {
      this.setState({ curationError: { detail: "Supply an approved alias, canonical ID and category." } }); return;
    }
    const token = this._curationReview = {};
    const current = () => !this._gone && this._curationReview === token && this.state.me === me
      && this.state.screen === "curation";
    this.setState({ curationBusy: true, curationError: null, curationNotice: "" });
    let refresh = false;
    try {
      const result = await API.post("/curation/skills/resolve", body, { timeoutMs: EVAL_TIMEOUT_MS });
      if (!current()) return;
      if (!result || result.action !== body.action || result.alias !== (body.alias ?? null)
          || result.canonical !== (body.canonical ?? null) || result.category !== (body.category ?? null)
          || typeof result.decided_at !== "string" || !Number.isFinite(Date.parse(result.decided_at))
          || !(result.admin_user_id === null || typeof result.admin_user_id === "string" && result.admin_user_id)
          || Object.keys(result).some(k => !["action", "alias", "canonical", "category", "decided_at", "admin_user_id"].includes(k)))
        throw { kind: "invalid_response", detail: "The server returned an invalid decision receipt." };
      this.setState({ curationSelection: null, curationAlias: "", curationCanonical: "", curationCategory: "",
        curationNotice: body.action === "ignore" ? "Term ignored." : "Vocabulary approved." });
      refresh = true;
    } catch (err) {
      if (!current() || err?.kind === "session_lost") return;
      const stale = err?.status === 409 && /^review snapshot changed/.test(err.detail || "");
      const missing = err?.kind === "not_found" || err?.status === 404;
      const ambiguous = ["timeout", "network", "invalid_response"].includes(err?.kind) || err?.status >= 500;
      this.setState({ curationError: missing ? { detail: "Term is no longer available. Refresh or select another term." }
        : stale ? { detail: "The review changed. Select the term again from the refreshed queue before deciding." }
        : { ...err, ambiguous }, curationNeedsRefresh: ambiguous || stale || missing,
        ...(stale || missing ? { curationSelection: null, curationAlias: "", curationCanonical: "", curationCategory: "" } : {}) });
      refresh = stale || missing;
    } finally {
      if (current()) { this._curationReview = null; this.setState({ curationBusy: false }); }
    }
    if (refresh && !this._gone && this.state.me === me && this.state.screen === "curation") return this.loadCuration(false);
  };

  curationValues() {
    const st = this.state;
    const me = st.me || {};
    const curationAllowed = me.kind === "admin" && st.screen === "curation";
    const curationData = curationAllowed ? st.curationList.data : null;
    return {
      curationAllowed, curationDenied: st.screen === "curation" && !curationAllowed,
      curation: (curationData?.terms || []).map(t => ({
        key: t.norm_key, term: t.display_name, sources: t.source_types.join(", "), count: t.occurrences,
        review: this.selectCuration(t), ignore: this.ignoreCuration(t)
      })),
      curationLoading: curationAllowed && st.curationList.loading,
      curationBusy: curationAllowed && (st.curationBusy || st.curationList.loading),
      curationControlsDisabled: !this.curationReady(),
      curationError: curationAllowed && !!(st.curationError || st.curationList.error),
      curationErrorText: curationAllowed ? this.curationErrorCopy(st.curationError || st.curationList.error) : "",
      curationNotice: curationAllowed ? st.curationNotice : "",
      curationNeedsRefresh: curationAllowed && st.curationNeedsRefresh,
      curationHasData: !!curationData, curationLoaded: curationData?.terms.length || 0,
      curationEmpty: !!curationData && !curationData.terms.length,
      curationMore: !!curationData?.next_cursor,
      curationSelected: curationAllowed && !!st.curationSelection,
      curationSelectedName: curationAllowed && st.curationSelection ? st.curationSelection.display_name : "",
      curationAlias: curationAllowed ? st.curationAlias : "", curationCanonical: curationAllowed ? st.curationCanonical : "",
      curationCategory: curationAllowed ? st.curationCategory : "", curationAction: curationAllowed ? st.curationAction : "map",
      reloadCuration: this.reloadCuration, moreCuration: this.moreCuration,
      setCurationAlias: this.setCurationAlias, setCurationCanonical: this.setCurationCanonical,
      setCurationCategory: this.setCurationCategory, setCurationAction: this.setCurationAction,
      approveCuration: this.approveCuration, cancelCuration: this.cancelCuration,
    };
  }
  };
})(window);
