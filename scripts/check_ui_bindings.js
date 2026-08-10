/* Resolve every {{ binding }} in Veritas.dc.html against what renderVals()
 * actually returns.  `node scripts/check_ui_bindings.js`
 *
 * WHY THIS EXISTS. `frontend/` has no bundler, no type checker and no CI
 * (PI-8 decision 0.1), and the template is bound to the logic class by NAME.
 * A renamed or forgotten value therefore fails silently: the runtime resolves
 * it to undefined and renders an empty string, so a screen loses a number and
 * still looks fine. That is the same class of defect as a guard that inspects
 * nothing — it passes by not looking.
 *
 * It does not render. It EXECUTES the logic class (the same source the browser
 * evaluates through `new Function`), calls renderVals() over several states,
 * and checks that every binding in the template resolves in at least one of
 * them. Running renderVals() at all is half the value: a null-dereference in
 * the mapping shows up here rather than as a blank screen.
 *
 * sc-for scopes are tracked, so `{{ c.reason }}` inside
 * `<sc-for list="{{ candidates }}" as="c">` is checked against a real row.
 */
"use strict";

const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..");
const UI = path.join(ROOT, "frontend", "Veritas.dc.html");
const API_JS = path.join(ROOT, "frontend", "api.js");

const src = fs.readFileSync(UI, "utf8");
const open = src.indexOf('<script type="text/x-dc"');
const bodyStart = src.indexOf(">", open) + 1;
const bodyEnd = src.indexOf("</script>", bodyStart);
const template = src.slice(0, open);
const logic = src.slice(bodyStart, bodyEnd);

/* ── a browser-shaped enough sandbox ────────────────────────────────────── */
const fakeWindow = {
  location: { search: "" },
  localStorage: { getItem: () => null, setItem: () => {} },
  document: { cookie: "" },
  fetch: () => Promise.reject(new Error("no network in the binding check")),
};
new Function("window", fs.readFileSync(API_JS, "utf8"))(fakeWindow);

class DCLogic {
  setState() {}
}

const Component = new Function(
  "DCLogic", "window", "document", "navigator", "FileReader", "setTimeout",
  "clearTimeout", "setInterval", "clearInterval",
  logic + "\nreturn Component;"
)(
  DCLogic, fakeWindow, fakeWindow.document, { clipboard: null },
  function FileReader() {}, () => 0, () => {}, () => 0, () => {}
);

/* ── fixtures, shaped from app/screening/schema.py + app/schemas/report.py ── */
const SIGNALS = {
  risk_band: "elevated", risk_confidence: 0.71, depth_band: "superficial",
  depth_score: 0.31, loudest_signal: "resume_farm", loudest_band: "near_duplicate",
  n_components: 3, farm_band: "near_duplicate", farm_score: 0.91,
  farm_corpus_size: 4182, matched_existing: false, matched_on: null,
  duplicate_resume: false, flagged_claims: 2,
};
const COUNTS = { pending: 4, processing: 1, done: 12, failed: 1 };
const BATCH = {
  id: "bat_abc123def456", name: "Wipro DE — August intake", domain: "genai",
  created_at: "2026-08-10T09:14:00Z", created_by_org_user_id: null,
  counts: COUNTS, status: "processing",
};
const QUEUE = {
  rows: [
    {
      item_id: "itm_1111", status: "done", created_at: "2026-08-10T09:14:00Z",
      processed_at: "2026-08-10T09:20:00Z", candidate_id: "can_2222",
      resume_id: "res_3333", report_id: "rep_4444", risk_score: 0.78,
      signals: SIGNALS, reason: "elevated fabrication risk — resume farm is the loudest of 3; confidence 0.71",
      error: null, advisory: true, human_review_required: true,
    },
    {
      item_id: "itm_5555", status: "pending", created_at: "2026-08-10T09:14:00Z",
      processed_at: null, candidate_id: null, resume_id: null, report_id: null,
      risk_score: null, signals: null, reason: "not screened yet", error: null,
      advisory: true, human_review_required: true,
    },
    {
      item_id: "itm_6666", status: "failed", created_at: "2026-08-10T09:14:00Z",
      processed_at: "2026-08-10T09:21:00Z", candidate_id: null, resume_id: null,
      report_id: null, risk_score: null, signals: null,
      reason: "could not be screened: empty_resume", error: "empty_resume",
      advisory: true, human_review_required: true,
    },
  ],
  next_cursor: "eyJhIjoxfQ",
};
const SUMMARY = {
  batch_id: BATCH.id, name: BATCH.name, domain: "genai", status: "processing",
  counts: COUNTS, n_screened: 12,
  by_risk_band: { elevated: 2, moderate: 3, low: 6, insufficient_data: 1 },
  top_signals: [
    { signal: "resume_farm", count: 5 },
    { signal: "cross_field", count: 4 },
    { signal: "ai_generation", count: 3 },
  ],
  advisory: true, human_review_required: true,
};
const REPORT = {
  id: "rep_4444", domain: "genai", created_at: "2026-08-10T09:20:00Z",
  candidate_id: "can_2222",
  candidate_context: { full_name: "Rohit Malviya", role_title: "Sr. GenAI Engineer", seniority: "senior" },
  verdicts: [{
    claim_id: "clm_1", claim_text: "Fine-tuned GPT-4 on 2M internal support tickets.",
    claim_type: "fine_tuning", status: "incoherent", coherence_score: 0.18,
    confidence: 0.79, reasoning: "No training stack is described.",
    expected_signals: ["training infra"], missing_signals: ["Any named training infrastructure"],
    evidence: [{ source: "rule", polarity: "contradicts", detail: "no infra signals present", weight: 0.6, ref: "fine_tuning_infra" }],
    probes: ["Which base checkpoint did you start from?"],
  }],
  depth_score: 0.31, depth_band: "superficial", overall_confidence: 0.6,
  advisory: true, human_review_required: true, summary: "Three depth claims sit ahead of the evidence.",
  flagged_claim_ids: ["clm_1"], deferred_claim_ids: [],
  ai_generation: { likelihood: 0.54, confidence: 0.48, band: "possible", signals: [], reasoning: "Template phrasing.", advisory: true },
  cross_field: { score: 0.22, confidence: 0.66, band: "minor_issues", findings: [], reasoning: "A four-month gap.", advisory: true },
  // matches[] arrive with their ids ALREADY NULL on the org plane (S8.4 Phase A).
  resume_farm: { score: 0.91, confidence: 0.82, band: "near_duplicate", corpus_size: 4182, reasoning: "One resume overlaps at 0.91.", advisory: true,
    matches: [{ candidate_id: null, resume_id: null, similarity: 0.91 }] },
  fabrication_risk: {
    score: 0.78, confidence: 0.71, band: "elevated", reasoning: "Fused.", advisory: true,
    components: [
      { id: "resume_farm", band: "near_duplicate", risk: 0.9, confidence: 0.82, weight: 0.41, flagged: true },
      { id: "ai_generation", band: "possible", risk: 0.5, confidence: 0.48, weight: 0.19, flagged: false },
      { id: "cross_field", band: "minor_issues", risk: 0.3, confidence: 0.66, weight: 0.26, flagged: false },
    ],
  },
};

