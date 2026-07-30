"""
Attendance Parser for StudyOS-India.
Extracts subject-wise AttendanceRecord objects from CSV, PDF export, or plain text.
Detects malformed rows (attended > conducted, division by 0) and flags needs_manual_review=True.
"""

import csv
import io
import os
import re
from typing import List, Dict, Any
from schema import AttendanceRecord, SchemaValidator


class AttendanceParser:

    @staticmethod
    def parse_csv_content(csv_text: str, student_id: str = "STD-2026-001") -> List[AttendanceRecord]:
        """
        Parses CSV content representing attendance sheet.
        Expected headers (or flexible columns): Course/Subject, Conducted, Attended (or Held, Present).
        """
        records: List[AttendanceRecord] = []
        reader = csv.reader(io.StringIO(csv_text.strip()))
        
        rows = list(reader)
        if not rows:
            return records

        # Identify header indices
        header = [c.strip().lower() for c in rows[0]]
        course_idx = -1
        conducted_idx = -1
        attended_idx = -1

        for idx, col in enumerate(header):
            if any(k in col for k in ['course', 'subject', 'code', 'name']):
                course_idx = idx
            elif any(k in col for k in ['conducted', 'held', 'total', 'total_classes']):
                conducted_idx = idx
            elif any(k in col for k in ['attended', 'present', 'classes_attended']):
                attended_idx = idx

        # Default fallback column mapping if headers are missing or unusual
        if course_idx == -1: course_idx = 0
        if conducted_idx == -1: conducted_idx = 1
        if attended_idx == -1: attended_idx = 2

        # Process data rows
        start_row = 1 if (any(c in rows[0][0].lower() for c in ['course', 'subject', 's.no', 'sr.no'])) else 0

        for row_idx in range(start_row, len(rows)):
            row = [r.strip() for r in rows[row_idx]]
            if not row or len(row) < 2:
                continue

            course_name = row[course_idx] if course_idx < len(row) else f"Subject-{row_idx}"
            raw_conducted = row[conducted_idx] if conducted_idx < len(row) else ""
            raw_attended = row[attended_idx] if attended_idx < len(row) else ""

            needs_review = False
            review_reasons = []

            conducted = 0
            attended = 0

            # Safe integer parsing
            try:
                conducted = int(raw_conducted)
            except ValueError:
                needs_review = True
                review_reasons.append(f"Invalid conducted_classes value '{raw_conducted}'")

            try:
                attended = int(raw_attended)
            except ValueError:
                needs_review = True
                review_reasons.append(f"Invalid attended_classes value '{raw_attended}'")

            # Mathematical validation checks
            if not needs_review:
                if conducted < 0 or attended < 0:
                    needs_review = True
                    review_reasons.append("Negative class counts detected")
                
                if conducted == 0:
                    needs_review = True
                    review_reasons.append("Conducted classes is 0 (division by zero)")

                if attended > conducted:
                    needs_review = True
                    review_reasons.append(f"Attended classes ({attended}) exceeds conducted classes ({conducted})")

            # Calculate percentage
            percentage = 0.0
            if conducted > 0 and not (attended > conducted):
                percentage = round((attended / conducted) * 100.0, 2)
            else:
                percentage = 0.0

            rec = AttendanceRecord(
                course=course_name,
                conducted_classes=conducted,
                attended_classes=attended,
                percentage=percentage,
                student_id=student_id,
                needs_manual_review=needs_review,
                review_reason="; ".join(review_reasons) if review_reasons else None
            )

            records.append(rec)

        return records

    @classmethod
    def parse_file(cls, file_path: str, student_id: str = "STD-2026-001") -> List[AttendanceRecord]:
        """Reads file and delegates to CSV parser."""
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        return cls.parse_csv_content(content, student_id=student_id)
