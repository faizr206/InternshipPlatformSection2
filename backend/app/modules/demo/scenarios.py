"""Demo scenarios (ported from Team P6/P7's waypoint presets, legacy/p06-p07-waypoint/source/src/data.js).

Each scenario starts from an empty platform and is built by calling the REAL endpoints in order, on the
demo date each step happened. So a scenario is also a regression test: if a rule changes and a step
becomes invalid, loading the scenario fails loudly.

- fresh     23 Nov 2026  nothing yet: run the whole journey live
- reviewed  28 Nov 2026  Layla's Jira gap prepared, revised and demonstrated; profile v3; matching rerun
- midpoint  18 Mar 2027  + applied, offered, accepted, PL-0001 confirmed; agreement, logs, judgements, actions
- end        4 Jun 2027  + Period 1 complete, employer feedback in; ready for the advisor's final review
"""
from app import db
from app.modules.applications import router as p04
from app.modules.matching import router as p05
from app.modules.preparation import router as p06
from app.modules.progress import router as p07
from app.modules.progress import service as p07_service

SCENARIOS = {
    "fresh": {"today": "2026-11-23", "label": "Fresh start",
              "note": "No activity yet. Run the journey end to end."},
    "reviewed": {"today": "2026-11-28", "label": "Jira reviewed",
                 "note": "Layla's Jira evidence is demonstrated; profile v3 and a rerun recommendation."},
    "midpoint": {"today": "2027-03-18", "label": "Mid-placement",
                 "note": "PL-0001 confirmed at Emirates Group; week 7 of Period 1 with logs, judgements and actions."},
    "end": {"today": "2027-06-04", "label": "End of period",
            "note": "Period 1 closed and employer feedback in; ready for the final review."},
}
LAYLA = "COOP-B001"
STUDENT = {"actor_role": "student"}
COORD = {"actor_role": "coordinator"}
REVIEWER = {"actor_role": "reviewer"}
SUPERVISOR = {"actor_role": "supervisor"}
ADVISOR = {"actor_role": "advisor"}
EMPLOYER = {"actor_role": "employer"}


def set_today(value: str) -> None:
    with db.connect() as conn:
        conn.execute("INSERT OR REPLACE INTO demo_settings (key, value) VALUES ('today', ?)", (value,))


def build(name: str) -> None:
    if name in ("reviewed", "midpoint", "end"):
        _reviewed()
    if name in ("midpoint", "end"):
        _midpoint()
    if name == "end":
        _end()


def _reviewed() -> None:
    # P05: Layla's run on profile v2 lists Jira (self-declared) as a gap on OP-028; she sends it to P06.
    set_today("2026-11-24")
    recs = p05.run_recommendations(LAYLA)
    rec = next(r for r in recs if r["opportunity_id"] == "OP-028")
    p05.handoff_gap(rec["recommendation_id"], "SK-JIRA", p05.GapHandoffIn(**STUDENT))
    p06.add_manual_gap(LAYLA, p06.GapIn(**COORD, skill_id="SK-VIZ", opportunity_id="OP-028",
                                        reason="Desirable for OP-028; self-declared only"))
    p06.complete_resource(LAYLA, "MOD-JIRA-101", p06.Actor(**STUDENT))

    set_today("2026-11-25")
    for key, who in (("OPS-101", "Layla Hassan"), ("OPS-102", "Priya Nair"), ("OPS-103", "Omar Saleh")):
        p06.assign_board_item(LAYLA, key, p06.AssignIn(**STUDENT, assignee=who))
    p06.move_board_item(LAYLA, "OPS-101", p06.MoveIn(**STUDENT, to="inprogress",
                                                     reason="Started cleaning; 3% of rows have no gate time."))
    p06.move_board_item(LAYLA, "OPS-101", p06.MoveIn(**STUDENT, to="done",
                                                     reason="Cleaned file shared with the team; missing rows flagged in OPS-104."))
    p06.move_board_item(LAYLA, "OPS-102", p06.MoveIn(**STUDENT, to="inprogress",
                                                     reason="Priya booked a call with the ops lead for Thursday."))
    for summary, who in (("Check missing gate-time values in the March extract", "Layla Hassan"),
                         ("Write the data dictionary for the delay table", "Omar Saleh")):
        board = p06.add_board_item(LAYLA, p06.ItemIn(**STUDENT, summary=summary))
        p06.assign_board_item(LAYLA, board["items"][-1]["key"], p06.AssignIn(**STUDENT, assignee=who))
    sub = p06.submit_evidence(LAYLA, p06.EvidenceIn(
        **STUDENT, module_id="MOD-JIRA-101",
        explanation="I created two new work items for the sprint, gave every item on the board an owner and moved "
                    "OPS-101 from To do through In progress to Done once the cleaned file was shared with the team."))
    p06.review_submission(sub["evidence_id"], p06.ReviewIn(
        **REVIEWER, decision="revision", checklist=[True, True, True, False],
        comment="Good board. Your explanation needs to say why each status changed and what happens next, "
                "so a colleague can follow it."))

    set_today("2026-11-26")
    p06.submit_evidence(LAYLA, p06.EvidenceIn(
        **STUDENT, module_id="MOD-JIRA-101",
        explanation="I created OPS-104 and OPS-105 for work the team will need next, gave every item an owner, and "
                    "moved OPS-101 from To do to Done once the cleaned file was shared. Each move has a reason so "
                    "Omar and Priya can see what changed and what comes next."))

    set_today("2026-11-27")
    p06.review_submission(sub["evidence_id"], p06.ReviewIn(
        **REVIEWER, decision="demonstrated", checklist=[True, True, True, True],
        comment="All four criteria met. Clear reasons on every move."))


