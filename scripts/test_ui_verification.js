"use strict";
const assert = require("node:assert/strict");
const { test } = require("node:test");
// Reuse the shipped-logic harness; its existing evaluation/client cases also run.
const { component, settle } = require("./test_ui_evaluate");
const pending = { id: "contact_server_id", method: "otp_email", status: "pending" };
const verified = { ...pending, status: "verified" };

function fixture(post) {
  const fixture = component("candidate", post || (async p => p.endsWith("confirm") ? verified : { verification: pending }));
  const { c, window, calls } = fixture;
  c.state.screen = "portal";
  c.state.contactDestination = "synthetic-contact@example.com";
  window.VeritasAPI.get = async p => { calls.push(["GET", p]); if (p === "/auth/sessions") return []; return p === "/portal/verifications"
    ? { verifications: [pending], assurance: { level: 0 } } : { reports: [], resumes: [], consents: [], interviews: [] }; };
  return fixture;
}

test("contact start sends one candidate request and success uses actual server ID", async () => {
  let resolve;
  const { c, calls } = fixture(() => new Promise(r => { resolve = r; }));
  c.startContactVerification(); c.startContactVerification(); await settle();
  assert.equal(calls.length, 1);
  assert.equal(calls[0][1], "/portal/verifications");
  assert.deepEqual(calls[0][2], { method: "otp_email", destination: c.state.contactDestination });
  assert.equal(c.state.contactNotice, "");
  resolve({ verification: pending }); await settle();
  assert.equal(c.state.contactId, pending.id);
  assert(c.state.contactNotice.includes("Code sent"));
  assert.equal(c.state.contactBusy, false);
});

test("confirmation sends delivered code once, clears plaintext, and reads saved status", async () => {
  const { c, calls } = fixture();
  c.state.contactId = pending.id; c.state.contactCode = "123456";
  c.confirmContactVerification(); c.confirmContactVerification(); await settle();
  assert.equal(calls.filter(x => x[0] === "POST").length, 1);
  assert.equal(calls[0][1], "/portal/verifications/" + pending.id + "/confirm");
  assert.deepEqual(calls[0][2], { code: "123456" });
  assert.equal(c.state.contactCode, "");
  assert.equal(c.state.contactId, null);
  assert(c.state.contactNotice.includes("not employment"));
  assert(calls.some(x => x[1] === "/portal/me"));
});

for (const detail of ["email_unavailable", "phone_unavailable", "email_send_failed"]) {
  test("delivery refusal has no sent notice and retains destination: " + detail, async () => {
    const { c } = fixture(() => Promise.reject({ status: 503, detail, kind: "http" }));
    const destination = c.state.contactDestination;
    c.startContactVerification(); await settle();
    assert.equal(c.state.contactBusy, false);
    assert.equal(c.state.contactNotice, "");
    assert.equal(c.state.contactId, null);
    assert.equal(c.state.contactDestination, destination);
    assert(c.renderVals().contactErrorText);
  });
}

test("wrong/expired code remains a refusal; selecting or editing contact cannot reuse another target", async () => {
  const { c } = fixture(() => Promise.reject({ status: 400, detail: "challenge expired" }));
  c.state.contactId = pending.id; c.state.contactCode = "123456";
  c.confirmContactVerification(); await settle();
  assert.equal(c.state.contactNotice, "");
  assert.equal(c.state.contactCode, "");
  assert.equal(c.state.contactBusy, false);
  assert(c.renderVals().contactErrorText.includes("expired"));
  assert.equal(c.state.contactId, null);
  c.setContactDestination({ target: { value: "other@example.com" } });
  assert.equal(c.state.contactId, null);
  c.continueContact(pending.id, "otp_email")();
  assert.equal(c.state.contactDestination, "");
  assert(c.state.contactNotice.includes("may have expired"));
});

test("invalid success cannot advertise sent or confirmed; wrong plane never submits", async () => {
  const { c, calls } = fixture(async () => ({}));
  c.startContactVerification(); await settle();
  assert.equal(c.state.contactNotice, "");
  assert(c.state.contactError);
  c.state.me = { kind: "org" }; c.startContactVerification(); await settle();
  assert.equal(calls.filter(x => x[0] === "POST").length, 1);
});

test("a malformed reference or wrong returned contact method cannot advertise sent", async () => {
  for (const verification of [{ ...pending, id: {} }, { ...pending, method: "otp_phone" }]) {
    const { c } = fixture(async () => ({ verification }));
    c.startContactVerification(); await settle();
    assert.equal(c.state.contactNotice, "");
    assert(c.state.contactError);
  }
});

