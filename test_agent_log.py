"""
Unit tests for AgentLog system and DoD verification.
"""

import unittest
from schema import AttendanceRecord, Task, ExamEvent
from attendance_risk_agent import AttendanceRiskAgent
from planner_module import DeterministicConstraintSolver, ExamRevisionPlanner
from helpdesk_agent import GroundedHelpdeskAgent
from agent_log import (
    clear_logs,
    get_all_entries,
    get_recent_logs,
    run_with_logging,
    emit_log,
)


class TestAgentLogSystem(unittest.TestCase):

    def setUp(self):
        clear_logs()

    def test_dod_1_exact_4_ordered_log_entries_on_success(self):
        """DoD 1: Calling attendance-risk function produces exactly 4 correctly ordered log entries ending in 'passed'."""
        rec = AttendanceRecord(course="Physics", conducted_classes=30, attended_classes=25)
        res = AttendanceRiskAgent.evaluate_attendance(rec, remaining_classes=10)

        entries = get_all_entries()
        self.assertEqual(len(entries), 4, f"Expected exactly 4 log entries, got {len(entries)}")

        statuses = [e.status for e in entries]
        self.assertEqual(statuses, ["planning", "running", "verifying", "passed"])

        last_entry = entries[-1]
        self.assertEqual(last_entry.status, "passed")
        self.assertGreater(last_entry.checks_run, 0)
        self.assertEqual(last_entry.checks_passed, last_entry.checks_run)
        self.assertIsNone(last_entry.failure_reason)

    def test_dod_2_forced_failure_emits_failed_status_with_specific_reason(self):
        """DoD 2: Manually forcing a bad output produces a 'failed' status with a specific failure_reason."""
        def bad_compute():
            # Return corrupt dict where percent doesn't match attended/conducted
            return {
                "percent": 99.9, # False percentage
                "risk_level": "safe",
                "condonation_eligible": False,
                "recovery_classes_needed": 0,
                "recovery_impossible": False,
                "explanation": "Corrupted output"
            }

        rec = AttendanceRecord(course="Chemistry", conducted_classes=20, attended_classes=10)

        def bad_check(result):
            return AttendanceRiskAgent._verify_output(result, rec, remaining=5)

        run_with_logging(
            agent_name="Attendance-Risk Agent",
            action_description="Testing bad output verification",
            compute_fn=bad_compute,
            checks_fn=bad_check
        )

        entries = get_all_entries()
        self.assertEqual(len(entries), 4)
        statuses = [e.status for e in entries]
        self.assertEqual(statuses, ["planning", "running", "verifying", "failed"])

        last_entry = entries[-1]
        self.assertEqual(last_entry.status, "failed")
        self.assertIsNotNone(last_entry.failure_reason)
        self.assertIn("percent mismatch", last_entry.failure_reason)

    def test_dod_3_get_recent_logs_newest_first(self):
        """DoD 3: get_recent_logs returns entries sorted newest-first."""
        emit_log("AgentA", "Action 1", "planning")
        emit_log("AgentA", "Action 2", "passed")
        emit_log("AgentB", "Action 3", "failed", failure_reason="Test fail")

        recent = get_recent_logs(limit=10)
        self.assertEqual(len(recent), 3)

        # Newest first means Action 3 is index 0
        self.assertEqual(recent[0]["action"], "Action 3")
        self.assertEqual(recent[1]["action"], "Action 2")
        self.assertEqual(recent[2]["action"], "Action 1")

    def test_dod_4_all_modules_emit_logs(self):
        """DoD 4: Every existing module (attendance-risk, planner, revision planner, helpdesk) emits logs."""
        clear_logs()

        # 1. Attendance Risk
        rec = AttendanceRecord(course="Maths", conducted_classes=40, attended_classes=35)
        AttendanceRiskAgent.evaluate_attendance(rec)

        # 2. Planner
        tasks = [Task(title="Assignment 1", course="CS101", due_at="2026-11-05")]
        hours = {"2026-11-01": 4.0}
        DeterministicConstraintSolver.create_weekly_plan(tasks, hours)

        # 3. Revision Planner
        exams = [ExamEvent(class_id="C1", course="CS101", exam_date="2026-11-05", study_leave_days_before=2)]
        ExamRevisionPlanner.generate_revision_plan(exams, hours)

        # 4. Helpdesk
        agent = GroundedHelpdeskAgent()
        agent.answer_query("What is the fee for revaluation?")

        entries = get_all_entries()
        agent_names = {e.agent_name for e in entries}

        self.assertIn("Attendance-Risk Agent", agent_names)
        self.assertIn("Planner Agent", agent_names)
        self.assertIn("Exam-Revision Planner", agent_names)
        self.assertIn("Helpdesk Agent", agent_names)

        # Confirm each module emitted logs (at least 4 entries per top-level call)
        self.assertGreaterEqual(len(entries), 16)


if __name__ == "__main__":
    unittest.main()
