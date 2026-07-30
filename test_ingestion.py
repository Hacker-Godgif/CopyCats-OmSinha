"""
Comprehensive Unit Test Suite for StudyOS-India Ingestion Agent.
Tests:
1. Clean Syllabus Extraction Accuracy (>= 90%) with source_ref.
2. Messy / Scanned Timetable manual review flagging.
3. Malformed Attendance CSV manual review flagging.
4. Datesheet Study Leave Days exact arithmetic (hand-verified).
5. Mock Classroom import Task schema validation parity.
6. Schema Validator on all 5 core schema shapes.
"""

import unittest
import os
from schema import Task, AttendanceRecord, ExamEvent, PlanDiff, HelpdeskAnswer, SchemaValidator
from date_parser import parse_indian_date
from syllabus_parser import SyllabusParser
from attendance_parser import AttendanceParser
from datesheet_parser import DatesheetParser
from classroom_importer import ClassroomImporter
from timetable_parser import TimetableParser
from sample_generator import generate_samples


class TestStudyOSIngestionAgent(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        generate_samples()

    # -------------------------------------------------------------
    # 1. CLEAN SYLLABUS EXTRACTION (>= 90% accuracy & source_ref)
    # -------------------------------------------------------------
    def test_clean_syllabus_extraction(self):
        with open("sample_syllabus.txt", "r", encoding="utf-8") as f:
            content = f.read()

        tasks = SyllabusParser.parse_syllabus_text(content, source_filename="Syllabus.txt", course_name="CS101")
        
        # We expect 10 stated deadlines in sample_syllabus.txt
        self.assertGreaterEqual(len(tasks), 9, f"Extracted {len(tasks)} tasks out of 10 expected deadlines (<90% threshold)")

        # Verify due_at and source_ref presence
        tasks_with_valid_dates = [t for t in tasks if t.due_at is not None]
        accuracy = (len(tasks_with_valid_dates) / 10.0) * 100.0
        self.assertGreaterEqual(accuracy, 90.0, f"Deadline extraction accuracy was {accuracy}%, expected >= 90%")

        for t in tasks:
            self.assertTrue(t.source_ref.startswith("Syllabus.txt page"), f"Invalid source_ref: {t.source_ref}")
            self.assertEqual(t.course, "CS101")
            val_res = SchemaValidator.validate_task(t)
            self.assertTrue(val_res["valid"], f"Task failed schema validation: {val_res['errors']}")

    # -------------------------------------------------------------
    # 2. MESSY / SCANNED PDF TIMETABLE (MANUAL REVIEW FLAG)
    # -------------------------------------------------------------
    def test_messy_scanned_timetable_flagging(self):
        with open("sample_scanned_timetable.txt", "r", encoding="utf-8") as f:
            content = f.read()

        tasks = TimetableParser.parse_timetable_text(content, source_name="ScannedTimetable.pdf", is_scanned=True)
        self.assertGreater(len(tasks), 0, "No tasks generated from scanned timetable")

        # Every task from scanned timetable must be flagged needs_manual_review=True
        flagged = [t for t in tasks if t.needs_manual_review]
        self.assertEqual(len(flagged), len(tasks), "Scanned/low-confidence timetable items were not flagged for manual review")

    # -------------------------------------------------------------
    # 3. MALFORMED ATTENDANCE CSV (MANUAL REVIEW FLAG)
    # -------------------------------------------------------------
    def test_malformed_attendance_csv(self):
        with open("sample_attendance_malformed.csv", "r", encoding="utf-8") as f:
            csv_content = f.read()

        records = AttendanceParser.parse_csv_content(csv_content)
        self.assertEqual(len(records), 4, f"Expected 4 attendance records, got {len(records)}")

        # Row 1: Attended (45) > Conducted (40) -> Flagged
        self.assertTrue(records[0].needs_manual_review)
        self.assertIn("exceeds conducted", records[0].review_reason.lower())

        # Row 2: Conducted = 0 -> Flagged
        self.assertTrue(records[1].needs_manual_review)
        self.assertIn("division by zero", records[1].review_reason.lower())

        # Row 3: Conducted = -10 -> Flagged
        self.assertTrue(records[2].needs_manual_review)
        self.assertIn("negative", records[2].review_reason.lower())

        # Row 4: Conducted = invalid_num -> Flagged
        self.assertTrue(records[3].needs_manual_review)
        self.assertIn("invalid", records[3].review_reason.lower())

    # -------------------------------------------------------------
    # 4. EXAM DATESHEET STUDY LEAVE DAYS CALCULATION
    # Hand-verified math:
    # Term Start: 2026-11-01
    # Exam 1 (2026-11-05): (Nov 5 - Nov 1) - 1 = 3 days
    # Exam 2 (2026-11-08): (Nov 8 - Nov 5) - 1 = 2 days
    # Exam 3 (2026-11-09): (Nov 9 - Nov 8) - 1 = 0 days
    # Exam 4 (2026-11-14): (Nov 14 - Nov 9) - 1 = 4 days
    # -------------------------------------------------------------
    def test_datesheet_study_leave_calculation(self):
        with open("sample_datesheet.txt", "r", encoding="utf-8") as f:
            content = f.read()

        events = DatesheetParser.parse_datesheet_text(content, class_id="CSE-2026-A", term_start_date="2026-11-01")
        self.assertEqual(len(events), 4, f"Expected 4 exam events, got {len(events)}")

        expected_leave_days = [3, 2, 0, 4]
        expected_dates = ["2026-11-05", "2026-11-08", "2026-11-09", "2026-11-14"]

        for idx, event in enumerate(events):
            self.assertEqual(event.exam_date, expected_dates[idx], f"Exam {idx+1} date mismatch")
            self.assertEqual(
                event.study_leave_days_before,
                expected_leave_days[idx],
                f"Exam {idx+1} ({event.course}) expected {expected_leave_days[idx]} study leave days, got {event.study_leave_days_before}"
            )
            val_res = SchemaValidator.validate_exam_event(event)
            self.assertTrue(val_res["valid"], f"ExamEvent failed validation: {val_res['errors']}")

    # -------------------------------------------------------------
    # 5. MOCK CLASSROOM IMPORT PARITY
    # -------------------------------------------------------------
    def test_mock_classroom_import_parity(self):
        tasks = ClassroomImporter.import_mock_assignments()
        self.assertGreater(len(tasks), 0)

        for t in tasks:
            self.assertEqual(t.source_ref, "Mock Classroom Import")
            # All Classroom tasks must pass the exact same validator as syllabus tasks
            val_res = SchemaValidator.validate_task(t)
            self.assertTrue(val_res["valid"], f"Classroom Task failed schema validation: {val_res['errors']}")

    # -------------------------------------------------------------
    # 6. ALL SCHEMA VALIDATOR EXECUTION
    # -------------------------------------------------------------
    def test_schema_validator_all_types(self):
        # 1. Task
        t = Task(title="Test Task", course="CS101", source_ref="Test.txt")
        self.assertTrue(SchemaValidator.validate(t)["valid"])

        # 2. AttendanceRecord
        a = AttendanceRecord(course="CS101", conducted_classes=10, attended_classes=8, percentage=80.0)
        self.assertTrue(SchemaValidator.validate(a)["valid"])

        # 3. ExamEvent
        e = ExamEvent(class_id="CSE-A", course="CS101", exam_date="2026-11-05", study_leave_days_before=3)
        self.assertTrue(SchemaValidator.validate(e)["valid"])

        # 4. PlanDiff
        p = PlanDiff(added_tasks=[t.to_dict()], summary="Added test task")
        self.assertTrue(SchemaValidator.validate(p)["valid"])

        # 5. HelpdeskAnswer
        h = HelpdeskAnswer(query="When is CS101 exam?", answer="Nov 5, 2026", sources=["datesheet.txt"])
        self.assertTrue(SchemaValidator.validate(h)["valid"])


if __name__ == "__main__":
    unittest.main()
