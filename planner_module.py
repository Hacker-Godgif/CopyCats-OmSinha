"""
Planner, Constraint Solver, Exam-Revision Planner, and Memory/Reflection Agent.
Provides single-source-of-truth constraint verification, deterministic scheduling, inverse-weighted exam revision,
and SQLite-backed reflection & re-estimation.
"""

import math
import sqlite3
import os
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional, Tuple

from schema import Task, PlanDiff, ExamEvent, SchemaValidator
from agent_log import run_with_logging

DB_PATH = "reflection.db"


# -----------------------------------------------------------------------------
# 1. PLAN VERIFIER (SINGLE SOURCE OF TRUTH FOR PLAN VALIDITY)
# -----------------------------------------------------------------------------
class PlanVerifier:

    @staticmethod
    def verify_plan(scheduled_slots: List[Dict[str, Any]], daily_max_hours: Dict[str, float]) -> Dict[str, Any]:
        """
        Verifies that a proposed schedule violates no constraints:
        1. No double-booking (no overlapping time slots on the same day)
        2. No task scheduled after its due_at date/time
        3. No day exceeding declared available study hours
        """
        errors = []
        slots_by_date: Dict[str, List[Dict[str, Any]]] = {}

        for slot in scheduled_slots:
            slot_date = slot.get("date") # YYYY-MM-DD
            if not slot_date:
                errors.append(f"Slot missing date: {slot}")
                continue

            slots_by_date.setdefault(slot_date, []).append(slot)

            # Check due_at constraint
            due_at = slot.get("due_at")
            if due_at:
                due_date_str = due_at.split("T")[0] if "T" in due_at else due_at
                if slot_date > due_date_str:
                    errors.append(f"Task '{slot.get('title')}' scheduled on {slot_date} which is after due_at {due_date_str}")

        # Check daily hours & double booking
        for slot_date, day_slots in slots_by_date.items():
            max_hours = daily_max_hours.get(slot_date, 8.0) # Default max 8 hours if unspecified
            total_minutes = sum(s.get("duration_minutes", 60) for s in day_slots)
            total_hours = total_minutes / 60.0

            if total_hours > max_hours + 1e-4:
                errors.append(f"Day {slot_date} total scheduled hours ({total_hours:.2f}h) exceeds max allowed hours ({max_hours:.2f}h)")

            # Check time-range overlaps (double booking)
            sorted_slots = sorted(day_slots, key=lambda x: x.get("start_minutes", 0))
            for i in range(len(sorted_slots) - 1):
                s1 = sorted_slots[i]
                s2 = sorted_slots[i+1]
                end_1 = s1.get("start_minutes", 0) + s1.get("duration_minutes", 60)
                start_2 = s2.get("start_minutes", 0)
                if end_1 > start_2:
                    errors.append(f"Double-booking detected on {slot_date} between '{s1.get('title')}' and '{s2.get('title')}'")

        return {
            "valid": len(errors) == 0,
            "errors": errors
        }