test("status refresh closes a terminal code entry and ignores late reads after session loss", async () => {
  const { c, window } = fixture();
  c.state.contactId = pending.id; c.state.contactCode = "123456";
  window.VeritasAPI.get = async () => ({ verifications: [verified] });
  await c.loadContacts();
  assert.equal(c.state.contactId, null);
  assert.equal(c.state.contactCode, "");
  let resolve;
  window.VeritasAPI.get = () => new Promise(r => { resolve = r; });
  c.loadContacts(); c.handleSessionLost(); resolve({ verifications: [verified] }); await settle();
  assert.equal(c.state.contactList.data, null);
});

test("portal assurance shows held and expired contact methods from the real wire shape", () => {
  const { c } = fixture();
  c.state.portal = { loading: false, error: null, data: { identity: {
    level: 2, methods: ["otp_email"], expired_methods: [] } } };
  assert.equal(c.renderVals().portalAssurance.find(a => a.method.includes("(email)")).status, "Held");
  c.state.portal.data.identity = { level: 0, methods: [], expired_methods: ["otp_email"] };
  assert.equal(c.renderVals().portalAssurance.find(a => a.method.includes("(email)")).status, "Expired");
});

test("session loss ignores late contact success/list and clears destination/code", async () => {
  let resolve;
  const { c } = fixture(() => new Promise(r => { resolve = r; }));
  c.state.contactCode = "123456";
  c.startContactVerification(); await settle(); c.handleSessionLost();
  resolve({ verification: pending }); await settle();
  assert.equal(c.state.screen, "login");
  assert.equal(c.state.contactDestination, "");
  assert.equal(c.state.contactCode, "");
  assert.equal(c.state.contactId, null);
  assert.equal(c.state.contactList.data, null);
});

test("timeout suggests checking server status and navigation does not become false success", async () => {
  const { c } = fixture(() => Promise.reject({ kind: "timeout" }));
  c.startContactVerification(); c.nav("devices")(); await settle();
  assert.equal(c.state.screen, "devices");
  assert.equal(c.state.contactBusy, false);
  assert.equal(c.state.contactNotice, "");
  assert(c.renderVals().contactErrorText.includes("refresh contact status"));
});

for (const [detail, expected] of [
  ["contact_code_capacity_exhausted", /busy/],
  ["contact_code_executor_closed", /temporarily unavailable/],
  ["contact_code_pending", /Refresh contact status and enter that code before requesting another/],
]) {
  test("contact admission/wait refusal settles without sent notice or automatic replay: " + detail, async () => {
    const { c, calls, window } = fixture(async () => { throw { detail, status: detail === "contact_code_pending" ? 504 : 503 }; });
    c.startContactVerification(); await settle();
    assert.equal(c.state.contactBusy, false);
    assert.equal(c.state.contactNotice, "");
    assert.equal(c.state.contactId, null);
    assert.equal(c.state.contactDestination, "synthetic-contact@example.com");
    assert.match(c.renderVals().contactErrorText, expected);
    assert.equal(calls.filter(x => x[0] === "POST").length, 1);
    assert(calls.some(x => x[1] === "/portal/verifications" && x[0] === "GET"));
    window.VeritasAPI.get = async () => ({ verifications: [pending] });
    await c.loadContacts();
    c.continueContact(pending.id, "otp_email")();
    c.setContactCode({ target: { value: "123456" } });
    window.VeritasAPI.post = async (path, body) => { calls.push(["POST", path, body]); return verified; };
    c.confirmContactVerification(); await settle();
    assert.equal(calls.filter(x => x[0] === "POST").length, 2);
    assert.equal(calls.filter(x => x[0] === "POST").at(-1)[1], "/portal/verifications/" + pending.id + "/confirm");
    assert.equal(c.state.contactId, null);
    assert.match(c.state.contactNotice, /Contact verified/);
  });
}

function authFixture(plane = "candidate", mode = "signin") {
  const ctx = fixture();
  Object.assign(ctx.c.state, { screen: "login", me: null, plane, authMode: mode,
    emailInput: "  synthetic-login@example.com  ", orgNameInput: "  Synthetic Org  " });
  ctx.window.VeritasAPI.get = async p => {
    ctx.calls.push(["GET", p]);
    if (p === "/screening/batches") return { batches: [] };
    if (p === "/portal/me") return { profile: {}, resumes: [], reports: [], consents: [], interviews: [] };
    if (p === "/portal/verifications") return { verifications: [] };
    return [];
  };
  ctx.window.VeritasAPI.post = async (p, body) => {
    ctx.calls.push(["POST", p, body]);
    return p.endsWith("/verify")
      ? { principal: plane === "operator" ? "admin" : plane, organization_id: plane === "org" ? "owned-org" : null }
      : { status: "accepted" };
  };
  return ctx;
}

