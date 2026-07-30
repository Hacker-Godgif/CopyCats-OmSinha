"""
Timetable Parser for StudyOS-India.
Handles clean timetable exports as well as messy/scanned documents.
Low-confidence parses are explicitly flagged with needs_manual_review=True.
"""

import re
import os
from typing import List, Dict, Any
from schema import Task
from date_parser import extract_dates_from_text, parse_indian_date


class TimetableParser:

    @staticmethod
    def parse_timetable_text(text: str, source_name: str = "Timetable.pdf", is_scanned: bool = False) -> List[Task]:
        """
        Parses timetable content into Task / schedule items.
        If is_scanned or text confidence is low, sets needs_manual_review = True.
        """
        tasks: List[Task] = []
        lines = text.strip().split('\n')

        # Heuristic check for low-confidence / corrupted OCR text (unusual non-ASCII or chaotic characters)
        gibberish_chars = len(re.findall(r'[^\w\s\:\-\,\.\/\(\)]', text))
        low_confidence = is_scanned or (len(text) > 0 and (gibberish_chars / len(text)) > 0.15)

        for line_idx, line in enumerate(lines, start=1):
            line_str = line.strip()
            if not line_str or len(line_str) < 3:
                continue

            # Look for course / subject and time slots
            has_time = bool(re.search(r'\b(\d{1,2}[:.]\d{2}|\d{1,2}\s*(?:AM|PM|am|pm))\b', line_str))
            has_day = bool(re.search(r'\b(Mon|Tue|Wed|Thu|Fri|Sat|Sun|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b', line_str, re.IGNORECASE))
            found_dates = extract_dates_from_text(line_str)

            if has_time or has_day or found_dates or "class" in line_str.lower():
                needs_review = low_confidence
                review_reason = "Scanned/low-confidence OCR parse requires manual confirmation" if low_confidence else None

                due_at = found_dates[0][1] if found_dates else None

                task = Task(
                    title=f"Class Schedule: {line_str}",
                    course="Timetable Entry",
                    due_at=due_at,
                    source_ref=f"{source_name} line {line_idx}",
                    status="pending",
                    needs_manual_review=needs_review,
                    review_reason=review_reason
                )

                tasks.append(task)

        # If low confidence and no structured lines found, return a flagged placeholder task
        if low_confidence and not tasks:
            tasks.append(Task(
                title="Unstructured Scanned Timetable",
                course="Unknown",
                due_at=None,
                source_ref=f"{source_name} (Scanned Image/PDF)",
                status="pending",
                needs_manual_review=True,
                review_reason="Document contains scanned or rotated image text that requires manual review."
            ))

        return tasks
