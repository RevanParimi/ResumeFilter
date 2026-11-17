/* Employer roles and advisory board handlers/view values for DCLogic.
 * Shared state, loading, navigation and lifecycle remain in the component.
 */
(function (global) {
  "use strict";

  global.VeritasEmployerRoles = (Base, {
    API, errorCopy, statusChip, BAND, chip, navBtn
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

  employerValues = () => {
    const st = this.state;

    // -- roles (org plane) -----------------------------------------
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

    return {
      isRoles: st.screen === "roles",
      navRoles: navBtn(st.screen === "roles"),
      goRoles: this.goRoles,
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
      boardLoading: st.board.loading

    };
  };
  };
})(window);
