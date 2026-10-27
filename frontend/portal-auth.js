/* Authentication, candidate portal and device logic for DCLogic.
 * Shared state, boot/session cleanup, navigation and row cache stay in the component.
 */
(function (global) {
  "use strict";

  global.VeritasPortalAuth = (Base, {
    API, EVAL_TIMEOUT_MS, errorCopy, PLANE_PATH, KIND_TO_PLANE, LANDING,
    otpBoxes, PLANE_HINT, tabBtn, modeBtn, ERROR_BOX, NOTICE_BOX, fieldValue,
    fmtDate, fmtDateTime, stateChip, SMALL_GHOST, SMALL_MUTED, relTime
  }) => class extends Base {
  // ── auth ──────────────────────────────────────────────────────────────────
  setEmailInput = (e) => this.setState({ emailInput: e.target.value, authError: null });
  authErrorCopy = (err) => {
    if (err && err.detail === "auth_code_capacity_exhausted") return "Code requests are busy. Try again shortly.";
    if (err && err.detail === "auth_code_executor_closed") return "Sign-in is temporarily unavailable. Try again shortly.";
    return errorCopy(err);
  };
  setOrgNameInput = (e) => this.setState({ orgNameInput: e.target.value, authError: null });
  onEmailKey = (e) => { if (e.key === "Enter") { e.preventDefault(); this.sendCode(); } };

  sendCode = () => {
    const { plane, authMode, emailInput, orgNameInput } = this.state;
    const email = (emailInput || "").trim();
    if (!email) { this.setState({ authError: { detail: "Enter your email address." } }); return; }
    const p = PLANE_PATH[plane];
    // Operator has no signup route at all — accounts are minted via
    // POST /admin/users by an existing operator.
    const signingUp = authMode === "signup" && plane !== "operator";
    const path = "/auth/" + p + (signingUp ? "/signup" : "/login");
    const body = signingUp && plane === "org"
      ? { email, organization_name: (orgNameInput || "").trim() }
      : { email };
    if (signingUp && plane === "org" && !body.organization_name) {
      this.setState({ authError: { detail: "Enter your organisation name." } });
      return;
    }

    this.setState({ authBusy: true, authError: null, authNotice: null });
    API.post(path, body).then(
      (res) => {
        // A LOCAL api with login_otp_debug_echo on returns the code itself, so
        // a developer is not retyping six digits out of a capture file on every
        // session. Absent in staging and prod — prod refuses to boot with the
        // knob — so this branch simply never fires against a real deployment.
        const echoed = res && res.debug_code;
        this.setState({
          authBusy: false, screen: "verify", otp: otpBoxes(echoed),
          // Signup and login ALWAYS answer 202, known address or not. Never
          // render "no account found" — that would re-open the enumeration hole
          // the backend deliberately closed.
          authNotice: echoed ? "Local API echoed the code — signing you in."
            : "If a code arrives, enter it below. Delivery may still be in progress. Wait before requesting another code."
        });
        // Pass the code EXPLICITLY rather than trusting the setState above to
        // have landed: submitCode reads this.state.otp, and racing it produces
        // an "Enter all six digits" error on a screen that visibly has six.
        if (echoed) this.submitCode(String(echoed));
      },
      (err) => this.setState({ authBusy: false, authError: err })
    );
  };

  resendCode = (e) => {
    if (e && e.preventDefault) e.preventDefault();
    const { plane, emailInput } = this.state;
    // Always the LOGIN route on resend: a second signup for an address already
    // on file is a silent no-op on the org plane.
    API.post("/auth/" + PLANE_PATH[plane] + "/login", { email: (emailInput || "").trim() }).then(
      (res) => {
        // The SAME echo as the first send. Leaving it off here is the exact
        // trap this feature exists to remove: a resend mints a NEW code and
        // kills the previous one, so boxes still holding the old digits are
        // now holding a dead code — and every failure mode of a dead code is
        // reported identically, by design.
        const echoed = res && res.debug_code;
        // Only TOUCH the boxes when a code actually came back. Inside the
        // cooldown the 202 carries no code (the previous one is still live),
        // and blanking six digits somebody just typed would make the resend
        // button destructive.
        this.setState({
          ...(echoed ? { otp: otpBoxes(echoed) } : {}),
          authNotice: echoed
            ? "Local API echoed the new code — signing you in."
            : "If a code arrives, enter it below. Delivery may still be in progress. Wait before requesting another code.",
          authError: null
        });
        if (echoed) this.submitCode(String(echoed));
      },
      (err) => this.setState({ authError: err })
    );
  };

  submitCode = (codeArg) => {
    const { plane, emailInput, otp } = this.state;
    // `codeArg` is the local debug echo handing us the code directly. Typed
    // check, not truthiness: this is also a click handler, so the argument is
    // normally a DOM event — and `event.trim` would throw.
    const code = (typeof codeArg === "string" ? codeArg : (otp || []).join("")).trim();
    if (code.length < 6) { this.setState({ authError: { detail: "Enter all six digits." } }); return; }
    this.setState({ authBusy: true, authError: null });
    API.post("/auth/" + PLANE_PATH[plane] + "/verify", { email: (emailInput || "").trim(), code }).then(
      (res) => {
        const uiPlane = KIND_TO_PLANE[res.principal] || plane;
        const screen = LANDING[uiPlane];
        this.setState({
          authBusy: false, authError: null, authNotice: null,
          me: { kind: res.principal, organization_id: res.organization_id },
          plane: uiPlane, screen, otp: ["", "", "", "", "", ""]
        });
        this.loadForScreen(screen);
        window.scrollTo(0, 0);
      },
      (err) => this.setState({ authBusy: false, authError: err, otp: ["", "", "", "", "", ""] })
    );
  };

  // Six boxes, one string. A pasted code lands in whichever box has focus, so
  // `onInput` distributes anything longer than one character rather than
  // needing an onPaste handler (which this runtime does not map).
  otpHandlers = [0, 1, 2, 3, 4, 5].map((i) => ({
    onInput: (e) => {
      const raw = (e.target.value || "").replace(/\D/g, "");
      this.setState((s) => {
        const next = (s.otp || []).slice();
        if (raw.length > 1) {
          for (let k = 0; k < raw.length && i + k < 6; k++) next[i + k] = raw[k];
        } else {
          next[i] = raw;
        }
        return { otp: next, authError: null };
      });
    },
    onKeyDown: (e) => {
      if (e.key === "Enter") { e.preventDefault(); this.submitCode(); return; }
      if (e.key === "Backspace" && !e.target.value) {
        this.setState((s) => {
          const next = (s.otp || []).slice();
          if (i > 0) next[i - 1] = "";
          return { otp: next };
        });
      }
    }
  }));

  backToLogin = () => this.setState({
    screen: "login", otp: ["", "", "", "", "", ""], authError: null, authNotice: null
  });

  signOut = () => {
    // Ask the server to kill the session, then clear locally either way — a
    // failed logout must not strand someone in a signed-in-looking shell.
    API.post("/auth/logout").catch(() => {});
    this.handleSessionLost();
    this.setState({ authNotice: null });
  };

  loadContacts = () => {
    const me = this.state.me;
    if (!me || me.kind !== "candidate") return;
    const token = this._contactLoad = {};
    const current = () => !this._gone && this.state.me === me && this._contactLoad === token;
    return this.load("contactList", () => API.get("/portal/verifications", { timeoutMs: EVAL_TIMEOUT_MS }), current)
      .then(data => {
        if (!data || !current()) return;
        const selected = (data.verifications || []).find(v => v.id === this.state.contactId);
        if (selected && selected.status !== "pending") this.setState({ contactId: null, contactCode: "" });
      });
  };
  contactEmail = () => this.setContactMethod("otp_email");
  contactPhone = () => this.setContactMethod("otp_phone");
  setContactMethod = (method) => {
    if (!this._contactAction) this.setState({ contactMethod: method, contactId: null,
      contactCode: "", contactError: null, contactNotice: "" });
  };
  setContactDestination = (e) => { if (!this._contactAction) this.setState({ contactDestination: e.target.value,
    contactId: null, contactCode: "", contactError: null, contactNotice: "" }); };
  setContactCode = (e) => { if (!this._contactAction) this.setState({ contactCode: e.target.value }); };
  continueContact = (id, method) => () => {
    if (!this._contactAction) this.setState({ contactId: id, contactMethod: method, contactDestination: "",
      contactCode: "", contactError: null, contactNotice: "Enter the previously delivered code. It may have expired or been replaced." });
  };
  contactErrorCopy = (err) => {
    if (!err) return "";
    if (err.detail === "contact_code_capacity_exhausted") return "Contact code requests are busy. Try again shortly.";
    if (err.detail === "contact_code_executor_closed") return "Contact verification is temporarily unavailable. Try again shortly.";
    if (err.detail === "contact_code_pending") return "The request may still be running. A code can arrive later. Refresh contact status and enter that code before requesting another.";
    if (err.detail === "email_unavailable") return "Email delivery is unavailable. Request a new code when it is available.";
    if (err.detail === "phone_unavailable") return "Phone delivery is unavailable. Use email if an email contact is on your record.";
    if (err.detail === "email_send_failed") return "The code request failed. You can request a new code.";
    if (["network", "timeout"].includes(err.kind)) return "The request could not be completed here. It may have completed on the server; refresh contact status before retrying.";
    if (err.status === 403 && err.kind !== "csrf") return "This account cannot perform this contact check.";
    if (err.status >= 500) return "Contact verification is unavailable. Try again later.";
    return errorCopy(err);
  };
  startContactVerification = () => this.contactRequest(false);
  confirmContactVerification = () => this.contactRequest(true);
  contactRequest = async (confirm) => {
    const st = this.state, me = st.me;
    if (this._gone || this._contactAction || !me || me.kind !== "candidate") return;
    if (confirm ? !st.contactId || !st.contactCode.trim() : !st.contactDestination.trim()) {
      this.setState({ contactError: { detail: confirm ? "Enter the delivered verification code." : "Enter the contact on your candidate record." } });
      return;
    }
    const token = this._contactAction = {};
    const current = () => !this._gone && this._contactAction === token && this.state.me === me;
    const id = st.contactId;
    const body = confirm ? { code: st.contactCode.trim() }
      : { method: st.contactMethod, destination: st.contactDestination.trim() };
    this.setState({ contactBusy: true, contactError: null, contactNotice: "",
      contactCode: "", ...(confirm ? {} : { contactId: null }) });
    try {
      const result = await API.post(confirm ? "/portal/verifications/" + encodeURIComponent(id) + "/confirm" : "/portal/verifications",
        body, { timeoutMs: EVAL_TIMEOUT_MS });
      if (!current()) return;
      const verification = confirm ? result : result && result.verification;
      if (!verification || typeof verification.id !== "string" || !verification.id
          || verification.method !== st.contactMethod || verification.status !== (confirm ? "verified" : "pending")
          || (confirm && verification.id !== id)) throw { detail: "The server did not return the expected verification state. Refresh contact status." };
      this.setState({ contactId: confirm ? null : verification.id,
        contactNotice: confirm ? "Contact verified. This proves contact control, not employment." : "Code sent. Enter the code delivered to your contact." });
      this.loadContacts();
      if (confirm) this.load("portal", () => API.get("/portal/me"), () => !this._gone && this.state.me === me);
    } catch (err) {
      if (!current() || err.kind === "session_lost") return;
      this.setState({ contactError: err, ...(confirm && (err.status === 404
        || (err.status === 400 && err.detail !== "incorrect code")) ? { contactId: null } : {}) });
      this.loadContacts();
    } finally {
      if (current()) { this._contactAction = null; this.setState({ contactBusy: false }); }
    }
  };
  revokeConsent = (id) => () => {
    this.setState({ busyId: id });
    API.post("/portal/consents/" + id + "/revoke").then(
      () => { this.setState({ busyId: null }); this.load("consentList", () => API.get("/portal/consents")); },
      (err) => this.setState({ busyId: null, consentList: { loading: false, data: this.state.consentList.data, error: err } })
    );
  };

  revokeSession = (id) => () => {
    this.setState({ busyId: id });
    API.post("/auth/sessions/" + id + "/revoke").then(
      () => { this.setState({ busyId: null }); this.load("sessionList", () => API.get("/auth/sessions")); },
      (err) => this.setState({ busyId: null, sessionList: { loading: false, data: this.state.sessionList.data, error: err } })
    );
  };

  setErasureConfirm = (e) => this.setState({ erasureConfirm: e.target.value });
  confirmErasure = () => {
    if ((this.state.erasureConfirm || "").trim().toUpperCase() !== "DELETE") return;
    this.setState({ busyId: "erase" });
    API.del("/portal/me").then(
      () => {
        // Everything cascades server-side and the session dies with it, so the
        // only honest next screen is login.
        this.setState({ busyId: null, erasureConfirm: "" });
        this.handleSessionLost();
        this.setState({ authNotice: "Your data has been deleted. Nothing is left to sign in to." });
      },
      (err) => this.setState({ busyId: null, portal: { loading: false, data: this.state.portal.data, error: err } })
    );
  };

  // operator has no self-signup path, so switching to it forces sign-in mode
  setOrg = () => this.setState({ plane: "org" });
  setCandidate = () => this.setState({ plane: "candidate" });
  setAdmin = () => this.setState({ plane: "operator", authMode: "signin" });
  setSignIn = () => this.setState({ authMode: "signin" });
  setSignUp = () => this.setState({ authMode: "signup" });

  authValues = () => {
    const st = this.state;
    return {
      // -- auth bindings ----------------------------------------------------
      emailInput: st.emailInput, setEmailInput: this.setEmailInput, onEmailKey: this.onEmailKey,
      orgNameInput: st.orgNameInput, setOrgNameInput: this.setOrgNameInput,
      submitCode: this.submitCode, resendCode: this.resendCode,
      verifyAction: st.authBusy ? "Checking…" : "Verify and continue",
      otpBoxes: (st.otp || []).map((v, i) => ({
        value: v, onInput: this.otpHandlers[i].onInput, onKeyDown: this.otpHandlers[i].onKeyDown
      })),
      authError: !!(st.authError || st.authNotice),
      authErrorBox: st.authError ? ERROR_BOX : NOTICE_BOX,
      authErrorText: st.authError ? this.authErrorCopy(st.authError) : (st.authNotice || ""),

      tabOrg: tabBtn(this.state.plane === "org"),
      tabCandidate: tabBtn(this.state.plane === "candidate"),
      tabAdmin: tabBtn(this.state.plane === "operator"),
      planeHint: PLANE_HINT[this.state.plane],
      canSignUp: this.state.plane !== "operator",
      operatorOnly: this.state.plane === "operator",
      needsOrgName: this.state.plane === "org" && this.state.authMode === "signup",
      modeSignIn: modeBtn(this.state.authMode === "signin"),
      modeSignUp: modeBtn(this.state.authMode === "signup"),
      setSignIn: this.setSignIn, setSignUp: this.setSignUp,
      authTitle: this.state.plane === "operator" ? "Operator sign in"
        : this.state.authMode === "signup" ? "Create your account" : "Sign in",
      emailPlaceholder: this.state.plane === "candidate" ? "you@example.com"
        : this.state.plane === "operator" ? "you@veritas.in" : "you@agency.in",
      authAction: st.authBusy
        ? "Sending…"
        : (st.authMode === "signup" && st.plane !== "operator" ? "Create account and send code" : "Send code"),
    };
  };

  portalValues = () => {
    const st = this.state;
    const me = st.me || {};
    const busy = (id) => st.busyId === id;

    // -- portal (candidate plane) -----------------------------------------
    const my = st.portal.data;
    const prof = (my && my.profile) || null;
    const name = prof ? fieldValue(prof.full_name) : null;
    const retention = (my && my.retention && my.retention.windows) || [];
    const retentionLine = retention.length
      ? retention.map((w) => w.data_class + " " + w.ttl_days + "d").join(" · ")
        + (my.retention.sweep_active ? "" : " — surfaced, not swept")
      : "—";

    const portalProfile = my ? [
      { k: "Name", v: name || "Not extracted" },
      { k: "Email", v: prof && fieldValue(prof.email) ? fieldValue(prof.email) : "Held as a hash only" },
      { k: "Phone", v: prof && fieldValue(prof.phone) ? fieldValue(prof.phone) : "Held as a hash only" },
      { k: "Location", v: (prof && fieldValue(prof.location)) || "—" },
      { k: "Resume versions", v: String((my.resumes || []).length) },
      { k: "Retention policy", v: retentionLine }
    ] : [];

    // The subject sees that a report EXISTS and when — never its internals.
    const portalReports = my ? (my.reports || []).map((x) => ({
      id: x.report_id, meta: x.domain + " · " + fmtDate(x.created_at)
    })) : [];

    // S7.1 assurance ladder. `identity` is null until the candidate verifies
    // anything, which is the common case and not an error.
    const held = new Set(((my && my.identity && my.identity.methods) || []).map(String));
    const expired = new Set(((my && my.identity && my.identity.expired_methods) || []).map(String));
    const portalAssurance = my ? [
      ["Self-attestation", "self_attested"],
      ["Contact-control OTP (email)", "otp_email"],
      ["Contact-control OTP (phone)", "otp_phone"],
      ["Operator manual review", "manual_review"],
      ["Government ID", "government_id"]
    ].map(([label, key]) => {
      const isHeld = held.has(key);
      const status = isHeld ? "Held" : expired.has(key) ? "Expired"
        : key === "government_id" ? "Not implemented" : "Not held";
      return { key, method: label, status, chip: stateChip(isHeld) };
    }) : [];

    const accessRows = st.accessLog.data;
    const accessLog = accessRows ? accessRows.map((e) => ({
      when: fmtDateTime(e.at),
      org: e.actor_name || e.actor_id || (e.actor_type === "system" ? "Veritas (internal)" : e.actor_type),
      purpose: e.action,
      outcome: e.allowed === true ? "Allowed" : e.allowed === false ? "Refused" : "—",
      chip: stateChip(e.allowed === true)
    })) : [];

    const consentRows = st.consentList.data;
    const consents = consentRows ? consentRows.map((c) => {
      const g = c.grant || {};
      const active = c.state === "active";
      return {
        org: g.organization_name || g.org_id || "—",
        purpose: g.purpose + (g.expires_at ? " · expires " + fmtDate(g.expires_at) : ""),
        expiry: c.state === "active" ? "Active" : c.state === "revoked" ? "Revoked" : "Expired",
        active,
        action: active && !busy(g.id) ? SMALL_GHOST : SMALL_MUTED,
        actionLabel: busy(g.id) ? "…" : active ? "Revoke" : "Revoked",
        revoke: active ? this.revokeConsent(g.id) : this.noop
      };
    }) : [];

    // -- devices (any plane) ----------------------------------------------
    const sessRows = st.sessionList.data;
    const sessions = sessRows ? sessRows.map((d) => ({
      agent: d.user_agent || "Unknown device",
      id: String(d.id).slice(0, 8) + "…",
      lastSeen: relTime(d.last_seen_at),
      status: d.current ? "This device" : (d.status === "active" ? "Live" : d.status),
      current: d.current,
      chip: stateChip(d.current),
      // Use Sign out for this device; keep its row's revoke action inert.
      action: d.current || busy(d.id) ? SMALL_MUTED : SMALL_GHOST,
      actionLabel: busy(d.id) ? "…" : d.current ? "—" : "Revoke",
      revoke: d.current ? this.noop : this.revokeSession(d.id)
    })) : [];

    return {
      // Who you actually are, not a prop.
      accountName: me.kind === "candidate"
        ? (name || "Your data")
        : me.kind === "admin" ? "Operator" : (me.organization_id ? "Org " + String(me.organization_id).slice(0, 8) : "Organisation"),
      accountInitial: me.kind === "candidate" ? (name ? name[0] : "C") : me.kind === "admin" ? "O" : "S",
      portalLoading: st.portal.loading,
      portalError: !!st.portal.error,
      portalErrorText: errorCopy(st.portal.error),
      contactDestination: st.contactDestination, contactCode: st.contactCode,
      contactDestinationLabel: st.contactMethod === "otp_phone" ? "Phone contact on record" : "Email contact on record",
      contactBusy: st.contactBusy, contactStartLabel: st.contactBusy ? "Working…" : "Send contact code",
      contactEmail: this.contactEmail, contactPhone: this.contactPhone,
      setContactDestination: this.setContactDestination, setContactCode: this.setContactCode,
      startContactVerification: this.startContactVerification, confirmContactVerification: this.confirmContactVerification,
      contactPending: !!st.contactId, contactNotice: st.contactNotice,
      contactError: !!st.contactError, contactErrorText: this.contactErrorCopy(st.contactError),
      loadContacts: this.loadContacts, contactListLoading: st.contactList.loading,
      contactListError: !!st.contactList.error, contactListErrorText: this.contactErrorCopy(st.contactList.error),
      contactRecords: ((st.contactList.data && st.contactList.data.verifications) || [])
        .filter(v => v.method === "otp_email" || v.method === "otp_phone").map(v => ({
          id: v.id, pending: v.status === "pending",
          label: (v.method === "otp_email" ? "Email" : "Phone") + " · " + v.status + " · " + fmtDateTime(v.requested_at),
          continue: this.rowHandler("contact", v.id, () => this.continueContact(v.id, v.method))
        })),
      portalProfile, portalReports, portalAssurance,
      portalCounts: {
        resumes: my ? (my.resumes || []).length : 0,
        reports: my ? (my.reports || []).length : 0,
        consents: my ? (my.consents || []).length : 0,
        interviews: my ? (my.interviews || []).length : 0
      },

      accessLog,
      accessLogLoading: st.accessLog.loading,
      accessLogEmpty: !!accessRows && accessRows.length === 0,

      consents,
      consentsLoading: st.consentList.loading,
      consentsEmpty: !!consentRows && consentRows.length === 0,

      sessions,
      sessionsLoading: st.sessionList.loading,

      erasureConfirm: st.erasureConfirm,
      setErasureConfirm: this.setErasureConfirm,
      confirmErasure: this.confirmErasure,
      erasureArmed: (st.erasureConfirm || "").trim().toUpperCase() === "DELETE",
      erasureLabel: busy("erase") ? "Deleting…" : "Delete everything",
    };
  };
  };
})(window);
