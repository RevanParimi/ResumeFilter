# DEPLOY.md — taking veritas live

> **This service has never been deployed, and that is deliberate.** There are
> zero customers. A running host with no users buys nothing and costs money,
> credentials and an attack surface, so every sprint through PI-8 has proven
> the system locally and stopped. **The user decides when that changes** — no
> agent and no session creates a cloud resource without being asked.
>
> This document exists so that when the answer is yes, go-live is a checklist
> and not a recollection.

Everything below is machine-checked where it can be:
`tests/test_deploy_doc.py` asserts that every `DEE_` variable named here is a
real `Settings` field, and that every setting the boot refusals read is named
here. A runbook that lists a variable the code ignores is worse than no runbook.

---

## 0. What is proven, and what is not

| Claim | Proven by | Where |
|---|---|---|
| The app boots, serves and refuses correctly | 1843 unit tests + 20 smoke scripts | local, every sprint |
| The image **builds** and contains the app | the `image` job | GitHub Actions, **on push only** |
| Migrations run up/down/up on Postgres | the `postgres` job | GitHub Actions |
| The app runs **on Railway** | nothing | — |

The development machine has **no Docker and no psql** (measured). The image is
therefore unproven until something is pushed and the `image` job runs. Push
first; do not learn about a broken `COPY` from a failed deploy.

---

## 1. Pre-flight: the eight boot refusals

The app **refuses to start** on any of these. That is the design: each one
produces a service that *looks* healthy while being unsafe or unusable, which
is precisely what a boot check is for. A configuration that satisfies all eight
is a bootable one, so this table doubles as the checklist.

| # | Refused when | Set | Failure it prevents |
|---|---|---|---|
| 1 | `DEE_API_AUTH_KEY` empty | `openssl rand -hex 32` | The admin plane — including the route that mints **any candidate's** access key — would be unguarded. No local exemption. |
| 2 | `DEE_ENV=prod` and `DEE_CANDIDATES_DB_URL` is SQLite | `postgresql+psycopg://…` | Container disks are ephemeral: every row is lost on redeploy, and SQLite serialises writes across workers. |
| 3 | `DEE_SESSION_COOKIE_SECURE=false` in prod | `true` | The session cookie travels the public internet; `false` ships a live session token in the clear. |
| 4 | `*` in `DEE_CORS_ALLOWED_ORIGINS` in prod | exact origins, or empty | This API is called with credentials; a wildcard is never correct, and leaning on the browser to reject it leaves a defect waiting to be "fixed" by silencing a console error. |
| 5 | `DEE_EMAIL_PROVIDER=capture` in prod | `smtp` | `CaptureEmail` writes login codes to a file in plaintext — an OTP leak wearing a test harness's clothes. |
| 6 | `DEE_RATE_LIMIT_ENABLED=false` in prod | `true` | The OTP endpoints are the brute-force surface this PI created; unthrottled on a public host. |
| 7 | `DEE_GRIEVANCE_OFFICER_EMAIL` empty in prod | a monitored mailbox | DPDP requires the grievance mechanism to be **published**. `GET /grievance` would answer 200 with an empty contact — worse than a 404, because it looks answered. |
| 8 | no working email provider in prod | `DEE_EMAIL_PROVIDER=smtp` **and** `DEE_EMAIL_SMTP_HOST` | Signup and login on all three planes answer 503 `email_unavailable` — nobody can create an account or log in — while `/healthz` reports healthy. |

Refusal 8 asks the email **builder** whether it can deliver, not what
`DEE_EMAIL_PROVIDER` says: `smtp` with an empty host silently falls back to the
null provider, and a string check would have passed that config.

---

## 2. Environment

Secrets live only in the environment. `config.yaml` is baked into the image and
holds tunables, never credentials.

### Required

| Variable | Value | Why |
|---|---|---|
| `DEE_API_AUTH_KEY` | `openssl rand -hex 32` | Refusal 1. **Never reuse a smoke or test key.** |
| `DEE_CANDIDATES_DB_URL` | `postgresql+psycopg://…` | Refusal 2. Railway's Postgres plugin supplies this. |
| `DEE_ENV` | `prod` | Turns on refusals 3–8. |
| `DEE_EMAIL_PROVIDER` | `smtp` | Refusals 5 and 8. |
| `DEE_EMAIL_SMTP_HOST` | your relay | Refusal 8. |
| `DEE_EMAIL_SMTP_USER` | relay username | |
| `DEE_EMAIL_SMTP_PASSWORD` | relay password | Secret. |
| `DEE_EMAIL_FROM` | e.g. `no-reply@yourdomain` | What the login code arrives from. |
| `DEE_GRIEVANCE_OFFICER_EMAIL` | a **monitored** mailbox | Refusal 7. Published to every data principal at `GET /grievance`. |
| `DEE_GRIEVANCE_OFFICER_NAME` | a real person | Published beside the address. |
| `DEE_GRIEVANCE_OFFICER_PHONE` | a real number | Published beside the address. |

### Expected

