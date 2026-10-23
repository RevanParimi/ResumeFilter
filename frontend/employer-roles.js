/* Employer roles, advisory board and compensation handlers/view values for DCLogic.
 * Shared state, loading, navigation and lifecycle remain in the component.
 */
(function (global) {
  "use strict";

  global.VeritasEmployerRoles = (Base, {
    API, errorCopy, statusChip, BAND, chip, confWord, navBtn
  }) => class extends Base {
  loadJobs = () => this.load("jobList", () => API.get("/jobs")).then((jobs) => {
    if (jobs && jobs.length && !this.state.selectedJob) this.selectJob(jobs[0].id)();
  });

  selectJob = (id) => () => {
    this.setState({ selectedJob: id });
    // An empty pool is a successful board with a reason; render that separately
    // from denied access and failed requests.
    this.load("board", () => API.get("/jobs/" + id + "/board"));
  };

  loadComp = () => {
    const jobs = this.state.jobList.data;
    if (!jobs) { this.load("jobList", () => API.get("/jobs")).then(() => this.loadCompFor()); return; }
    this.loadCompFor();
  };
  loadCompFor = () => {
    const jobs = this.state.jobList.data || [];
    const job = jobs.find((j) => j.id === this.state.selectedJob) || jobs[0];
    if (!job) { this.setState({ comp: { loading: false, data: null, error: null } }); return; }
    this.load("comp", () => API.get("/jobs/" + job.id + "/comp"));
  };

  employerValues = () => {
    const st = this.state;

    // -- roles + comp (org plane) -----------------------------------------
    const jobRows = st.jobList.data;
    const jobs = jobRows ? jobRows.map((j) => ({
      id: j.id, title: j.title,
      loc: j.location || "—",
      domain: j.domain,
      status: j.status === "open" ? "Open" : j.status === "on_hold" ? "On hold" : j.status,
      matched: (j.must_have_skills || []).length + (j.nice_to_have_skills || []).length,
      band_label: "—",
      filled: "—",
      statusChip: statusChip(j.status === "open"),
      select: this.selectJob(j.id)
    })) : [];

    const boardData = st.board.data;
    const boardErr = st.board.error;
    const shortlist = boardData && boardData.match && boardData.match.ranked
      ? boardData.match.ranked.map((m) => {
          const b = BAND[m.risk_band] || BAND.insufficient;
          return {
            name: m.candidate_id,
            role: "match " + (m.score !== undefined && m.score !== null ? m.score.toFixed(2) : "—"),
            score: m.score !== undefined && m.score !== null ? m.score.toFixed(2) : "—",
            cover: "coverage " + (m.skill && m.skill.coverage !== undefined && m.skill.coverage !== null ? m.skill.coverage.toFixed(2) : "—"),
            chip: chip(b), bandLabel: b.label + " risk",
            note: m.reasoning || ""
          };
        })
      : [];

    // BOTH comp endpoints now answer a CompBenchmark, which WRAPS the estimate
    // (plus the requisition's own band and how it sits against the market).
    // S8.4 Phase B made POST /comp/estimate match GET /jobs/{id}/comp; before
    // that it returned the bare CompBandEstimate, and assuming one shape
    // rendered a band made entirely of dashes. The `|| compRaw` fallback stays
    // so this keeps working against either version of the API.
    const compRaw = st.comp.data;
    const compData = compRaw ? (compRaw.estimate || compRaw) : null;
    const compPosition = compRaw ? compRaw.position : null;
    const compJob = (jobRows || []).find((j) => j.id === st.selectedJob) || (jobRows || [])[0] || null;
    // The API answers in absolute INR; Indian comp is spoken in lakhs.
    const lpa = (v) => (v === null || v === undefined ? "—" : "₹" + (v / 100000).toFixed(1) + " LPA");
    const medianPct = (function () {
      if (!compData) return "50%";
      const lo = compData.p25, hi = compData.p75, mid = compData.p50;
      if ([lo, hi, mid].some((x) => x === null || x === undefined) || hi <= lo) return "50%";
      const frac = Math.min(1, Math.max(0, (mid - lo) / (hi - lo)));
      return (15 + frac * 70).toFixed(2) + "%";
    })();

    return {
      isRoles: st.screen === "roles",
      isComp: st.screen === "comp",
      navRoles: navBtn(st.screen === "roles"),
      navComp: navBtn(st.screen === "comp"),
      goRoles: this.goRoles, goComp: this.goComp,
      jobs,
      jobsLoading: st.jobList.loading,
      jobsEmpty: !!jobRows && jobRows.length === 0,
      hasJobs: jobs.length > 0,
      shortlist,
      // A successful empty pool, consent refusal and failed read are distinct.
      boardConsentBlocked: !!(boardErr && boardErr.kind === "consent"),
      boardEmptyPool: !!(boardData && boardData.match && boardData.match.reason === "no_materialized_candidates"),
      boardEmptyPoolText: "No candidates are ready to rank yet. Ask an operator to refresh candidate data, then select the role again.",
      boardError: !!(boardErr && boardErr.kind !== "consent"),
      boardErrorText: errorCopy(boardErr),
      boardLoading: st.board.loading,

      compLoading: st.comp.loading,
      compError: !!st.comp.error,
      compErrorText: errorCopy(st.comp.error),
      // Comp is benchmarked per requisition, so with none there is nothing to
      // show — better to say that than render a band made entirely of dashes.
      // `noComp` deliberately covers BOTH "no requisition" and "the benchmark
      // did not come back", so the screen can never render nothing at all.
      hasComp: !!compData,
      noComp: !compData && !st.comp.loading && !st.jobList.loading,
      noCompReason: compJob
        ? "The comp benchmark for this requisition did not load."
        : "Comp is benchmarked per requisition. Create one on the Roles screen and its band appears here.",
      compRole: compJob ? (compJob.title + " · " + (compJob.location || "—")) : "No requisition selected",
      compP25Label: lpa(compData && compData.p25),
      compP50Label: lpa(compData && compData.p50),
      compP75Label: lpa(compData && compData.p75),
      compObserved: compData ? String(compData.n_observed) : "—",
      compObservedLabel: compData
        ? (compData.n_observed > 0
            ? compData.n_observed + " observed offers · above the k=5 floor"
            : "No observed offers above the k=5 floor")
        : "—",
      compConfidenceLabel: compData && compData.confidence !== null && compData.confidence !== undefined
        ? compData.confidence.toFixed(2) + " · " + confWord(compData.confidence)
        : "—",
      // The median sits where it actually falls between p25 and p75, so a
      // skewed band is not silently redrawn as a symmetric one.
      compBandBar: { position: "absolute", left: "15%", width: "70%", height: "100%", borderRadius: "99px", background: "linear-gradient(92deg,var(--a1),var(--a2))" },
      compMedianMark: { position: "absolute", left: medianPct, top: "-4px", width: "2px", height: "14px", background: "var(--heading)" },
      compMedianLabelPos: { position: "absolute", left: medianPct, transform: "translateX(-50%)", whiteSpace: "nowrap", color: "var(--heading)" },
      compPriorOnly: !!(compData && !compData.n_observed),
      // `position` is null when the requisition carries no band of its own —
      // which is not "at market", so it must not render as a number.
      compPositionLabel: compPosition
        ? (compPosition + (compRaw && compRaw.delta_pct !== null && compRaw.delta_pct !== undefined
            ? " " + (compRaw.delta_pct >= 0 ? "+" : "") + (compRaw.delta_pct * 100).toFixed(0) + "%"
            : ""))
        : "No band set"
    };
  };
  };
})(window);