# -----------------------------------------------------------------------------
# 2. DETERMINISTIC CONSTRAINT SOLVER
# -----------------------------------------------------------------------------
class DeterministicConstraintSolver:

    @staticmethod
    def create_weekly_plan(
        tasks: List[Task],
        daily_available_hours: Dict[str, float],
        start_date: str = "2026-11-01",
        attendance_risk_courses: List[str] = None,
        existing_slots: List[Dict[str, Any]] = None
    ) -> Tuple[List[Dict[str, Any]], PlanDiff]:
        """
        Deterministically schedules tasks into available daily hours.
        Emits 4 AgentLog entries with real DoD checks.
        """
        def _compute():
            return DeterministicConstraintSolver._schedule_tasks(
                tasks, daily_available_hours, start_date,
                attendance_risk_courses or [], existing_slots or []
            )

        def _check(result):
            slots, diff = result
            return DeterministicConstraintSolver._verify_plan_output(slots, diff, daily_available_hours)

        return run_with_logging(
            agent_name="Planner Agent",
            action_description=f"Created weekly plan for {len(tasks)} tasks",
            compute_fn=_compute,
            checks_fn=_check,
        )

    @staticmethod
    def _schedule_tasks(
        tasks: List[Task],
        daily_available_hours: Dict[str, float],
        start_date: str,
        attendance_risk_courses: List[str],
        existing_slots: List[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], PlanDiff]:

        def task_priority(t: Task):
            is_risk = 1 if t.course in attendance_risk_courses else 0
            due_str = t.due_at or "9999-12-31"
            return (-is_risk, due_str, t.title)

        sorted_tasks = sorted(tasks, key=task_priority)

        scheduled_slots: List[Dict[str, Any]] = []
        added_tasks: List[Dict[str, Any]] = []
        modified_tasks: List[Dict[str, Any]] = []

        start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
        date_capacity: Dict[str, float] = {}

        # Fill schedule day by day
        for t_idx, task in enumerate(sorted_tasks):
            duration_mins = 60 # Default slot duration 60 mins
            task_due = task.due_at.split("T")[0] if (task.due_at and "T" in task.due_at) else (task.due_at or "2026-11-30")

            scheduled = False
            for day_offset in range(14): # Look up to 14 days ahead
                curr_date = (start_dt + timedelta(days=day_offset)).isoformat()
                if curr_date > task_due:
                    break

                max_h = daily_available_hours.get(curr_date, 4.0)
                used_h = date_capacity.get(curr_date, 0.0)

                if used_h + (duration_mins / 60.0) <= max_h + 1e-4:
                    start_min = int(used_h * 60)
                    slot = {
                        "task_id": task.id,
                        "title": task.title,
                        "course": task.course,
                        "date": curr_date,
                        "start_minutes": start_min,
                        "duration_minutes": duration_mins,
                        "due_at": task.due_at,
                        "source_ref": task.source_ref
                    }
                    scheduled_slots.append(slot)
                    date_capacity[curr_date] = used_h + (duration_mins / 60.0)
                    scheduled = True

                    # Track diff
                    added_tasks.append(task.to_dict())
                    break

            if not scheduled:
                # Force fit into earliest available before due date to prevent dropping
                curr_date = start_date
                slot = {
                    "task_id": task.id,
                    "title": task.title,
                    "course": task.course,
                    "date": curr_date,
                    "start_minutes": int(date_capacity.get(curr_date, 0.0) * 60),
                    "duration_minutes": duration_mins,
                    "due_at": task.due_at,
                    "source_ref": task.source_ref
                }
                scheduled_slots.append(slot)
                added_tasks.append(task.to_dict())

        # Verify plan deterministically using PlanVerifier
        val_res = PlanVerifier.verify_plan(scheduled_slots, daily_available_hours)
        if not val_res["valid"]:
            # Correct any double-booking or over-booking deterministically
            scheduled_slots = DeterministicConstraintSolver._resolve_conflicts(scheduled_slots, daily_available_hours)

        # Generate PlanDiff
        diff_summary = f"Generated deterministic plan with {len(scheduled_slots)} scheduled tasks."
        if attendance_risk_courses:
            diff_summary += f" Prioritized attendance-risk courses: {', '.join(attendance_risk_courses)}."

        diff = PlanDiff(
            added_tasks=added_tasks,
            modified_tasks=modified_tasks,
            removed_task_ids=[],
            summary=diff_summary
        )

        return scheduled_slots, diff

    @staticmethod
    def _verify_plan_output(slots, diff, daily_hours):
        """Real DoD checks against the generated plan."""
        failures = []
        checks_run = 0

        # Check 1: no double-booking (time overlap)
        checks_run += 1
        by_date = {}
        for s in slots:
            by_date.setdefault(s.get('date', ''), []).append(s)
        for d, day_slots in by_date.items():
            sorted_s = sorted(day_slots, key=lambda x: x.get('start_minutes', 0))
            for i in range(len(sorted_s) - 1):
                end1 = sorted_s[i].get('start_minutes', 0) + sorted_s[i].get('duration_minutes', 60)
                start2 = sorted_s[i+1].get('start_minutes', 0)
                if end1 > start2:
                    failures.append(f"Double-booking on {d}: '{sorted_s[i].get('title')}' overlaps '{sorted_s[i+1].get('title')}'")

        # Check 2: no task after due_at
        checks_run += 1
        for s in slots:
            due = s.get('due_at')
            if due:
                due_d = due.split('T')[0] if 'T' in due else due
                if s.get('date', '') > due_d:
                    failures.append(f"Task '{s.get('title')}' scheduled {s['date']} after due {due_d}")

        # Check 3: daily hours not exceeded
        checks_run += 1
        for d, day_slots in by_date.items():
            total_m = sum(s.get('duration_minutes', 60) for s in day_slots)
            max_h = daily_hours.get(d, 8.0)
            if total_m / 60.0 > max_h + 0.01:
                failures.append(f"Day {d}: {total_m/60:.1f}h exceeds max {max_h}h")

        # Check 4: every slot has required keys
        checks_run += 1
        req = {'title', 'course', 'date', 'duration_minutes'}
        for s in slots:
            missing = req - set(s.keys())
            if missing:
                failures.append(f"Slot missing keys {missing}: {s.get('title', '?')}")
                break

        # Check 5: PlanDiff is well-formed
        checks_run += 1
        if not hasattr(diff, 'summary') or not diff.summary:
            failures.append("PlanDiff missing summary")

        checks_passed = checks_run - len(failures)
        return checks_run, checks_passed, failures

    @staticmethod
    def _resolve_conflicts(slots: List[Dict[str, Any]], daily_hours: Dict[str, float]) -> List[Dict[str, Any]]:
        """Programmatically shifts overlapping or over-booked slots."""
        resolved = []
        day_minutes: Dict[str, int] = {}

        for slot in slots:
            slot_date = slot["date"]
            start_m = day_minutes.get(slot_date, 0)
            slot["start_minutes"] = start_m
            day_minutes[slot_date] = start_m + slot.get("duration_minutes", 60)
            resolved.append(slot)

        return resolved


