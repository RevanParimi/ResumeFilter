/* Organization-administration handlers and values for the existing DCLogic component.
 * Shared state and lifecycle remain in the composed component.
 */
(function (global) {
  "use strict";

  global.VeritasOrganizationAdmin = (Base, { API, EVAL_TIMEOUT_MS, errorCopy, fmtDate, stateChip }) => class extends Base {
  // Existing org APIs return all rows; paging/filtering here is local.
  validOrg = (o) => o && typeof o.id === "string" && o.id && typeof o.name === "string"
    && typeof o.status === "string" && typeof o.created_at === "string"
    && Number.isFinite(o.reliability_weight) && o.reliability_weight >= 0;
  orgErrorCopy = (err) => err?.status === 403 && err.kind !== "csrf"
    ? "This account is not permitted to administer organisations." : errorCopy(err);
  loadOrgAdmin = () => {
    const me = this.state.me;
    if (!me || me.kind !== "admin" || this._gone) return;
    const token = this._orgLoad = {};
    const current = () => !this._gone && this.state.me === me && this._orgLoad === token
      && this.state.screen === "adminorgs";
    return this.load("orgList", () => API.get("/ledger/orgs", { timeoutMs: EVAL_TIMEOUT_MS }).then(rows => {
      if (!Array.isArray(rows) || !rows.every(this.validOrg) || new Set(rows.map(o => o.id)).size !== rows.length)
        throw { detail: "The server returned invalid organisation data. Refresh before making changes." };
      return rows;
    }), current).then(rows => {
      if (!rows || !current()) return;
      const selected = rows.find(o => o.id === this.state.orgSelection);
      if (!selected) this.setState({ orgSelection: null, orgWeight: "", orgConfirm: null });
      else this.setState({ orgWeight: String(selected.reliability_weight) });
      const count = rows.filter(o => (o.name + " " + o.id).toLowerCase().includes(this.state.orgFilter.toLowerCase())).length;
      this.setState({ orgPage: Math.min(this.state.orgPage, Math.max(0, Math.ceil(count / 20) - 1)) });
    });
  };
  reloadOrgs = () => { if (!this._orgAction) { this.dismissOrgKey(); this.setState({ orgConfirm: null }); return this.loadOrgAdmin(); } };
  setOrgName = (e) => { if (!this._orgAction) this.setState({ orgName: e.target.value, orgError: null, orgNotice: "" }); };
  setOrgWeight = (e) => { if (!this._orgAction) this.setState({ orgWeight: e.target.value, orgError: null, orgNotice: "" }); };
  setOrgFilter = (e) => this.setState({ orgFilter: e.target.value, orgPage: 0 });
  prevOrgs = () => this.setState(s => ({ orgPage: Math.max(0, s.orgPage - 1) }));
  nextOrgs = () => { if (!this.renderVals().orgNextDisabled) this.setState(s => ({ orgPage: s.orgPage + 1 })); };
  dismissOrgKey = () => this.setState({ orgKey: "", orgKeyOwner: "", orgKeyVisible: false });
  toggleOrgKey = () => this.setState(s => ({ orgKeyVisible: !s.orgKeyVisible }));
  selectOrg = (id) => () => {
    if (this._orgAction || this.state.orgList.loading || this.state.me?.kind !== "admin") return;
    const row = (this.state.orgList.data || []).find(o => o.id === id);
    if (!row) return;
    this.dismissOrgKey();
    this.setState({ orgSelection: id, orgWeight: String(row.reliability_weight), orgConfirm: null,
      orgError: null, orgNotice: "" });
  };
  armOrgRotate = () => this.armOrgAction("rotate");
  armOrgDelete = () => this.armOrgAction("delete");
  armOrgAction = (action) => {
    if (this.state.me?.kind === "admin" && this.state.orgSelection && !this._orgAction && !this.state.orgList.loading)
      this.setState({ orgConfirm: { id: this.state.orgSelection, action }, orgError: null, orgNotice: "" });
  };
  cancelOrgConfirm = () => { if (!this._orgAction) this.setState({ orgConfirm: null }); };
  confirmOrgAction = () => {
    const choice = this.state.orgConfirm;
    if (choice && choice.id === this.state.orgSelection) return this.changeOrg(choice.action);
  };
  createOrg = () => this.changeOrg("create");
  saveOrgReliability = () => this.changeOrg("reliability");
  changeOrg = async (action) => {
    const st = this.state, me = st.me;
    if (this._gone || this._orgAction || me?.kind !== "admin" || st.screen !== "adminorgs") return;
    const name = st.orgName.trim(), weight = Number(st.orgWeight);
    const target = (st.orgList.data || []).find(o => o.id === st.orgSelection);
    if (action !== "create" && (!target || st.orgList.loading || st.orgList.error)) return;
    if (action === "create" && (!name || name.length > 200)) {
      this.setState({ orgError: { detail: "Enter an organisation name of 1 to 200 characters." } }); return;
    }
    if (action === "reliability" && (!st.orgWeight.trim() || !Number.isFinite(weight) || weight < 0)) {
      this.setState({ orgError: { detail: "Enter a finite reliability multiplier of 0 or greater." } }); return;
    }
    if (["rotate", "delete"].includes(action) && (st.orgConfirm?.id !== target.id || st.orgConfirm?.action !== action)) return;
    const token = this._orgAction = {};
    const current = () => !this._gone && this._orgAction === token && this.state.me === me;
    const visible = () => current() && this.state.screen === "adminorgs";
    this.setState({ orgBusy: true, orgError: null, orgNotice: "", orgConfirm: null,
      orgKey: "", orgKeyOwner: "", orgKeyVisible: false });
    try {
      const path = "/ledger/orgs" + (target && action !== "create" ? "/" + encodeURIComponent(target.id) : "");
      const opts = { timeoutMs: EVAL_TIMEOUT_MS };
      const result = action === "delete" ? await API.del(path, opts)
        : await API.post(path + (action === "rotate" ? "/api-key" : action === "reliability" ? "/reliability" : ""),
            action === "create" ? { name } : action === "reliability" ? { weight } : {}, opts);
      if (!visible()) return;
      if (action === "create" && (!this.validOrg(result?.org) || typeof result.api_key !== "string" || !result.api_key)
          || action === "reliability" && (!this.validOrg(result) || result.id !== target.id)
          || action === "rotate" && (result?.org_id !== target.id || typeof result.api_key !== "string" || !result.api_key)
          || action === "delete" && (result?.org_id !== target.id || result.deleted !== true))
        throw { detail: "The server returned an unexpected change result. Refresh before retrying; the change may have completed." };
      const id = action === "create" ? result.org.id : target.id;
      this.setState({ orgNotice: action === "create" ? "Organisation created." : action === "reliability" ? "Reliability saved."
          : action === "rotate" ? "Organisation key rotated. The previous key no longer works." : "Organisation offboarded.",
        orgSelection: action === "delete" ? null : id,
        ...(action === "create" ? { orgName: "", orgFilter: "", orgPage: 0 } : {}),
        ...(["create", "rotate"].includes(action) ? { orgKey: result.api_key, orgKeyOwner: action === "create" ? result.org.name : target.name } : {}) });
      await this.loadOrgAdmin();
    } catch (err) {
      if (!visible() || err?.kind === "session_lost") return;
      this.setState({ orgError: err });
    } finally {
      if (current()) { this._orgAction = null; this.setState({ orgBusy: false }); }
    }
  };

  organizationAdminValues() {
    const st = this.state;
    const me = st.me || {};
    const orgAllowed = me.kind === "admin";
    const orgRows = orgAllowed && !st.orgList.error ? (st.orgList.data || []) : [];
    const orgFiltered = orgRows.filter(o => (o.name + " " + o.id).toLowerCase().includes(st.orgFilter.toLowerCase()));
    const orgPages = Math.max(1, Math.ceil(orgFiltered.length / 20));
    const orgPage = Math.min(st.orgPage, orgPages - 1);
    const orgSelected = orgRows.find(o => o.id === st.orgSelection);
    const orgDisabled = st.orgBusy || st.orgList.loading || !!st.orgList.error;
    return {
      orgAdminAllowed: orgAllowed, orgAdminDenied: !orgAllowed,
      adminOrgs: orgFiltered.slice(orgPage * 20, (orgPage + 1) * 20).map(o => ({ ...o,
        created: fmtDate(o.created_at), chip: stateChip(o.status === "active"), inspect: this.selectOrg(o.id) })),
      orgSelected: orgSelected ? { ...orgSelected, created: fmtDate(orgSelected.created_at) } : null,
      orgName: st.orgName, orgWeight: st.orgWeight, orgFilter: st.orgFilter,
      setOrgName: this.setOrgName, setOrgWeight: this.setOrgWeight, setOrgFilter: this.setOrgFilter,
      createOrg: this.createOrg, saveOrgReliability: this.saveOrgReliability, reloadOrgs: this.reloadOrgs,
      orgBusy: st.orgBusy, orgControlsDisabled: orgDisabled,
      orgNotice: st.orgNotice, orgActionError: !!st.orgError,
      orgActionErrorText: this.orgErrorCopy(st.orgError) + (st.orgError &&
        (["network", "timeout"].includes(st.orgError.kind) || st.orgError.status >= 500)
        ? " The change may have completed. Refresh organisations before retrying. A lost key response cannot be retrieved; rotation needs another explicit confirmation." : ""),
      orgListLoading: st.orgList.loading, orgListError: !!st.orgList.error,
      orgListErrorText: this.orgErrorCopy(st.orgList.error),
      orgEmpty: orgAllowed && !!st.orgList.data && !st.orgList.loading && !st.orgList.error && !orgFiltered.length,
      orgPrevDisabled: orgPage === 0, orgNextDisabled: orgPage + 1 >= orgPages,
      orgPageLabel: "Page " + (orgPage + 1) + " of " + orgPages + " · " + orgFiltered.length + " organisations",
      prevOrgs: this.prevOrgs, nextOrgs: this.nextOrgs,
      orgConfirm: !!st.orgConfirm, armOrgRotate: this.armOrgRotate, armOrgDelete: this.armOrgDelete,
      cancelOrgConfirm: this.cancelOrgConfirm, confirmOrgAction: this.confirmOrgAction,
      orgConfirmLabel: st.orgConfirm?.action === "rotate" ? "Confirm key rotation" : "Confirm offboarding",
      orgConfirmCopy: st.orgConfirm?.action === "rotate"
        ? "Rotate the key for " + (orgSelected?.name || "this organisation") + "? The previous machine key stops working immediately. Existing sign-in sessions remain. Save the replacement securely when returned."
        : "Permanently offboard " + (orgSelected?.name || "this organisation") + "? This deletes its dependent records, jobs, grants and memberships. Candidates and historical reports/judgements can remain. This cannot be undone.",
      orgHasKey: orgAllowed && !!st.orgKey, orgKey: orgAllowed ? st.orgKey : "", orgKeyOwner: orgAllowed ? st.orgKeyOwner : "",
      orgKeyType: st.orgKeyVisible ? "text" : "password", orgKeyToggleLabel: st.orgKeyVisible ? "Conceal API key" : "Reveal API key",
      toggleOrgKey: this.toggleOrgKey, dismissOrgKey: this.dismissOrgKey,
    };
  }
  };
})(window);