for (const [plane, mode, path, landing] of [
  ["org", "signup", "/auth/org/signup", "queue"],
  ["org", "signin", "/auth/org/login", "queue"],
  ["candidate", "signup", "/auth/candidate/signup", "portal"],
  ["candidate", "signin", "/auth/candidate/login", "portal"],
  ["operator", "signup", "/auth/admin/login", "adminorgs"],
  ["operator", "signin", "/auth/admin/login", "adminorgs"],
]) {
  test(`auth ${plane}/${mode} retains its own routes, payload and landing`, async () => {
    const { c, calls } = authFixture(plane, mode);
    const send = c.sendCode; send(); await settle();
    assert.deepEqual(calls[0], ["POST", path, {
      email: "synthetic-login@example.com", ...(plane === "org" && mode === "signup" ? { organization_name: "Synthetic Org" } : {})
    }]);
    assert.equal(c.state.screen, "verify"); assert.equal(c.state.authBusy, false);
    assert.match(c.renderVals().authErrorText, /Delivery may still be in progress/);
    assert.equal(c.renderVals().otpBoxes.length, 6);
    assert.equal(c.state.me, null);
    assert.equal(calls.length, 1, "generic acceptance must not verify or replay the request");
    c.state.otp = ["1", "2", "3", "4", "5", "6"];
    const verify = c.submitCode; verify({ type: "click" }); await settle();
    assert.deepEqual(calls.find(x => x[1].endsWith("/verify")), ["POST", path.replace(/\/(signup|login)$/, "/verify"),
      { email: "synthetic-login@example.com", code: "123456" }]);
    assert.equal(c.state.screen, landing);
    assert.equal(c.state.me.kind, plane === "operator" ? "admin" : plane);
    assert.deepEqual(c.state.otp, ["", "", "", "", "", ""]);
    assert(calls.some(x => x[0] === "GET"));
  });
}

test("auth validation refuses locally and plane/mode controls preserve operator sign-in", () => {
  const { c, calls } = authFixture("org", "signup");
  c.setEmailInput({ target: { value: " " } }); c.sendCode();
  assert.match(c.renderVals().authErrorText, /email address/);
  c.setEmailInput({ target: { value: "synthetic@example.com" } });
  c.setOrgNameInput({ target: { value: " " } }); c.sendCode();
  assert.match(c.renderVals().authErrorText, /organisation name/);
  c.submitCode(); assert.match(c.renderVals().authErrorText, /all six digits/);
  assert.equal(calls.length, 0);
  const admin = c.setAdmin; admin();
  assert.equal(c.state.authMode, "signin"); assert.equal(c.renderVals().canSignUp, false);
  assert.equal(c.renderVals().operatorOnly, true);
  c.setCandidate(); c.setSignUp();
  assert.equal(c.renderVals().needsOrgName, false); assert.equal(c.renderVals().authTitle, "Create your account");
  c.setOrg(); assert.equal(c.renderVals().needsOrgName, true);
  c.setSignIn(); assert.equal(c.renderVals().authTitle, "Sign in");
  c.state.authBusy = true;
  assert.equal(c.renderVals().authAction, "Sending…");
  assert.equal(c.renderVals().verifyAction, "Checking…");
});

test("OTP paste/backspace/Enter callbacks keep identity and independent instance arrays", async () => {
  const { c, calls } = authFixture();
  const sibling = new c.constructor(); sibling.props = {};
  assert.notEqual(c.otpHandlers, sibling.otpHandlers);
  const first = c.renderVals().otpBoxes, second = c.renderVals().otpBoxes;
  assert.equal(first[0].onInput, second[0].onInput);
  first[2].onInput({ target: { value: "12x34567" } });
  assert.deepEqual(c.state.otp, ["", "", "1", "2", "3", "4"]);
  first[4].onKeyDown({ key: "Backspace", target: { value: "" } });
  assert.equal(c.state.otp[3], "");
  first[0].onInput({ target: { value: "123456" } });
  let prevented = 0;
  first[5].onKeyDown({ key: "Enter", preventDefault() { prevented++; } }); await settle();
  assert.equal(prevented, 1); assert(calls.some(x => x[1] === "/auth/candidate/verify"));
  assert.deepEqual(sibling.state.otp, ["", "", "", "", "", ""]);
});

