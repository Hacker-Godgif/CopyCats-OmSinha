"""
Mock Google Classroom Importer for StudyOS-India.
Converts mock Classroom assignment payload into Task objects using the identical Task validation pipeline.
"""

from typing import List, Dict, Any
from schema import Task, SchemaValidator
from date_parser import parse_indian_date

# Sample realistic Google Classroom API assignment payloads
MOCK_CLASSROOM_PAYLOAD = [
    {
        "id": "gc-101",
        "title": "Programming Assignment 1: Data Structures",
        "course": "CS101 - Computer Science Fundamentals",
        "dueDate": "18/08/2026",
        "dueTime": "23:59:00",
        "status": "PUBLISHED"
    },
    {
        "id": "gc-102",
        "title": "Calculus Problem Set 3 - Integration Techniques",
        "course": "MATH201 - Advanced Mathematics",
        "dueDate": "22-Aug-2026",
        "dueTime": "17:00:00",
        "status": "PUBLISHED"
    },
    {
        "id": "gc-103",
        "title": "Database Schema Design & ER Diagrams Lab",
        "course": "CS204 - Database Management Systems",
        "dueDate": "2026-09-01",
        "dueTime": "23:59:00",
        "status": "PUBLISHED"
    },
    {
        "id": "gc-104",
        "title": "Operating Systems Quiz 2 (Tentative)",
        "course": "CS302 - Operating Systems",
        "dueDate": "TBD",
        "dueTime": "",
        "status": "DRAFT"
    }
]


class ClassroomImporter:

    @staticmethod
    def import_mock_assignments(custom_payload: List[Dict[str, Any]] = None) -> List[Task]:
        """
        Converts Classroom assignments to Task objects through identical validation logic as syllabus parser.
        """
        items = custom_payload if custom_payload is not None else MOCK_CLASSROOM_PAYLOAD
        tasks: List[Task] = []

        for item in items:
            raw_due = item.get("dueDate", "")
            parsed_due = parse_indian_date(raw_due)

            needs_review = False
            review_reason = None

            if not parsed_due:
                if raw_due and raw_due.upper() != "TBD":
                    parsed_due = raw_due  # pass along if formatted, validator will catch
                else:
                    parsed_due = None
                    needs_review = True
                    review_reason = "Classroom assignment due date is missing or TBD"

            if item.get("status") == "DRAFT":
                needs_review = True
                review_reason = "Classroom assignment is in DRAFT state"

            task = Task(
                title=item.get("title", "Untitled Classroom Assignment"),
                course=item.get("course", "General"),
                due_at=parsed_due,
                source_ref="Mock Classroom Import",
                status="pending",
                needs_manual_review=needs_review,
                review_reason=review_reason
            )

            # Validate using shared SchemaValidator
            val_res = SchemaValidator.validate_task(task)
            if not val_res["valid"]:
                task.needs_manual_review = True
                task.review_reason = f"Schema validation issues: {', '.join(val_res['errors'])}"

            tasks.append(task)

        return tasks
