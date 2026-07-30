"""
Exam Datesheet Parser for StudyOS-India.
Extracts ExamEvent objects and calculates exact study_leave_days_before using date arithmetic.
"""

import re
import os
from datetime import datetime, date
from typing import List, Optional, Dict, Any
from schema import ExamEvent, SchemaValidator
from date_parser import parse_indian_date, extract_dates_from_text


class DatesheetParser:

    @staticmethod
    def parse_datesheet_text(
        text: str,
        class_id: str = "CSE-2026-A",
        term_start_date: str = "2026-11-01"
    ) -> List[ExamEvent]:
        """
        Parses datesheet text lines, extracts exam date & course, sorts chronologically,
        and calculates exact study_leave_days_before.
        """
        raw_events = []
        lines = text.strip().split('\n')

        # Term start parsed as date object
        term_start_dt = datetime.strptime(term_start_date, "%Y-%m-%d").date()

        for line_idx, line in enumerate(lines, start=1):
            line_str = line.strip()
            if not line_str or line_str.startswith("#"):
                continue

            # Look for dates
            found_dates = extract_dates_from_text(line_str)
            if not found_dates:
                continue

            exam_date_str = found_dates[0][1] # YYYY-MM-DD
            exam_date_obj = datetime.strptime(exam_date_str, "%Y-%m-%d").date()

            # Extract course name from remaining line text
            course_text = line_str
            for matched_sub, _ in found_dates:
                course_text = course_text.replace(matched_sub, "")
            
            # Clean up punctuation and common labels
            course_text = re.sub(r'\b(Exam|Date|Subject|Paper|Code|Class|Time|Morning|Evening|Slot)\b', '', course_text, flags=re.IGNORECASE)
            course_text = re.sub(r'[:\|\-\,]', ' ', course_text).strip()
            if not course_text:
                course_text = f"Subject-{line_idx}"

            raw_events.append({
                "course": course_text,
                "exam_date_obj": exam_date_obj,
                "exam_date_str": exam_date_str,
                "line_idx": line_idx
            })

        # Sort raw events chronologically
        raw_events.sort(key=lambda x: x["exam_date_obj"])

        exam_events: List[ExamEvent] = []

        for idx, event in enumerate(raw_events):
            current_dt = event["exam_date_obj"]
            needs_review = False
            review_reason = None

            # Calculate study_leave_days_before using exact calendar date arithmetic
            if idx == 0:
                # First exam: gap from term_start_date
                prev_dt = term_start_dt
            else:
                prev_dt = raw_events[idx - 1]["exam_date_obj"]

            if current_dt < prev_dt:
                leave_days = 0
                needs_review = True
                review_reason = f"Exam date ({current_dt}) is before previous milestone ({prev_dt})"
            else:
                day_delta = (current_dt - prev_dt).days
                leave_days = max(0, day_delta - 1)

            if current_dt == prev_dt and idx > 0:
                needs_review = True
                review_reason = f"Multiple exams scheduled on the exact same date ({current_dt})"

            event_obj = ExamEvent(
                class_id=class_id,
                course=event["course"],
                exam_date=event["exam_date_str"],
                study_leave_days_before=leave_days,
                needs_manual_review=needs_review,
                review_reason=review_reason
            )

            exam_events.append(event_obj)

        return exam_events

    @classmethod
    def parse_file(cls, file_path: str, class_id: str = "CSE-2026-A", term_start_date: str = "2026-11-01") -> List[ExamEvent]:
        """Reads file and parses datesheet."""
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        return cls.parse_datesheet_text(content, class_id=class_id, term_start_date=term_start_date)
