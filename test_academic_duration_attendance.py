"""
Unit tests for Academic Duration, Exam Dates, and Academic Attendance Projection.
"""

import os
import tempfile
import unittest
from datetime import date, timedelta
from storage import StudyOSStore


class TestAcademicDurationAttendance(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.db_path = self.tmp.name
        self.tmp.close()
        self.store = StudyOSStore(self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except OSError:
                pass

    def test_save_profile_academic_duration(self):
        profile_data = {
            "name": "Jane",
            "institution": "IIT Delhi",
            "programme": "B.Tech",
            "semester": "4",
            "daily_hours": 4,
            "academic_start": "2026-08-01",
            "academic_end": "2026-12-15",
        }
        saved = self.store.save_profile(profile_data)
        self.assertEqual(saved["academic_start"], "2026-08-01")
        self.assertEqual(saved["academic_end"], "2026-12-15")

    def test_exam_management(self):
        exam = self.store.add_exam(
            course="Physics",
            title="Mid-Term Exam",
            exam_date="2026-10-15",
            study_leave_days_before=2
        )
        self.assertEqual(exam["course"], "Physics")
        self.assertEqual(exam["exam_date"], "2026-10-15")

        exams = self.store.get_exams()
        self.assertEqual(len(exams), 1)
        self.assertEqual(exams[0]["title"], "Mid-Term Exam")

        self.store.delete_exam(exam["id"])
        self.assertEqual(len(self.store.get_exams()), 0)

    def test_academic_attendance_projection_math(self):
        today = date.today().isoformat()
        end_date = (date.today() + timedelta(days=60)).isoformat()

        self.store.save_profile({
            "name": "Test",
            "institution": "DU",
            "academic_start": today,
            "academic_end": end_date,
        })

        # Add course: 10 conducted, 7 attended -> 70%
        self.store.upsert_course("Data Structures", conducted=10, attended=7, threshold=75)

        # Add recurring Monday timetable slot
        weekday_mon = 0
        self.store.replace_timetable([
            {"course": "Data Structures", "weekday": weekday_mon, "start_time": "10:00", "end_time": "11:00"}
        ], "test source")

        proj_result = self.store.calculate_academic_attendance_projection()
        self.assertIn("projections", proj_result)
        self.assertEqual(len(proj_result["projections"]), 1)

        p = proj_result["projections"][0]
        self.assertEqual(p["course_name"], "Data Structures")
        self.assertGreater(p["future_classes"], 0)
        self.assertGreaterEqual(p["total_projected_classes"], 10)
        self.assertIn("max_bunks_allowed", p)
        self.assertIn("min_future_classes_needed", p)


if __name__ == "__main__":
    unittest.main()
