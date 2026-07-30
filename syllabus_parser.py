"""
Syllabus PDF / Document Parser for StudyOS-India.
Extracts course deadlines, assignments, and exam submissions as Task objects.
"""

import re
import os
from typing import List, Dict, Any
from schema import Task, SchemaValidator
from date_parser import parse_indian_date, extract_dates_from_text

# Keywords indicating deadlines or tasks in academic syllabi
TASK_KEYWORDS = [
    'assignment', 'submission', 'due', 'deadline', 'quiz', 'midterm', 'mid-term',
    'project', 'viva', 'presentation', 'exam', 'lab report', 'homework', 'test'
]


class SyllabusParser:

    @staticmethod
    def parse_syllabus_text(text: str, source_filename: str = "Syllabus.pdf", course_name: str = "General") -> List[Task]:
        """
        Parses syllabus plain text line by line.
        Track line numbers and pages.
        """
        tasks: List[Task] = []
        lines = text.split('\n')
        current_page = 1
        page_pattern = re.compile(r'--- Page (\d+) ---', re.IGNORECASE)

        for line_idx, line in enumerate(lines, start=1):
            line_str = line.strip()
            if not line_str:
                continue

            page_match = page_pattern.search(line_str)
            if page_match:
                current_page = int(page_match.group(1))
                continue

            # Check if line contains a task keyword or deadline indicator
            lower_line = line_str.lower()
            contains_keyword = any(kw in lower_line for kw in TASK_KEYWORDS)

            # Find dates in line
            found_dates = extract_dates_from_text(line_str)

            if contains_keyword or found_dates:
                # Build Task
                source_ref = f"{source_filename} page {current_page}, line {line_idx}"
                
                # Title extraction
                title = line_str
                # Clean title if very long
                if len(title) > 120:
                    title = title[:117] + "..."

                due_at = None
                needs_review = False
                review_reason = None

                if found_dates:
                    due_at = found_dates[0][1] # first valid parsed date YYYY-MM-DD
                else:
                    needs_review = True
                    review_reason = "Task keyword detected but deadline date could not be automatically extracted."

                # Low confidence check if course name or title is ambiguous
                if "tbd" in lower_line or "to be announced" in lower_line or "tentative" in lower_line:
                    needs_review = True
                    review_reason = "Deadline flagged as tentative / to be announced in document."

                task = Task(
                    title=title,
                    course=course_name,
                    due_at=due_at,
                    source_ref=source_ref,
                    status="pending",
                    needs_manual_review=needs_review,
                    review_reason=review_reason
                )

                tasks.append(task)

        return tasks

    @classmethod
    def parse_pdf(cls, file_path: str, course_name: str = "General") -> List[Task]:
        """
        Extracts text from PDF (using pypdf or pdfplumber if available, or text fallback).
        """
        filename = os.path.basename(file_path)
        extracted_text = ""

        try:
            import pypdf
            reader = pypdf.PdfReader(file_path)
            for p_idx, page in enumerate(reader.pages, start=1):
                extracted_text += f"\n--- Page {p_idx} ---\n"
                extracted_text += page.extract_text() or ""
        except ImportError:
            try:
                import pdfplumber
                with pdfplumber.open(file_path) as pdf:
                    for p_idx, page in enumerate(pdf.pages, start=1):
                        extracted_text += f"\n--- Page {p_idx} ---\n"
                        extracted_text += page.extract_text() or ""
            except ImportError:
                # Fallback text reading if path is text file formatted as pdf
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    extracted_text = f.read()

        return cls.parse_syllabus_text(extracted_text, source_filename=filename, course_name=course_name)