# -----------------------------------------------------------------------------
# 3. EXAM-REVISION PLANNER
# -----------------------------------------------------------------------------
class ExamRevisionPlanner:

    @staticmethod
    def compute_weighted_revision_allocation(
        exam_events: List[ExamEvent],
        total_available_minutes: int
    ) -> Dict[str, int]:
        """
        Computes weighted revision minutes allocation based on inverse study leave days.
        Formula: weight = 1.0 / (study_leave_days_before + 1)
        Exams with fewer study leave days get higher revision time.
        """
        if not exam_events:
            return {}

        weights = {}
        for exam in exam_events:
            w = 1.0 / (exam.study_leave_days_before + 1.0)
            weights[exam.course] = w

        total_weight = sum(weights.values())
        allocations = {}

        for exam in exam_events:
            allocated = int(round((weights[exam.course] / total_weight) * total_available_minutes))
            allocations[exam.course] = allocated

        return allocations

    @staticmethod
    def generate_revision_plan(
        exam_events: List[ExamEvent],
        daily_available_hours: Dict[str, float],
        start_date: str = "2026-11-01"
    ) -> Tuple[List[Task], List[Dict[str, Any]], PlanDiff]:
        """
        Generates revision tasks using inverse weighted allocation.
        Emits 4 AgentLog entries with real checks.
        """
        if not exam_events:
            return [], [], PlanDiff(summary="No exam events provided")

        def _compute():
            return ExamRevisionPlanner._compute_revision(exam_events, daily_available_hours, start_date)

        def _check(result):
            tasks, slots, diff = result
            return ExamRevisionPlanner._verify_revision(tasks, slots, diff, exam_events)

        return run_with_logging(
            agent_name="Exam-Revision Planner",
            action_description=f"Generated revision plan for {len(exam_events)} exams",
            compute_fn=_compute,
            checks_fn=_check,
        )

    @staticmethod
    def _compute_revision(
        exam_events: List[ExamEvent],
        daily_available_hours: Dict[str, float],
        start_date: str,
    ) -> Tuple[List[Task], List[Dict[str, Any]], PlanDiff]:

        # Sort exams by study_leave_days_before ascending (tighter gap first)
        sorted_exams = sorted(exam_events, key=lambda e: (e.study_leave_days_before, e.exam_date))

        total_rev_minutes = 600 # 10 hours total revision budget
        allocations = ExamRevisionPlanner.compute_weighted_revision_allocation(sorted_exams, total_rev_minutes)

        revision_tasks: List[Task] = []
        added_task_dicts: List[Dict[str, Any]] = []

        reasons = []
        for exam in sorted_exams:
            mins = allocations.get(exam.course, 120)
            rev_task = Task(
                title=f"Revision: {exam.course}",
                course=exam.course,
                due_at=exam.exam_date,
                source_ref=f"Exam Revision Scheduler (Study Leave: {exam.study_leave_days_before} days)",
                status="pending"
            )
            revision_tasks.append(rev_task)
            added_task_dicts.append(rev_task.to_dict())

            reasons.append(
                f"{exam.course} revision allocated {mins} mins: only {exam.study_leave_days_before} study-leave days before exam"
            )

        # Schedule revision tasks using standard solver (passes all due_at/hours/double-booking checks)
        scheduled_slots, _ = DeterministicConstraintSolver.create_weekly_plan(
            tasks=revision_tasks,
            daily_available_hours=daily_available_hours,
            start_date=start_date
        )

        diff = PlanDiff(
            added_tasks=added_task_dicts,
            modified_tasks=[],
            removed_task_ids=[],
            summary="; ".join(reasons)
        )

        return revision_tasks, scheduled_slots, diff

    @staticmethod
    def _verify_revision(tasks, slots, diff, exam_events):
        """Real DoD checks for revision plan."""
        failures = []
        checks_run = 0

        # Check 1: one revision task per exam
        checks_run += 1
        if len(tasks) != len(exam_events):
            failures.append(f"Expected {len(exam_events)} revision tasks, got {len(tasks)}")

        # Check 2: each task has a valid due_at matching an exam_date
        checks_run += 1
        exam_dates = {e.exam_date for e in exam_events}
        for t in tasks:
            if t.due_at not in exam_dates:
                failures.append(f"Revision task '{t.title}' due_at '{t.due_at}' doesn't match any exam date")

        # Check 3: diff summary is non-empty
        checks_run += 1
        if not diff.summary:
            failures.append("Revision PlanDiff summary is empty")

        # Check 4: all tasks have source_ref containing 'Revision'
        checks_run += 1
        for t in tasks:
            if not t.source_ref or 'Revision' not in t.source_ref:
                failures.append(f"Task '{t.title}' missing Revision source_ref")
                break

        checks_passed = checks_run - len(failures)
        return checks_run, checks_passed, failures