const IDLE = { loading: false, data: null, error: null };
const held = (d) => ({ loading: false, data: d, error: null });

/* Several states, because a binding only has to resolve in the state that
 * shows it — and because the states that break mappings are the empty ones. */
const STATES = {
  "boot / nothing loaded": {},
  "org, batch loaded": {
    screen: "queue", plane: "org", me: { kind: "org", organization_id: "org_1" },
    selectedBatch: BATCH.id, batch: held(BATCH), queue: held(QUEUE),
    summary: held(SUMMARY), batchList: held({ batches: [BATCH], next_cursor: "eyJhIjoxfQ" }),
    files: [{ name: "priya.pdf", size: 240000, kind: "pdf", file: null }],
  },
  "org, report open": {
    screen: "report", plane: "org", me: { kind: "org", organization_id: "org_1" },
    selectedBatch: BATCH.id, report: held(REPORT), batch: held(BATCH),
  },
  "org, empty account": {
    screen: "queue", plane: "org", me: { kind: "org", organization_id: "org_1" },
    batchList: held({ batches: [], next_cursor: null }),
  },
  "org, driving": {
    screen: "queue", plane: "org", me: { kind: "org", organization_id: "org_1" },
    selectedBatch: BATCH.id, batch: held(BATCH), queue: held(QUEUE), summary: held(SUMMARY),
    driving: true, driveDone: 7, driveFailed: 1,
  },
  // The screens wired in the 2026-08-03 session. Their fixtures are shaped
  // from the reads in liveVals(), which that session verified against the live
  // API — so what this proves here is that the TEMPLATE still matches the
  // mapping, not that the mapping still matches the API. The contract script
  // is what proves the latter.
  "candidate plane, portal loaded": {
    screen: "portal", plane: "candidate", me: { kind: "candidate" },
    portal: held({
      profile: { full_name: { value: "Priya Nandakumar" }, email: null, phone: null, location: { value: "Bengaluru" } },
      resumes: [{ id: "res_1" }], reports: [{ report_id: "rep_1", domain: "genai", created_at: "2026-08-01T10:00:00Z" }],
      consents: [{ id: "con_1" }], interviews: [], identity: { methods_held: ["otp_email"] },
      retention: { windows: [{ data_class: "resume", ttl_days: 365 }], sweep_active: false },
    }),
    accessLog: held([{ at: "2026-08-09T10:00:00Z", actor_name: "Sampoorna Staffing", actor_id: "org_1", actor_type: "organization", action: "ledger_read", allowed: true }]),
    consentList: held([{ state: "active", grant: { id: "con_1", organization_name: "Sampoorna Staffing", org_id: "org_1", purpose: "ledger_read", expires_at: null } }]),
    sessionList: held([{ id: "ses_11111111", issued_at: "2026-08-10T08:00:00Z", expires_at: "2026-08-10T20:00:00Z", last_seen_at: "2026-08-10T09:00:00Z", status: "active", user_agent: "Chrome 128 · Windows", current: true }]),
  },
  "org, roles + comp loaded": {
    screen: "roles", plane: "org", me: { kind: "org", organization_id: "org_1" },
    selectedJob: "job_1",
    jobList: held([{ id: "job_1", title: "Sr. Data Engineer", location: "Pune", domain: "data_eng", status: "open", must_have_skills: ["spark"], nice_to_have_skills: [] }]),
    board: held({ match: { matches: [{ candidate_id: "can_2222", score: 0.71, skill_coverage: 0.8, risk_band: "moderate", reasoning: "covers 4 of 5" }] } }),
    comp: held({ estimate: { p25: 1800000, p50: 2400000, p75: 3200000, n_observed: 7, confidence: 0.62 }, position: "at_market", delta_pct: 0.03 }),
  },
  "operator plane": { screen: "adminorgs", plane: "operator", me: { kind: "admin" } },
};

