"""
Unit Test Suite for Attendance-Risk & Condonation Agent.
Verifies all 5 Definition of Done requirements:
1. Safe (>=75%), Shortage/Fineable (65-74%), Detained (<65%), and exact edge cases at 75.0% and 65.0%.
2. Hand-computed recovery math calculation.
3. Recovery impossible case.
4. Validation against SCHEMA.md AttendanceRecord shape.
5. Data-driven explanation string generation.
"""

import unittest
import math
from schema import AttendanceRecord, SchemaValidator
from attendance_risk_agent import (
    AttendanceRiskAgent,
    THRESHOLD_SAFE,
    THRESHOLD_CONDONATION_MIN
)


class TestAttendanceRiskAgent(unittest.TestCase):

    # -------------------------------------------------------------
    # 1. THRESHOLD TESTS (SAFE, SHORTAGE, DETAINED, EDGE CASES)
    # -------------------------------------------------------------
    def test_safe_status(self):
        # 80/100 = 80.0% -> safe
        rec = AttendanceRecord(course="Physics", conducted_classes=100, attended_classes=80)
        res = AttendanceRiskAgent.evaluate_attendance(rec, remaining_classes=10)
        self.assertEqual(res["risk_level"], "safe")
        self.assertFalse(res["condonation_eligible"])
        self.assertFalse(res["recovery_impossible"])
        self.assertEqual(res["recovery_classes_needed"], 0)

    def test_edge_case_exact_75_percent(self):
        # 75/100 = 75.0% -> safe
        rec = AttendanceRecord(course="Physics", conducted_classes=100, attended_classes=75)
        res = AttendanceRiskAgent.evaluate_attendance(rec, remaining_classes=10)
        self.assertEqual(res["percent"], 75.0)
        self.assertEqual(res["risk_level"], "safe")
        self.assertFalse(res["condonation_eligible"])

    def test_shortage_condonation_eligible(self):
        # 70/100 = 70.0% -> shortage (65% to 75%)
        rec = AttendanceRecord(course="Chemistry", conducted_classes=100, attended_classes=70)
        res = AttendanceRiskAgent.evaluate_attendance(rec, remaining_classes=20)
        self.assertEqual(res["risk_level"], "shortage")
        self.assertTrue(res["condonation_eligible"])
        self.assertFalse(res["recovery_impossible"])

    def test_edge_case_exact_65_percent(self):
        # 65/100 = 65.0% -> shortage / condonation eligible
        rec = AttendanceRecord(course="Chemistry", conducted_classes=100, attended_classes=65)
        res = AttendanceRiskAgent.evaluate_attendance(rec, remaining_classes=20)
        self.assertEqual(res["percent"], 65.0)
        self.assertEqual(res["risk_level"], "shortage")
        self.assertTrue(res["condonation_eligible"])

    def test_detained_status(self):
        # 60/100 = 60.0% -> detained (<65%)
        rec = AttendanceRecord(course="Mathematics", conducted_classes=100, attended_classes=60)
        res = AttendanceRiskAgent.evaluate_attendance(rec, remaining_classes=10)
        self.assertEqual(res["risk_level"], "detained")
        self.assertFalse(res["condonation_eligible"])

    # -------------------------------------------------------------
    # 2. HAND-COMPUTED RECOVERY MATH TEST
    # Hand-computed scenario:
    # Conducted = 29, Attended = 20 (percent = 20/29 = 68.97% < 75%)
    # Remaining classes = 10
    # Total semester classes = 29 + 10 = 39 classes
    # 75% target of 39 classes = 0.75 * 39 = 29.25
    # Additional classes needed = ceil(29.25 - 20) = ceil(9.25) = 10 classes.
    # Verification: 20 + 10 = 30 / 39 = 76.92% >= 75%.
    # -------------------------------------------------------------
    def test_recovery_math_hand_computed(self):
        rec = AttendanceRecord(course="Physics", conducted_classes=29, attended_classes=20)
        res = AttendanceRiskAgent.evaluate_attendance(rec, remaining_classes=10)

        self.assertFalse(res["recovery_impossible"])
        self.assertEqual(res["recovery_classes_needed"], 10, "Expected exactly 10 recovery classes needed")
        self.assertTrue(res["condonation_eligible"])

    # -------------------------------------------------------------
    # 3. RECOVERY IMPOSSIBLE TEST
    # Scenario:
    # Conducted = 30, Attended = 15 (percent = 50.0%)
    # Remaining classes = 5
    # Max possible attendance = (15 + 5) / (30 + 5) = 20 / 35 = 57.14% < 75.0%
    # Result: recovery_impossible = True, recovery_classes_needed = None
    # -------------------------------------------------------------
    def test_recovery_impossible(self):
        rec = AttendanceRecord(course="Biology", conducted_classes=30, attended_classes=15)
        res = AttendanceRiskAgent.evaluate_attendance(rec, remaining_classes=5)

        self.assertTrue(res["recovery_impossible"])
        self.assertIsNone(res["recovery_classes_needed"])
        self.assertEqual(res["max_possible_percent"], 57.14)
        self.assertIn("mathematically impossible", res["explanation"].lower())

    # -------------------------------------------------------------
    # 4. SCHEMA CONFORMANCE TEST
    # -------------------------------------------------------------
    def test_schema_conformance(self):
        rec = AttendanceRecord(course="Computer Science", conducted_classes=50, attended_classes=40)
        res = AttendanceRiskAgent.evaluate_attendance(rec, remaining_classes=10)

        # Validate the underlying AttendanceRecord against SchemaValidator
        val_res = SchemaValidator.validate_attendance_record(rec)
        self.assertTrue(val_res["valid"], f"AttendanceRecord failed schema validation: {val_res['errors']}")

    # -------------------------------------------------------------
    # 5. DYNAMIC EXPLANATION GENERATION TEST
    # -------------------------------------------------------------
    def test_dynamic_explanation_generation(self):
        rec = AttendanceRecord(course="Data Structures", conducted_classes=40, attended_classes=27)
        res = AttendanceRiskAgent.evaluate_attendance(rec, remaining_classes=20)

        explanation = res["explanation"]
        self.assertIn("Data Structures", explanation)
        self.assertIn("67.5%", explanation)
        self.assertTrue("75%" in explanation or "75.0%" in explanation)
        self.assertIn("condonation", explanation.lower())


if __name__ == "__main__":
    unittest.main()
