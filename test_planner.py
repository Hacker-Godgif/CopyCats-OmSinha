"""
Comprehensive Unit Test Suite for StudyOS-India Planner, Constraint Solver & Memory/Reflection Agent.
Verifies all 10 Definition of Done requirements:
1. 5 overlapping-deadline tasks produce zero double-bookings.
2. Every task slot is scheduled before its due_at.
3. Mid-week urgent task injection produces correct PlanDiff objects.
4. Attendance-risk flag reprioritizes course tasks.
5. 2-day vs 5-day study leave exam test: 2-day exam gets strictly more revision minutes.
6. Revision tasks pass standard double-booking/hours/due_at verifier checks.
7. Revision task PlanDiff reason references actual study_leave_days_before numbers.
8. Task completion persists and survives simulated SQLite restart.
9. Synthetic 1.5x history adjusts specific target course only, not globally.
10. Output validates against SCHEMA.md for Task, PlanDiff, and ExamEvent.
"""

import unittest
import os
import gc
from schema import Task, PlanDiff, ExamEvent, SchemaValidator
from planner_module import (
    PlanVerifier,
    DeterministicConstraintSolver,
    ExamRevisionPlanner,
    ReflectionMemoryStore
)

TEST_DB_PATH = "test_reflection.db"


class TestStudyOSPlannerAgent(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._cleanup_db()

    @classmethod
    def tearDownClass(cls):
        cls._cleanup_db()

    @classmethod
    def _cleanup_db(cls):
        gc.collect()
        if os.path.exists(TEST_DB_PATH):
            try:
                os.remove(TEST_DB_PATH)
            except Exception:
                pass

    # -------------------------------------------------------------
    # 1. ZERO DOUBLE-BOOKINGS (ASSERT PROGRAMMATICALLY)
    # -------------------------------------------------------------
    def test_1_zero_double_bookings_overlapping_tasks(self):
        tasks = [
            Task(title=f"Task {i}", course="CS101", due_at="2026-11-05")
            for i in range(1, 6)
        ]
        daily_hours = {"2026-11-01": 3.0, "2026-11-02": 3.0, "2026-11-03": 3.0}

        slots, diff = DeterministicConstraintSolver.create_weekly_plan(
            tasks, daily_hours, start_date="2026-11-01"
        )

        val_res = PlanVerifier.verify_plan(slots, daily_hours)
        self.assertTrue(val_res["valid"], f"Plan contains double booking or capacity errors: {val_res['errors']}")

    # -------------------------------------------------------------
    # 2. EVERY SLOT BEFORE DUE_AT
    # -------------------------------------------------------------
    def test_2_all_slots_scheduled_before_due_at(self):
        tasks = [
            Task(title="Assignment 1", course="MATH201", due_at="2026-11-03"),
            Task(title="Assignment 2", course="CS101", due_at="2026-11-02"),
            Task(title="Assignment 3", course="CS204", due_at="2026-11-04")
        ]
        daily_hours = {"2026-11-01": 4.0, "2026-11-02": 4.0, "2026-11-03": 4.0, "2026-11-04": 4.0}

        slots, _ = DeterministicConstraintSolver.create_weekly_plan(
            tasks, daily_hours, start_date="2026-11-01"
        )

        for slot in slots:
            slot_date = slot["date"]
            due_date = slot["due_at"].split("T")[0]
            self.assertLessEqual(slot_date, due_date, f"Slot on {slot_date} scheduled after due_at {due_date}")

    # -------------------------------------------------------------
    # 3. MID-WEEK URGENT TASK INJECTION EMITS PLANDIFF
    # -------------------------------------------------------------
    def test_3_mid_week_injection_emits_plandiff(self):
        initial_tasks = [
            Task(title="Task A", course="CS101", due_at="2026-11-05"),
            Task(title="Task B", course="MATH201", due_at="2026-11-06")
        ]
        daily_hours = {"2026-11-01": 4.0, "2026-11-02": 4.0, "2026-11-03": 4.0}

        old_slots, _ = DeterministicConstraintSolver.create_weekly_plan(
            initial_tasks, daily_hours, start_date="2026-11-01"
        )

        # Inject urgent task mid-week
        urgent_task = Task(title="Urgent Midterm Submission", course="CS302", due_at="2026-11-02")
        all_tasks = initial_tasks + [urgent_task]

        new_slots, diff = DeterministicConstraintSolver.create_weekly_plan(
            all_tasks, daily_hours, start_date="2026-11-01", existing_slots=old_slots
        )

        self.assertIsInstance(diff, PlanDiff)
        self.assertGreater(len(diff.added_tasks), 0)
        self.assertIn("Urgent Midterm Submission", str(diff.added_tasks))

        val_res = SchemaValidator.validate_plan_diff(diff)
        self.assertTrue(val_res["valid"])

    # -------------------------------------------------------------
    # 4. ATTENDANCE-RISK REPRIORITIZATION
    # -------------------------------------------------------------
    def test_4_attendance_risk_reprioritization(self):
        tasks = [
            Task(title="Physics Homework", course="Physics", due_at="2026-11-05"),
            Task(title="CS Homework", course="CS101", due_at="2026-11-05")
        ]
        daily_hours = {"2026-11-01": 1.0} # Only 1 slot available on Day 1

        # Flag Physics as attendance risk
        slots, diff = DeterministicConstraintSolver.create_weekly_plan(
            tasks, daily_hours, start_date="2026-11-01", attendance_risk_courses=["Physics"]
        )

        # Physics task must get scheduled on Day 1 (first slot)
        day_1_slots = [s for s in slots if s["date"] == "2026-11-01"]
        self.assertEqual(day_1_slots[0]["course"], "Physics")
        self.assertIn("Physics", diff.summary)

    # -------------------------------------------------------------
    # 5. 2-DAY VS 5-DAY REVISION MINUTES ALLOCATION
    # -------------------------------------------------------------
    def test_5_study_leave_weighted_revision_allocation(self):
        exam_2day = ExamEvent(class_id="CSE-A", course="Computer Networks", exam_date="2026-11-05", study_leave_days_before=2)
        exam_5day = ExamEvent(class_id="CSE-A", course="Database Systems", exam_date="2026-11-08", study_leave_days_before=5)

        exams = [exam_2day, exam_5day]
        allocations = ExamRevisionPlanner.compute_weighted_revision_allocation(exams, total_available_minutes=600)

        cn_mins = allocations["Computer Networks"]
        dbms_mins = allocations["Database Systems"]

        self.assertGreater(cn_mins, dbms_mins, f"2-day exam CN ({cn_mins} mins) did not get more time than 5-day exam DBMS ({dbms_mins} mins)")

    # -------------------------------------------------------------
    # 6. REVISION TASKS PASS STANDARD CONSTRAINT VERIFIER
    # -------------------------------------------------------------
    def test_6_revision_tasks_pass_constraint_verifier(self):
        exam_2day = ExamEvent(class_id="CSE-A", course="CN", exam_date="2026-11-05", study_leave_days_before=2)
        exam_5day = ExamEvent(class_id="CSE-A", course="DBMS", exam_date="2026-11-08", study_leave_days_before=5)

        daily_hours = {"2026-11-01": 4.0, "2026-11-02": 4.0, "2026-11-03": 4.0}
        _, slots, _ = ExamRevisionPlanner.generate_revision_plan([exam_2day, exam_5day], daily_hours, start_date="2026-11-01")

        val_res = PlanVerifier.verify_plan(slots, daily_hours)
        self.assertTrue(val_res["valid"], f"Revision plan failed constraint verifier: {val_res['errors']}")

    # -------------------------------------------------------------
    # 7. REVISION PLANDIFF REASON REFERENCES NUMBERS
    # -------------------------------------------------------------
    def test_7_revision_plandiff_references_study_leave_numbers(self):
        exam = ExamEvent(class_id="CSE-A", course="CN", exam_date="2026-11-05", study_leave_days_before=2)
        daily_hours = {"2026-11-01": 4.0}
        _, _, diff = ExamRevisionPlanner.generate_revision_plan([exam], daily_hours, start_date="2026-11-01")

        self.assertIn("2 study-leave days", diff.summary)

    # -------------------------------------------------------------
    # 8. SQLITE PERSISTENCE SURVIVES RESTART
    # -------------------------------------------------------------
    def test_8_sqlite_persistence_survives_restart(self):
        db_file = "test_restart.db"
        if os.path.exists(db_file):
            try: os.remove(db_file)
            except Exception: pass

        store = ReflectionMemoryStore(db_path=db_file)
        store.log_task_completion(task_id="T101", course="Physics", est_minutes=60, actual_minutes=90, status="completed")
        store.log_task_completion(task_id="T102", course="Physics", est_minutes=60, actual_minutes=90, status="completed")

        # Simulate restart by instantiating new ReflectionMemoryStore object on same DB
        store_restarted = ReflectionMemoryStore(db_path=db_file)
        mult = store_restarted.get_course_multiplier("Physics")

        self.assertEqual(mult, 1.5, f"Expected 1.5 multiplier after restart, got {mult}")

        if os.path.exists(db_file):
            try: os.remove(db_file)
            except Exception: pass

    # -------------------------------------------------------------
    # 9. COURSE-SPECIFIC 1.5x RE-ESTIMATION
    # -------------------------------------------------------------
    def test_9_course_specific_reestimation(self):
        db_file = "test_course.db"
        if os.path.exists(db_file):
            try: os.remove(db_file)
            except Exception: pass

        store = ReflectionMemoryStore(db_path=db_file)
        # Log 2 Physics tasks taking 1.5x longer
        store.log_task_completion(task_id="P1", course="Physics", est_minutes=60, actual_minutes=90, status="completed")
        store.log_task_completion(task_id="P2", course="Physics", est_minutes=60, actual_minutes=90, status="completed")

        # Log 2 CS tasks matching estimate (1.0x)
        store.log_task_completion(task_id="C1", course="CS101", est_minutes=60, actual_minutes=60, status="completed")
        store.log_task_completion(task_id="C2", course="CS101", est_minutes=60, actual_minutes=60, status="completed")

        physics_mult = store.get_course_multiplier("Physics")
        cs_mult = store.get_course_multiplier("CS101")

        self.assertEqual(physics_mult, 1.50)
        self.assertEqual(cs_mult, 1.0)

        summary, diff = store.reflect()
        self.assertIn("Physics", summary)
        self.assertIn("50% longer", summary)
        self.assertNotIn("CS101 tasks are taking", summary)

        if os.path.exists(db_file):
            try: os.remove(db_file)
            except Exception: pass

    # -------------------------------------------------------------
    # 10. OUTPUT SCHEMA VALIDATION (TASK, PLANDIFF, EXAMEVENT)
    # -------------------------------------------------------------
    def test_10_output_schema_validation(self):
        # 1. Task
        t = Task(title="Test Task", course="CS101", source_ref="Syllabus line 1")
        self.assertTrue(SchemaValidator.validate_task(t)["valid"])

        # 2. PlanDiff
        p = PlanDiff(added_tasks=[t.to_dict()], summary="Added task")
        self.assertTrue(SchemaValidator.validate_plan_diff(p)["valid"])

        # 3. ExamEvent
        e = ExamEvent(class_id="CSE-A", course="CS101", exam_date="2026-11-05", study_leave_days_before=3)
        self.assertTrue(SchemaValidator.validate_exam_event(e)["valid"])


if __name__ == "__main__":
    unittest.main()