const bags = {};
for (const [label, patch] of Object.entries(STATES)) {
  const c = new Component();
  c.props = {};
  Object.assign(c.state, patch);
  try {
    bags[label] = c.renderVals();
  } catch (e) {
    console.error("FAIL  renderVals() threw in state '" + label + "': " + (e && e.stack || e));
    process.exit(1);
  }
}

/* ── walk the template, tracking sc-for scopes ──────────────────────────── */
const LITERAL = /^(true|false|null|-?\d+(\.\d+)?|'.*'|".*")$/;

/* `undefined` counts as MISSING, not as present-and-empty. Mutation testing
 * made the distinction load-bearing: a field explicitly set to undefined
 * survives an `in` check and renders as an empty string in the runtime, which
 * is the precise silent blank this script exists to catch. */
function resolve(bag, expr_path) {
  let cur = bag;
  for (const part of expr_path) {
    if (cur === null || cur === undefined) return { ok: false };
    if (!(part in cur) || cur[part] === undefined) return { ok: false };
    cur = cur[part];
  }
  return { ok: true, value: cur };
}

/* Every row a scope can iterate, in one bag. Recursive because sc-for nests:
 * `v.evidence` inside `reportVerdicts` is a list reached THROUGH a loop
 * variable, and a checker that could not follow it would silently skip the
 * report screen's whole inner half. */
function rowsForScope(bag, scopes, idx) {
  const { list } = scopes[idx];
  const outerIdx = scopes.slice(0, idx).map((s, i) => [s, i])
    .reverse().find(([s]) => s.as === list[0]);
  if (!outerIdx) {
    const found = resolve(bag, list);
    return found.ok && Array.isArray(found.value) ? found.value : [];
  }
  const out = [];
  for (const row of rowsForScope(bag, scopes, outerIdx[1])) {
    const found = resolve(row, list.slice(1));
    if (found.ok && Array.isArray(found.value)) out.push(...found.value);
  }
  return out;
}

const token = /<sc-for\b[^>]*?list="\{\{\s*([^}]+?)\s*\}\}"[^>]*?as="([^"]+)"[^>]*>|<\/sc-for>|\{\{\s*([^}]+?)\s*\}\}/g;
const scopes = [];
const misses = [];
const seen = new Set();
let m;
while ((m = token.exec(template)) !== null) {
  if (m[0] === "</sc-for>") { scopes.pop(); continue; }
  if (m[1] !== undefined) { scopes.push({ as: m[2], list: m[1].trim().split(".") }); continue; }

  const expr = m[3].trim();
  if (LITERAL.test(expr)) continue;
  seen.add(expr);
  const parts = expr.split(".");
  const scopeIdx = scopes.map((s, i) => [s, i]).reverse().find(([s]) => s.as === parts[0]);
  const frozen = scopes.slice();

  let resolvedSomewhere = false;
  for (const bag of Object.values(bags)) {
    if (scopeIdx) {
      const rows = rowsForScope(bag, frozen, scopeIdx[1]);
      // EVERY row must carry it, not just the first — a row shape that varies
      // by status is exactly where a binding goes missing.
      if (rows.length && rows.every((row) => resolve(row, parts.slice(1)).ok)) resolvedSomewhere = true;
    } else if (resolve(bag, parts).ok) {
      resolvedSomewhere = true;
    }
    if (resolvedSomewhere) break;
  }
  if (!resolvedSomewhere) {
    misses.push(expr + (scopeIdx ? "   (inside sc-for over " + scopeIdx[0].list.join(".") + ")" : ""));
  }
}

if (scopes.length) {
  console.error("FAIL  " + scopes.length + " unclosed <sc-for> in the template");
  process.exit(1);
}

const unique = [...new Set(misses)].sort();
console.log("checked " + seen.size + " distinct bindings across " + Object.keys(bags).length + " states");
if (unique.length) {
  console.error("\nFAIL  " + unique.length + " binding(s) resolve in no state:");
  unique.forEach((u) => console.error("  " + u));
  process.exit(1);
}
console.log("OK    every binding resolves");