test("resend uses login and preserves digits without server echo; local echo verifies explicitly", async () => {
  const { c, calls, window } = authFixture("org", "signup");
  c.state.otp = ["1", "2", "3", "", "", ""];
  const resend = c.resendCode; resend({ preventDefault() {} }); await settle();
  assert.equal(calls[0][1], "/auth/org/login");
  assert.deepEqual(c.state.otp, ["1", "2", "3", "", "", ""]);
  assert.match(c.renderVals().authErrorText, /If a code arrives/);
  assert.match(c.state.authNotice, /Delivery may still be in progress/);
  window.VeritasAPI.post = async (p, body) => {
    calls.push(["POST", p, body]);
    return p.endsWith("/verify") ? { principal: "org", organization_id: "owned" } : { debug_code: "654321" };
  };
  c.resendCode(); await settle();
  const verifiedCall = calls.filter(x => x[0] === "POST").at(-1);
  assert.equal(verifiedCall[1], "/auth/org/verify");
  assert.equal(verifiedCall[2].code, "654321");
  assert.equal(c.state.screen, "queue");
  c.sendCode(); await settle();
  assert(calls.some(x => x[1] === "/auth/org/signup"));
  assert.equal(c.state.screen, "queue");
});

test("failed send/verify/resend settle without successful sign-in and allow explicit recovery", async () => {
  const { c, window } = authFixture();
  window.VeritasAPI.post = async () => { throw { kind: "invalid_code", status: 400 }; };
  c.sendCode(); await settle();
  assert.equal(c.state.authBusy, false); assert.equal(c.state.screen, "login");
  c.state.screen = "verify"; c.state.otp = ["1", "2", "3", "4", "5", "6"];
  c.submitCode(); await settle();
  assert.equal(c.state.me, null); assert.equal(c.state.screen, "verify");
  assert.deepEqual(c.state.otp, ["", "", "", "", "", ""]);
  assert.match(c.renderVals().authErrorText, /That code did not work/);
  c.resendCode(); await settle(); assert(c.state.authError);
  c.backToLogin(); assert.equal(c.state.authNotice, null); assert.equal(c.state.authError, null);
  window.VeritasAPI.post = async () => ({ status: "accepted" });
  c.onEmailKey({ key: "Enter", preventDefault() {} }); await settle();
  assert.equal(c.state.screen, "verify");
});

test("portal navigation reads only the requested resource and rendering never uses sample records", async () => {
  const { c, calls } = fixture();
  for (const [screen, route] of [["portal", "/portal/me"], ["accesslog", "/portal/access-log"],
    ["consents", "/portal/consents"], ["devices", "/auth/sessions"]]) {
    calls.length = 0; c.nav(screen)(); await settle();
    assert(calls.some(x => x[1] === route));
    assert(calls.every(x => x[0] === "GET"));
    assert.equal(c.state.screen, screen);
  }
  c.handleSessionLost();
  const view = c.renderVals();
  for (const key of ["portalProfile", "portalReports", "portalAssurance", "accessLog", "consents", "sessions"])
    assert.deepEqual(view[key], [], key);
  assert.equal(view.accountName, "Organisation");
});

test("portal values preserve redacted contacts, report metadata, assurance, retention and access actors", () => {
  const { c } = fixture();
  c.state.portal = { loading: false, error: null, data: {
    profile: { full_name: { value: "Synthetic Subject" }, location: { value: "Synthetic City" } },
    resumes: [{}], reports: [{ report_id: "rep_owned", domain: "data_eng", summary: "Must not appear" }],
    consents: [{}], interviews: [{}, {}], retention: { windows: [{ data_class: "resume", ttl_days: 365 }], sweep_active: false },
    identity: { methods: ["otp_email"], expired_methods: ["manual_review"] }
  } };
  c.state.accessLog = { loading: false, error: null, data: [
    { actor_name: "Synthetic Actor", action: "ledger_read", allowed: true },
    { actor_type: "system", action: "maintenance", allowed: false }
  ] };
  const view = c.renderVals();
  assert.equal(view.accountName, "Synthetic Subject"); assert.equal(view.accountInitial, "S");
  assert.equal(view.portalProfile.find(row => row.k === "Email").v, "Held as a hash only");
  assert.match(view.portalProfile.find(row => row.k === "Retention policy").v, /365d.*not swept/);
  assert.deepEqual(view.portalCounts, { resumes: 1, reports: 1, consents: 1, interviews: 2 });
  assert.deepEqual(Object.keys(view.portalReports[0]).sort(), ["id", "meta"]);
  assert.equal(view.portalReports[0].id, "rep_owned");
  assert.equal(view.portalAssurance.find(row => row.key === "manual_review").status, "Expired");
  assert.equal(view.portalAssurance.find(row => row.key === "government_id").status, "Not implemented");
  assert.equal(view.accessLog[0].org, "Synthetic Actor"); assert.equal(view.accessLog[0].outcome, "Allowed");
  assert.equal(view.accessLog[1].org, "Veritas (internal)"); assert.equal(view.accessLog[1].outcome, "Refused");
});

