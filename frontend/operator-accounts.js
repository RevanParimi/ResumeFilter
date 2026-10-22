/* Operator-account handlers and view values for the existing DCLogic component.
 * Explicit shared helpers preserve its plain-script runtime and bound callbacks.
 */
(function (global) {
  "use strict";

  global.VeritasOperatorAccounts = (Base, { API, EVAL_TIMEOUT_MS, errorCopy, fmtDate }) => class extends Base {
  // Operator accounts have one fixed platform role; emails are hashed at rest.
  validUser = (u) => u && typeof u.id === "string" && u.id && typeof u.label === "string"
    && typeof u.created_at === "string" && (u.disabled_at === null || typeof u.disabled_at === "string");
  usersErrorCopy = (err) => err?.status === 403 && err.kind !== "csrf"
    ? "This account is not permitted to administer operator accounts." : errorCopy(err);
  loadUserAdmin = () => {
    const me = this.state.me;
    if (this._gone || me?.kind !== "admin" || this.state.screen !== "adminusers") return;
    const token = this._usersLoad = {};
    const current = () => !this._gone && this.state.me === me && this._usersLoad === token
      && this.state.screen === "adminusers";
    this.setState({ usersConfirm: null });
    return this.load("usersList", () => API.get("/admin/users", { timeoutMs: EVAL_TIMEOUT_MS }).then(rows => {
      if (!Array.isArray(rows) || !rows.every(this.validUser) || new Set(rows.map(u => u.id)).size !== rows.length)
        throw { detail: "The server returned invalid operator data. Refresh before making changes." };
      return rows;
    }), current).then(rows => {
      if (!rows || !current()) return;
      const count = rows.filter(u => (u.label + " " + u.id).toLowerCase().includes(this.state.usersFilter.toLowerCase())).length;
      this.setState({ usersPage: Math.min(this.state.usersPage, Math.max(0, Math.ceil(count / 20) - 1)) });
    });
  };
  reloadUsers = () => { if (!this._usersAction) return this.loadUserAdmin(); };
  setUsersEmail = (e) => { if (!this._usersAction) this.setState({ usersEmail: e.target.value, usersError: null, usersNotice: "" }); };
  setUsersLabel = (e) => { if (!this._usersAction) this.setState({ usersLabel: e.target.value, usersError: null, usersNotice: "" }); };
  setUsersFilter = (e) => this.setState({ usersFilter: e.target.value, usersPage: 0 });
  prevUsers = () => this.setState(s => ({ usersPage: Math.max(0, s.usersPage - 1) }));
  nextUsers = () => { if (!this.renderVals().usersNextDisabled) this.setState(s => ({ usersPage: s.usersPage + 1 })); };
  armUserDelete = (id) => () => {
    const st = this.state;
    if (st.me?.kind !== "admin" || st.screen !== "adminusers" || this._usersAction
        || st.usersList.loading || st.usersList.error || !(st.usersList.data || []).some(u => u.id === id)) return;
    this.setState({ usersConfirm: id, usersError: null, usersNotice: "" });
  };
  cancelUserDelete = () => { if (!this._usersAction) this.setState({ usersConfirm: null }); };
  confirmUserDelete = () => { if (this.state.usersConfirm) return this.changeUser("delete"); };
  createUser = () => this.changeUser("create");
  changeUser = async (action) => {
    const st = this.state, me = st.me;
    if (this._gone || this._usersAction || me?.kind !== "admin" || st.screen !== "adminusers"
        || st.usersList.loading || st.usersList.error) return;
    const email = st.usersEmail.trim(), label = st.usersLabel.trim();
    const target = (st.usersList.data || []).find(u => u.id === st.usersConfirm);
    if (action === "delete" && !target || !["create", "delete"].includes(action)) return;
    if (action === "create" && (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) || email.length > 254 || label.length > 200)) {
      this.setState({ usersError: { detail: "Enter a valid sign-in email (up to 254 characters) and a label of up to 200 characters." } }); return;
    }
    const token = this._usersAction = {};
    const current = () => !this._gone && this._usersAction === token && this.state.me === me
      && this.state.screen === "adminusers";
    this.setState({ usersBusy: true, usersError: null, usersNotice: "", usersConfirm: null });
    try {
      const opts = { timeoutMs: EVAL_TIMEOUT_MS };
      const result = action === "create" ? await API.post("/admin/users", { email, label }, opts)
        : await API.del("/admin/users/" + encodeURIComponent(target.id), opts);
      if (!current()) return;
      if (action === "create" ? !this.validUser(result) : result?.admin_user_id !== target.id || result.deleted !== true)
        throw { detail: "The server returned an unexpected change result. Refresh before retrying; the change may have completed." };
      this.setState({ usersNotice: action === "create" ? "Operator account created. The person can request a sign-in code."
          : "Operator account deleted. Its sessions have been revoked.",
        ...(action === "create" ? { usersEmail: "", usersLabel: "", usersFilter: "", usersPage: 0 } : {}) });
      // This also detects self deletion: the next authenticated read is a 401.
      await this.loadUserAdmin();
    } catch (err) {
      if (!current() || err?.kind === "session_lost") return;
      this.setState({ usersError: err });
    } finally {
      if (current()) { this._usersAction = null; this.setState({ usersBusy: false }); }
    }
  };

  operatorAccountValues() {
    const st = this.state;
    const me = st.me || {};
    const usersAllowed = me.kind === "admin";
    const usersRows = usersAllowed && !st.usersList.error ? (st.usersList.data || []) : [];
    const usersFiltered = usersRows.filter(u => (u.label + " " + u.id).toLowerCase().includes(st.usersFilter.toLowerCase()));
    const usersPages = Math.max(1, Math.ceil(usersFiltered.length / 20));
    const usersPage = Math.min(st.usersPage, usersPages - 1);
    const usersTarget = usersRows.find(u => u.id === st.usersConfirm);
    return {
      usersAdminAllowed: usersAllowed, usersAdminDenied: !usersAllowed,
      adminUsers: usersFiltered.slice(usersPage * 20, (usersPage + 1) * 20).map(u => ({
        id: u.id, displayLabel: u.label || "Unlabelled operator", role: "Operator",
        status: u.disabled_at === null ? "Enabled" : "Disabled", created: fmtDate(u.created_at), remove: this.armUserDelete(u.id) })),
      usersEmail: usersAllowed ? st.usersEmail : "", usersLabel: usersAllowed ? st.usersLabel : "", usersFilter: st.usersFilter,
      setUsersEmail: this.setUsersEmail, setUsersLabel: this.setUsersLabel, setUsersFilter: this.setUsersFilter,
      createUser: this.createUser, reloadUsers: this.reloadUsers, usersBusy: st.usersBusy,
      usersControlsDisabled: st.usersBusy || st.usersList.loading || !!st.usersList.error,
      usersLoading: st.usersList.loading, usersListError: !!st.usersList.error,
      usersListErrorText: this.usersErrorCopy(st.usersList.error),
      usersActionError: !!st.usersError, usersActionErrorText: this.usersErrorCopy(st.usersError) + (st.usersError &&
        (["network", "timeout"].includes(st.usersError.kind) || st.usersError.status >= 500)
        ? " The change may have completed. Refresh operator accounts before retrying." : ""),
      usersNotice: st.usersNotice,
      usersEmpty: usersAllowed && !!st.usersList.data && !st.usersList.loading && !st.usersList.error && !usersFiltered.length,
      usersPageLabel: "Page " + (usersPage + 1) + " of " + usersPages + " · " + usersFiltered.length + " operator accounts",
      usersPrevDisabled: usersPage === 0, usersNextDisabled: usersPage + 1 >= usersPages,
      prevUsers: this.prevUsers, nextUsers: this.nextUsers,
      usersConfirm: !!usersTarget, cancelUserDelete: this.cancelUserDelete, confirmUserDelete: this.confirmUserDelete,
      usersConfirmCopy: "Permanently delete " + (usersTarget?.label || "this operator") + " (" + (usersTarget?.id || "")
        + ")? All its sessions are revoked. If this is your own account, your sign-in ends immediately. The API allows deleting the last operator; recovery needs another operator or the configured machine admin key. This cannot be undone.",
    };
  }
  };
})(window);
