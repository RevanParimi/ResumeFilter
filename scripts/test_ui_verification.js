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