def _midpoint() -> None:
    # P04: apply, employer review, offer, acceptance, coordinator confirmation -> P07.
    set_today("2026-12-01")
    app = p04.submit_application(p04.ApplicationIn(
        **STUDENT, student_id=LAYLA, opportunity_id="OP-028",
        statement="Aviation analytics in Dubai is the career I am preparing for; my reviewed SQL and Jira "
                  "evidence fit this role."))
    aid = app["application_id"]
    for action in ("Under review", "Shortlisted", "Offer"):
        p04.decide(aid, p04.DecisionIn(**EMPLOYER, action=action))
    p04.respond_to_offer(aid, p04.OfferResponseIn(**STUDENT, response="accept"))
    set_today("2026-12-14")
    placement = p04.confirm_placement(aid, p04.ConfirmPlacementIn(**COORD))
    pid = placement["placement_id"]
    set_today("2026-12-15")
    p07.assign_advisor(pid, p07.AdvisorIn(**COORD, advisor="Dr. Ahmed Youssef"))

    set_today("2027-02-02")
    for text, los in (("Build a weekly on-time-performance dashboard that the ground-ops team uses", ["LO1", "LO2"]),
                      ("Present one analysis to the station operations meeting", ["LO2", "LO3"]),
                      ("Keep a weekly reflective log on professional practice", ["LO4", "LO3"])):
        p07.add_goal(pid, p07.GoalIn(**STUDENT, text=text, outcomes=los))
    p07.sign_agreement(pid, p07.Actor(**STUDENT))
    set_today("2027-02-03")
    p07.sign_agreement(pid, p07.Actor(**SUPERVISOR))
    set_today("2027-02-04")
    p07.sign_agreement(pid, p07.Actor(**ADVISOR))
    for text in ("Completed Emirates data-access training", "Dashboard v1 released to ground-ops",
                 "Present at station operations meeting"):
        p07.add_milestone(pid, p07.TextIn(**SUPERVISOR, text=text))
    set_today("2027-02-05")
    p07.set_milestone("MS-1", p07.MilestoneIn(**SUPERVISOR, done=True))

    set_today("2027-02-11")
    log1 = p07.add_log(pid, p07.LogIn(**STUDENT, goal_id="G1", evidence_ids=["EV-0001"],
                                      text="Mapped the data sources for on-time performance and agreed the weekly "
                                           "cut-off with R. Khan."))
    set_today("2027-02-12")
    p07.acknowledge_log(log1["log_id"], p07.Actor(**SUPERVISOR))
    set_today("2027-02-18")
    log2 = p07.add_log(pid, p07.LogIn(**STUDENT, goal_id="G1", text="Finished the dashboard and shared it with the team today.",
                                      new_evidence_title="OTP dashboard v1, screenshot and notes"))
    set_today("2027-02-19")
    p07.request_detail(log2["log_id"], p07.TextIn(
        **SUPERVISOR, text="Please say what the dashboard shows, who uses it and what changed after feedback."))
    set_today("2027-02-21")
    p07.revise_log(log2["log_id"], p07.TextIn(
        **STUDENT, text="Released dashboard v1 with three views: daily OTP, delay causes and gate turnaround. Ops leads "
                        "asked for a filter by aircraft type, which I added on Friday. Next: test it with the night shift."))
    p07.set_milestone("MS-2", p07.MilestoneIn(**SUPERVISOR, done=True))
    set_today("2027-02-22")
    p07.acknowledge_log(log2["log_id"], p07.Actor(**SUPERVISOR))
    set_today("2027-03-04")
    with db.connect() as conn:
        p07_service.add_evidence(conn, p07_service.load_placement(conn, pid),
                                 "Supervisor email confirming the dashboard is used weekly", "Supervisor")
    set_today("2027-03-02")
    p07.add_action(pid, p07.ActionIn(**ADVISOR, owner="supervisor", due="2027-03-10",
                                     text="Agree a date to present at the station operations meeting"))
    set_today("2027-03-11")
    p07.add_log(pid, p07.LogIn(**STUDENT, goal_id="G3",
                               text="Reflected on presenting numbers to people who were not in the analysis. I "
                                    "over-explained the method and ran out of time for questions."))
    set_today("2027-03-15")
    p07.judge(pid, "LO1", p07.JudgementIn(**ADVISOR, level="developing", evidence_ids=["EV-0101", "EV-0102"]))
    p07.judge(pid, "LO2", p07.JudgementIn(**ADVISOR, level="developing", evidence_ids=["EV-0101"]))
    p07.add_action(pid, p07.ActionIn(**ADVISOR, owner="student", due="2027-04-01",
                                     text="Add evidence for teamwork (LO3), such as meeting notes or peer feedback"))