test("consent/device revocation rereads saved rows, retains failures and leaves current-device action inert", async () => {
  const { c, calls, window } = fixture();
  const held = data => ({ loading: false, error: null, data });
  c.state.consentList = held([{ state: "active", grant: { id: "owned-grant", purpose: "ledger_read" } }]);
  c.state.sessionList = held([{ id: "current", current: true }, { id: "sibling", current: false, status: "active" }]);
  let view = c.renderVals();
  assert.equal(view.sessions[0].revoke, c.noop);
  view.sessions[0].revoke(); assert.equal(calls.length, 0);
  window.VeritasAPI.post = async p => { calls.push(["POST", p]); };
  window.VeritasAPI.get = async p => { calls.push(["GET", p]); return p.includes("consents")
    ? [{ state: "revoked", grant: { id: "owned-grant", purpose: "ledger_read" } }]
    : [{ id: "current", current: true }]; };
  view.consents[0].revoke(); await settle();
  assert(calls.some(x => x[1] === "/portal/consents/owned-grant/revoke"));
  assert.equal(c.renderVals().consents[0].active, false);
  view.sessions[1].revoke(); await settle();
  assert(calls.some(x => x[1] === "/auth/sessions/sibling/revoke"));
  assert.equal(c.renderVals().sessions.length, 1);
  window.VeritasAPI.post = async () => { throw { status: 403, detail: "Synthetic refusal" }; };
  c.revokeConsent("owned-grant")(); await settle();
  assert.equal(c.state.busyId, null); assert.equal(c.state.consentList.data[0].state, "revoked");
  assert.equal(c.state.consentList.error.status, 403);
  c.revokeSession("sibling")(); await settle();
  assert.equal(c.state.sessionList.error.status, 403); assert.equal(c.state.sessionList.data.length, 1);
});

test("typed erasure requires confirmation, preserves failure state and signs out only on success", async () => {
  const { c, window, calls } = fixture();
  c.state.portal = { loading: false, error: null, data: { profile: {} } };
  c.confirmErasure(); assert.equal(calls.length, 0);
  c.setErasureConfirm({ target: { value: "delete" } }); assert.equal(c.renderVals().erasureArmed, true);
  window.VeritasAPI.del = async p => { calls.push(["DELETE", p]); throw { status: 503, detail: "Synthetic refusal" }; };
  const erase = c.confirmErasure; erase(); await settle();
  assert.equal(c.state.me.kind, "candidate"); assert(c.state.portal.data); assert.equal(c.state.portal.error.status, 503);
  window.VeritasAPI.del = async p => { calls.push(["DELETE", p]); };
  erase(); await settle();
  assert.equal(calls.at(-1)[1], "/portal/me"); assert.equal(c.state.screen, "login");
  assert.equal(c.state.me, null); assert.equal(c.state.erasureConfirm, "");
  assert.match(c.state.authNotice, /Your data has been deleted/);
});

test("same-class contact actions isolate tokens and session loss cannot clear a sibling result", async () => {
  const queued = [];
  const { c } = fixture(() => new Promise(resolve => queued.push(resolve)));
  const sibling = new c.constructor(); sibling.props = {};
  Object.assign(sibling.state, { me: { kind: "candidate" }, screen: "portal", contactDestination: "sibling@example.com" });
  c.startContactVerification(); sibling.startContactVerification();
  assert.notEqual(c._contactAction, sibling._contactAction);
  assert.notEqual(c._rowHandlers, sibling._rowHandlers);
  c.handleSessionLost(); queued[0]({ verification: pending }); queued[1]({ verification: { ...pending, id: "sibling-id" } });
  await settle();
  assert.equal(c.state.contactId, null); assert.equal(c.state.contactNotice, "");
  assert.equal(sibling.state.contactId, "sibling-id"); assert.match(sibling.state.contactNotice, /Code sent/);
});