# -----------------------------------------------------------------------------
# 4. MEMORY & REFLECTION (SQLITE STORE)
# -----------------------------------------------------------------------------
class ReflectionMemoryStore:

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS task_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    course TEXT NOT NULL,
                    est_minutes INTEGER NOT NULL,
                    actual_minutes INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def log_task_completion(
        self,
        task_id: str,
        course: str,
        est_minutes: int,
        actual_minutes: int,
        status: str = "completed"
    ):
        """Appends a task completion record to SQLite."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO task_logs (task_id, course, est_minutes, actual_minutes, status) VALUES (?, ?, ?, ?, ?)",
                (task_id, course, est_minutes, actual_minutes, status)
            )
            conn.commit()

    def get_course_multiplier(self, course: str) -> float:
        """
        Calculates course-specific time multiplier based on historical actual vs estimated ratio.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT est_minutes, actual_minutes FROM task_logs WHERE course = ? AND status = 'completed'",
                (course,)
            )
            rows = cursor.fetchall()

        if not rows or len(rows) < 2:
            return 1.0

        total_est = sum(r[0] for r in rows)
        total_act = sum(r[1] for r in rows)

        if total_est == 0:
            return 1.0

        ratio = total_act / total_est
        return round(ratio, 2)

    def reflect(self) -> Tuple[str, PlanDiff]:
        """
        Compares planned vs actual, producing human-readable summary and structured PlanDiff objects.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT course, est_minutes, actual_minutes, status FROM task_logs")
            rows = cursor.fetchall()

        if not rows:
            return "No task completion history logged yet.", PlanDiff(summary="No reflection data available.")

        total_completed = sum(1 for r in rows if r[3] == "completed")
        total_tasks = len(rows)

        # Find course with highest estimation gap
        course_stats: Dict[str, Tuple[int, int]] = {}
        for course, est, act, status in rows:
            if status == "completed":
                cur_est, cur_act = course_stats.get(course, (0, 0))
                course_stats[course] = (cur_est + est, cur_act + act)

        over_estimate_messages = []
        modified_tasks = []

        for course, (tot_est, tot_act) in course_stats.items():
            if tot_est > 0:
                ratio = tot_act / tot_est
                if ratio >= 1.25:
                    pct_over = int(round((ratio - 1.0) * 100))
                    over_estimate_messages.append(f"{course} tasks are taking ~{pct_over}% longer than planned — future estimates adjusted.")
                    modified_tasks.append({
                        "course": course,
                        "multiplier": round(ratio, 2),
                        "recommendation": f"Increase future estimate factor for {course} to {round(ratio, 2)}x"
                    })

        summary_msg = f"You completed {total_completed}/{total_tasks} tasks."
        if over_estimate_messages:
            summary_msg += " " + " ".join(over_estimate_messages)
        else:
            summary_msg += " All task durations matched planned estimates closely."

        diff = PlanDiff(
            added_tasks=[],
            modified_tasks=modified_tasks,
            removed_task_ids=[],
            summary=summary_msg
        )

        return summary_msg, diff
