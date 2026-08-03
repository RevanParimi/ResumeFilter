/* veritas — API client for the design-component UI.
 *
 * Loaded as a plain <script> beside support.js. No modules, no bundler: the
 * .dc.html logic class is evaluated through `new Function(...)`, a function
 * scope rather than a module, so a global is the only seam that works.
 *
 * Everything in here exists because the browser is a hostile client the API was
 * not originally written for. The rules below are enforced centrally so no
 * caller can forget one — every observation is measured against a running API
 * (see the session's contract run), not remembered.
 *
 *   1. credentials:"include" on EVERY call, including GETs. The session is a
 *      cookie and the UI is on a different origin; without it nothing
 *      authenticates and the failure looks like a mysterious 401.
 *   2. X-CSRF-Token on every unsafe method, read from the dee_csrf cookie AT
 *      CALL TIME. Not cached at login: a re-login rotates it, and a stale token
 *      fails closed with a 403 that looks like an auth bug.
 *   3. 401 means the session died — expired (12h), idle (2h), revoked, or the
 *      account was erased. Redirect to login; NEVER retry. There is no rate
 *      limiting server-side yet (S8.3), so a retry loop is not caught anywhere.
 *   4. 403 has two unrelated meanings and the UI must fork on them. Both detail
 *      strings are measured:
 *        "missing or invalid CSRF token"          -> app/api/routes.py
 *        "no active consent for purpose '<p>'"    -> app/ledger/consent.py
 *      Anything else 403 defaults to `consent`, because consent-not-granted is
 *      the NORMAL state (UI.md §6) and mislabelling it as an auth failure turns
 *      an expected empty section into a red error.
 */
(function (global) {
  "use strict";

  var DEFAULT_BASE = "http://localhost:8000";
  var STORAGE_KEY = "veritas_api_base";
  var CSRF_COOKIE = "dee_csrf";
  var SAFE = { GET: 1, HEAD: 1, OPTIONS: 1 };

  var sessionLostHandler = null;
  var cachedBase = null;

  function trimSlash(u) {
    return String(u || "").replace(/\/+$/, "");
  }

  /* ?api=... wins (shareable demo links), then localStorage, then the default.
   * A base URL that is invisible is a base URL that will eventually point
   * somewhere nobody expects, so the UI renders whatever this returns. */
  function base() {
    if (cachedBase !== null) return cachedBase;
    var fromQuery = null;
    try {
      fromQuery = new URLSearchParams(global.location.search).get("api");
    } catch (e) {
      fromQuery = null;
    }
    if (fromQuery) {
      setBase(fromQuery);
      return cachedBase;
    }
    var stored = null;
    try {
      stored = global.localStorage.getItem(STORAGE_KEY);
    } catch (e) {
      stored = null;
    }
    cachedBase = trimSlash(stored || DEFAULT_BASE);
    return cachedBase;
  }

  function setBase(url) {
    cachedBase = trimSlash(url || DEFAULT_BASE);
    try {
      global.localStorage.setItem(STORAGE_KEY, cachedBase);
    } catch (e) {
      /* private mode — the in-memory value still applies for this page */
    }
    return cachedBase;
  }

  /* The CSRF cookie is deliberately NOT httpOnly — the client has to read it to
   * echo it back. That asymmetry IS the double-submit scheme. */
  function csrfToken() {
    var all = String(global.document.cookie || "").split(";");
    for (var i = 0; i < all.length; i++) {
      var p = all[i].trim();
      if (p.indexOf(CSRF_COOKIE + "=") === 0) {
        return decodeURIComponent(p.slice(CSRF_COOKIE.length + 1));
      }
    }
    return null;
  }

  function ApiError(status, detail, kind) {
    var e = new Error(typeof detail === "string" ? detail : "request failed");
    e.name = "ApiError";
    e.status = status;
    e.detail = detail;
    e.kind = kind;
    return e;
  }

  /* FastAPI answers {"detail": ...}, but `detail` is a LIST of objects for a 422
   * validation error and a plain string everywhere else. A proxy 502 is not JSON
   * at all. Never throw from inside the error path. */
  function readDetail(body) {
    if (!body || typeof body !== "object") return String(body || "");
    var d = body.detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d)) {
      return d
        .map(function (item) {
          return item && item.msg ? item.msg : JSON.stringify(item);
        })
        .join("; ");
    }
    return d ? JSON.stringify(d) : "";
  }

  function classify(status, detail) {
    if (status === 401) return "session_lost";
    if (status === 403) {
      return /csrf/i.test(detail) ? "csrf" : "consent";
    }
    if (status === 400 && detail === "invalid_code") return "invalid_code";
    if (status === 503 && detail === "email_unavailable") return "email_down";
    if (status === 422) return "unprocessable";
    if (status === 404) return "not_found";
    if (status === 409) return "conflict";
    return "http";
  }

  function request(method, path, body, opts) {
    var m = String(method || "GET").toUpperCase();
    var init = {
      method: m,
      // Rule 1. Not an option a caller can pass — there is no way to omit it.
      credentials: "include",
      headers: {},
    };
    if (body !== undefined && body !== null) {
      init.headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(body);
    }
    if (!SAFE[m]) {
      // Rule 2. Read at call time, not cached.
      var t = csrfToken();
      if (t) init.headers["X-CSRF-Token"] = t;
    }

    return global
      .fetch(base() + path, init)
      .catch(function (netErr) {
        // A CORS rejection and a dead server are indistinguishable here by
        // design (the browser withholds the detail), so say both.
        throw ApiError(
          0,
          "Could not reach the API at " +
            base() +
            ". Check it is running and that this origin is in " +
            "DEE_CORS_ALLOWED_ORIGINS. (" +
            (netErr && netErr.message ? netErr.message : "network error") +
            ")",
          "network"
        );
      })
      .then(function (res) {
        var isJson = (res.headers.get("content-type") || "").indexOf("json") !== -1;
        return (isJson ? res.json().catch(function () { return null; }) : res.text())
          .then(function (parsed) {
            if (res.ok) return parsed;
            var detail = isJson ? readDetail(parsed) : String(parsed || "").slice(0, 300);
            var kind = classify(res.status, detail);
            if (kind === "session_lost" && sessionLostHandler) {
              // Rule 3. Fire once, then throw. The caller must not retry, and
              // there is nothing to retry with.
              try {
                sessionLostHandler();
              } catch (e) {
                /* a broken handler must not mask the original 401 */
              }
            }
            throw ApiError(res.status, detail, kind);
          });
      });
  }

  global.VeritasAPI = {
    base: base,
    setBase: setBase,
    csrfToken: csrfToken,
    request: request,
    get: function (p) { return request("GET", p); },
    post: function (p, b) { return request("POST", p, b === undefined ? {} : b); },
    patch: function (p, b) { return request("PATCH", p, b === undefined ? {} : b); },
    del: function (p) { return request("DELETE", p); },
    onSessionLost: function (fn) { sessionLostHandler = fn; },

    /* Screens with no endpoint until S8.4 render mock data. They must SAY so:
     * a confident UI beside an honest backend is how a demo ends up showing a
     * buyer numbers that were never computed (UI.md §7). */
    MOCK_NOTE: "Sample data — this screen has no endpoint until S8.4",
  };
})(window);