| Variable | Value | Why |
|---|---|---|
| `DEE_EMAIL_SMTP_PORT` | `587` | Default; matches STARTTLS. |
| `DEE_EMAIL_SMTP_STARTTLS` | `true` | Default. Turn off only for a relay on localhost. |
| `DEE_SESSION_COOKIE_SECURE` | `true` | Default, and refusal 3. |
| `DEE_SESSION_COOKIE_SAMESITE` | `lax` | Default since S8.6 — the UI is served by this API, so requests are same-origin. Use `none` **only** if you host the UI separately. |
| `DEE_RATE_LIMIT_ENABLED` | `true` | Default, and refusal 6. |
| `DEE_RATE_LIMIT_TRUSTED_PROXY_HOPS` | **`1`** behind Railway | See §3. The default `0` is wrong behind a proxy. |
| `DEE_VECTORSTORE_BACKEND` | `memory` | Unless a Chroma volume is mounted: `PersistentClient` can hang, and grounding is best-effort. |
| `DEE_LOG_JSON` | `true` | Structured logs. |
| `DEE_LOG_LEVEL` | `INFO` | |
| `DEE_CORS_ALLOWED_ORIGINS` | **usually empty** | See §4. |
| `DEE_OPENROUTER_API_KEY` | your key, or unset | Every LLM step has a deterministic fallback; unset means the system still works, with weaker output. |

`DEE_DB_MIGRATE_ON_BOOT` defaults to `true` and should stay there — **the
container migrates itself on boot**, holding a Postgres advisory lock so
multiple workers cannot race. There is no separate migration step.

---

## 3. Behind a proxy: `DEE_RATE_LIMIT_TRUSTED_PROXY_HOPS`

**Set this to `1` on Railway.** The default is `0`, which ignores
`X-Forwarded-For` entirely and uses the socket peer — correct for direct
exposure, and wrong behind a load balancer, where *every caller shares one
bucket*.

That failure is worth recognising in advance because of how it presents
(`OPERATING.md` §3): a flood of `scope="ip"` denials across many different
emails **looks exactly like an attack** and is almost always this setting being
wrong for the deployment. Set it too high and the value falls back to the
socket peer; the n-th entry is counted *from the right*.

---

## 4. CORS is usually empty now

The UI is served **by this API** at `/ui` (S8.6), so its calls are same-origin
and CORS does not apply to them. A deployment can leave
`DEE_CORS_ALLOWED_ORIGINS` empty and the UI works.

Add exact origins only for third-party browser integrations. Never `*` — prod
refuses to boot (refusal 4). CORS is fail-closed: with no configured origin the
middleware is not installed at all.

---

## 5. The retention cron — **do not skip this**

**The retention sweep has no scheduler.** There is no worker and no in-process
timer anywhere in `app/`, deliberately: with N replicas an in-process timer
would run the most destructive operation in the repo N times concurrently,
inside a web worker where a long `DELETE` competes with request handling.

It runs when something calls it. **If nothing calls it, nothing is ever
deleted — and the portal goes on telling every data principal that eleven
classes of their data are purged on a schedule.** Shipping that is shipping the
exact falsehood S8.3 Phase B was written to remove.

Wire a Railway cron on the same image:

```bash
python -m app.retention.sweep --apply
```

Daily, off-peak, is the intended cadence.

**Its contract** (pinned by `tests/test_retention_cli_contract.py`):

| | |
|---|---|
| **Preview** | no `--apply` = dry run. Counts, deletes nothing. Safe to run any time. |
| **Output** | the report is the **last line** of stdout and is JSON. The process shares stdout with the structured log, so the stream is a *sequence* of JSON documents — `jq` is fine, `json.loads(whole_output)` is not. |
| **Exit 0** | ran. |
| **Exit 2** | refused: `DEE_RETENTION_SWEEP_ENABLED` is false. Distinct from 0 so a cron can tell "refused" from "ran and deleted nothing". |
| **Exit 3** | refused: the database schema is not at head. Nothing was read or deleted. Start the web service (it migrates on boot) first. |
| **`truncated: true`** | a class hit `DEE_SWEEP_MAX_ROWS_PER_CLASS` (10 000) and **more rows remain**. The cap bounds how long one statement holds locks; it is not an error. **Re-run until it is false**, or the backlog never clears. |

An operator can also POST to `/admin/retention/sweep`. Both doors go through
the same function and both refuse a real run on a disabled config.

---

## 6. Deploying

`railway.json` is committed: `DOCKERFILE` builder, healthcheck on `/healthz`,
restart on failure. The image runs as a non-root user and binds `${PORT}`.

1. Push, and **wait for the `image` job to go green.** It is the only proof the
   image builds.
2. Create the project and the Postgres plugin.
3. Set every variable in §2.
4. Deploy. Watch the logs for `startup_complete`; a `LaunchConfigError` names
   the exact refusal and the exact variable.
5. Check `GET /healthz`, then `GET /` — the endpoints list is derived from the
   live route table, so it is a true inventory of what is running.
6. Wire the cron from §5.
7. Create the first org and the first admin. Sign up through the UI at `/ui`.

**`scripts/` is not in the image** (`.dockerignore`), so
`scripts/migrate_reports_into_main_db.py` cannot be run in the container. It is
needed only by a deployment predating S8.1 — of which there are none, because
there are no deployments. If that ever changes, run it from a checkout against
the same database URL.

---

## 7. Before any of this: the IBM check

**Blocking, and not technical.** The author works at IBM. The IP-assignment and
outside-activity terms in that employment agreement must be reviewed **before
veritas takes revenue** — not after a customer signs, when the answer is
materially worse and the options are fewer.

See `docs/superpowers/specs/2026-08-01-veritas-gtm-positioning.md` §8.3. This
line item is here because this is the document someone opens on the day they
decide to go live, which is the last honest moment to have already done it.