def _end() -> None:
    pid = "PL-0001"
    set_today("2027-03-13")
    p07.acknowledge_log("LOG-03", p07.Actor(**SUPERVISOR))
    set_today("2027-03-19")
    p07.close_action("ACT-01", p07.CloseIn(**SUPERVISOR, closure="Meeting date agreed for 8 April; see EV-0103"))
    set_today("2027-04-08")
    log4 = p07.add_log(pid, p07.LogIn(**STUDENT, goal_id="G2", new_evidence_title="Station ops meeting slides and attendance note",
                                      text="Presented the delay-cause analysis at the station operations meeting. Led "
                                           "with one recommendation, then took questions."))
    p07.set_milestone("MS-3", p07.MilestoneIn(**SUPERVISOR, done=True))
    set_today("2027-04-09")
    p07.acknowledge_log(log4["log_id"], p07.Actor(**SUPERVISOR))
    set_today("2027-05-02")
    log5 = p07.add_log(pid, p07.LogIn(**STUDENT, goal_id="G3", new_evidence_title="Peer feedback from Priya Nair on joint delay analysis",
                                      text="Worked with Priya on the joint delay analysis and asked her for written "
                                           "feedback on how I share work."))
    p07.acknowledge_log(log5["log_id"], p07.Actor(**SUPERVISOR))
    p07.close_action("ACT-02", p07.CloseIn(**STUDENT, closure="EV-0104 peer feedback added"))
    set_today("2027-05-28")
    p07.employer_feedback(pid, p07.FeedbackIn(
        **SUPERVISOR, would_host="yes",
        text="Layla delivered a dashboard the ground-ops team now uses every week and presented clearly to duty "
             "managers. Next step: own a small analysis end to end with less check-in."))
    set_today("2027-06-01")
    p07.judge(pid, "LO1", p07.JudgementIn(**ADVISOR, level="achieved", evidence_ids=["EV-0101", "EV-0102"]))
    p07.judge(pid, "LO2", p07.JudgementIn(**ADVISOR, level="achieved", evidence_ids=["EV-0101", "EV-0103"]))
    p07.judge(pid, "LO3", p07.JudgementIn(**ADVISOR, level="developing", evidence_ids=["EV-0104"]))
    set_today("2027-06-02")
    # Period 2 work: shown in the log but never counted towards Period 1 outcomes.
    p07.add_log(pid, p07.LogIn(**STUDENT, goal_id="G1", new_evidence_title="Draft plan for night-shift dashboard (Period 2 work)",
                               text="Planned the night-shift version of the dashboard for next period with the ops leads."))
