"""
Attendance-Risk & Condonation Agent for StudyOS-India.
Computes deterministic attendance risk levels, condonation eligibility, and recovery math
based on Indian UGC / AICTE academic guidelines.
"""

import math
from typing import Dict, Any, Optional
from schema import AttendanceRecord, SchemaValidator
from agent_log import run_with_logging

# Named Threshold Constants (UGC / AICTE Framework)
THRESHOLD_SAFE: float = 75.0            # Minimum attendance percentage for safe status
THRESHOLD_CONDONATION_MIN: float = 65.0 # Minimum attendance percentage for condonation eligibility


class AttendanceRiskAgent:

    @staticmethod
    def evaluate_attendance(
        record: AttendanceRecord,
        remaining_classes: int = 0,
        condonation_deadline: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Evaluates attendance risk, condonation eligibility, and recovery requirements.
        Conforms strictly to SCHEMA.md AttendanceRecord shape.
        Emits 4 AgentLog entries: planning -> running -> verifying -> passed/failed.
        """
        course = record.course or "Subject"

        def _compute():
            return AttendanceRiskAgent._compute_risk(record, remaining_classes, condonation_deadline)

        def _check(result):
            return AttendanceRiskAgent._verify_output(result, record, remaining_classes)

        return run_with_logging(
            agent_name="Attendance-Risk Agent",
            action_description=f"Generated AttendanceRecord for {course}",
            compute_fn=_compute,
            checks_fn=_check,
        )

    @staticmethod
    def _compute_risk(
        record: AttendanceRecord,
        remaining_classes: int,
        condonation_deadline: Optional[str],
    ) -> Dict[str, Any]:
        """Pure computation — no logging."""
        conducted = record.conducted_classes
        attended = record.attended_classes
        course = record.course or "Subject"

        # Calculate exact percentage
        if conducted > 0:
            percent = round((attended / conducted) * 100.0, 2)
        else:
            percent = 0.0

        record.percentage = percent

        # Determine Risk Level using named constants
        if percent >= THRESHOLD_SAFE:
            risk_level = "safe"
            condonation_eligible = False
        elif percent >= THRESHOLD_CONDONATION_MIN:
            risk_level = "shortage"
            condonation_eligible = True
        else:
            risk_level = "detained"
            condonation_eligible = False

        # Calculate maximum possible percentage if 100% future classes are attended
        total_semester_classes = conducted + remaining_classes
        if total_semester_classes > 0:
            max_possible_percent = round(((attended + remaining_classes) / total_semester_classes) * 100.0, 2)
        else:
            max_possible_percent = percent

        # Recovery Math
        recovery_impossible = False
        recovery_classes_needed: Optional[int] = None

        if percent >= THRESHOLD_SAFE:
            recovery_classes_needed = 0
            recovery_impossible = False
        else:
            if max_possible_percent < THRESHOLD_SAFE:
                recovery_impossible = True
                recovery_classes_needed = None
            else:
                recovery_impossible = False
                target_attended = (THRESHOLD_SAFE / 100.0) * total_semester_classes
                needed = math.ceil(target_attended - attended)
                recovery_classes_needed = max(1, needed)

        explanation = AttendanceRiskAgent._generate_explanation(
            course=course,
            percent=percent,
            attended=attended,
            conducted=conducted,
            risk_level=risk_level,
            condonation_eligible=condonation_eligible,
            recovery_classes_needed=recovery_classes_needed,
            recovery_impossible=recovery_impossible,
            max_possible_percent=max_possible_percent,
            remaining_classes=remaining_classes,
            condonation_deadline=condonation_deadline
        )

        return {
            "attendance_record": record.to_dict(),
            "percent": percent,
            "risk_level": risk_level,
            "condonation_eligible": condonation_eligible,
            "recovery_classes_needed": recovery_classes_needed,
            "recovery_impossible": recovery_impossible,
            "max_possible_percent": max_possible_percent,
            "explanation": explanation,
            "thresholds": {
                "safe": THRESHOLD_SAFE,
                "condonation_min": THRESHOLD_CONDONATION_MIN
            }
        }

    @staticmethod
    def _verify_output(result: Dict[str, Any], record: AttendanceRecord, remaining: int) -> tuple:
        """Run real Definition-of-Done assertions against the output. Returns (checks_run, checks_passed, failures)."""
        failures = []
        checks_run = 0

        # Check 1: percent matches attended/conducted math
        checks_run += 1
        expected_pct = round((record.attended_classes / record.conducted_classes) * 100.0, 2) if record.conducted_classes > 0 else 0.0
        if abs(result["percent"] - expected_pct) > 0.01:
            failures.append(f"percent mismatch: got {result['percent']}, expected {expected_pct}")

        # Check 2: risk_level correctly derived from percent
        checks_run += 1
        pct = result["percent"]
        if pct >= THRESHOLD_SAFE:
            expected_risk = "safe"
        elif pct >= THRESHOLD_CONDONATION_MIN:
            expected_risk = "shortage"
        else:
            expected_risk = "detained"
        if result["risk_level"] != expected_risk:
            failures.append(f"risk_level mismatch: got '{result['risk_level']}', expected '{expected_risk}' for {pct}%")

        # Check 3: condonation_eligible consistent with risk_level
        checks_run += 1
        expected_condonation = (expected_risk == "shortage")
        if result["condonation_eligible"] != expected_condonation:
            failures.append(f"condonation_eligible mismatch: got {result['condonation_eligible']}, expected {expected_condonation}")

        # Check 4: schema validation passes
        checks_run += 1
        val = SchemaValidator.validate_attendance_record(record)
        if not val.get("valid", False):
            failures.append(f"Schema validation failed: {val.get('errors', [])}")

        # Check 5: recovery math consistency
        checks_run += 1
        if result["recovery_impossible"]:
            if result["recovery_classes_needed"] is not None:
                failures.append("recovery_impossible=True but recovery_classes_needed is not None")
        elif result["risk_level"] != "safe" and result["recovery_classes_needed"] is not None:
            total = record.conducted_classes + remaining
            target = (THRESHOLD_SAFE / 100.0) * total
            expected_needed = max(1, math.ceil(target - record.attended_classes))
            if result["recovery_classes_needed"] != expected_needed:
                failures.append(f"recovery_classes_needed mismatch: got {result['recovery_classes_needed']}, expected {expected_needed}")

        # Check 6: required keys present
        checks_run += 1
        required_keys = {"percent", "risk_level", "condonation_eligible", "recovery_classes_needed", "recovery_impossible", "explanation"}
        missing = required_keys - set(result.keys())
        if missing:
            failures.append(f"Missing required keys: {missing}")

        checks_passed = checks_run - len(failures)
        return checks_run, checks_passed, failures

    @staticmethod
    def _generate_explanation(
        course: str,
        percent: float,
        attended: int,
        conducted: int,
        risk_level: str,
        condonation_eligible: bool,
        recovery_classes_needed: Optional[int],
        recovery_impossible: bool,
        max_possible_percent: float,
        remaining_classes: int,
        condonation_deadline: Optional[str]
    ) -> str:
        """Generates dynamic plain-language explanation from computed data."""
        if risk_level == "safe":
            return f"You're at {percent}% in {course} ({attended}/{conducted} classes). Your attendance is safe (above the {THRESHOLD_SAFE}% UGC/AICTE threshold)."

        if recovery_impossible:
            return (
                f"You're at {percent}% in {course} ({attended}/{conducted} classes). "
                f"Even if you attend all {remaining_classes} remaining classes, your maximum possible attendance is {max_possible_percent}%, "
                f"making recovery to {THRESHOLD_SAFE}% mathematically impossible. Status: Detained."
            )

        explanation = f"You're at {percent}% in {course} ({attended}/{conducted} classes)."

        if recovery_classes_needed is not None and recovery_classes_needed > 0:
            explanation += f" Attend your next {recovery_classes_needed} classes with zero misses to reach {THRESHOLD_SAFE}%."

        if condonation_eligible:
            deadline_str = f" before {condonation_deadline}" if condonation_deadline else ""
            explanation += f" Alternatively, you are eligible to apply for condonation (fineable shortage between {THRESHOLD_CONDONATION_MIN}% and {THRESHOLD_SAFE}%){deadline_str}."

        return explanation
