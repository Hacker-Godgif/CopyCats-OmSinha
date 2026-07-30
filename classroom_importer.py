import os
import json
import urllib.request
import urllib.parse
from typing import List, Dict, Any
from schema import Task, SchemaValidator
from date_parser import parse_indian_date

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_CLASSROOM_API = "https://classroom.googleapis.com/v1"

SCOPES = [
    "https://www.googleapis.com/auth/classroom.courses.readonly",
    "https://www.googleapis.com/auth/classroom.coursework.me.readonly",
    "openid",
    "email",
    "profile"
]


class GoogleAuthManager:
    @staticmethod
    def get_login_url(redirect_uri: str) -> str:
        client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(SCOPES),
            "access_type": "offline",
            "prompt": "consent"
        }
        return f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"

    @staticmethod
    def exchange_code_for_tokens(code: str, redirect_uri: str) -> Dict[str, Any]:
        client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
        client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")
        
        data = urllib.parse.urlencode({
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code"
        }).encode("utf-8")

        req = urllib.request.Request(GOOGLE_TOKEN_URL, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))

    @staticmethod
    def fetch_live_assignments(access_token: str) -> List[Dict[str, Any]]:
        """Fetch courses & coursework directly from Google Classroom REST API"""
        headers = {"Authorization": f"Bearer {access_token}"}
        
        courses = []
        # Try fetching student courses first, then active courses
        for url in [f"{GOOGLE_CLASSROOM_API}/courses?studentId=me&courseStates=ACTIVE", f"{GOOGLE_CLASSROOM_API}/courses?courseStates=ACTIVE"]:
            req = urllib.request.Request(url, headers=headers)
            try:
                with urllib.request.urlopen(req) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    fetched = data.get("courses", [])
                    if fetched:
                        courses = fetched
                        break
            except Exception as e:
                print(f"[GoogleClassroom] Course list warning for {url}: {e}")
                continue

        assignments = []

        for course in courses:
            c_id = course.get("id")
            c_name = course.get("name", "Classroom Course")
            
            cw_url = f"{GOOGLE_CLASSROOM_API}/courses/{c_id}/courseWork"
            cw_req = urllib.request.Request(cw_url, headers=headers)
            try:
                with urllib.request.urlopen(cw_req) as cw_resp:
                    cw_data = json.loads(cw_resp.read().decode("utf-8"))
                    for item in cw_data.get("courseWork", []):
                        cw_id = item.get("id")
                        state = str(item.get("state", "PUBLISHED")).upper()
                        
                        # Check student submission status
                        is_submitted = False
                        sub_url = f"{GOOGLE_CLASSROOM_API}/courses/{c_id}/courseWork/{cw_id}/studentSubmissions?studentId=me"
                        try:
                            sub_req = urllib.request.Request(sub_url, headers=headers)
                            with urllib.request.urlopen(sub_req) as sub_resp:
                                sub_data = json.loads(sub_resp.read().decode("utf-8"))
                                for sub in sub_data.get("studentSubmissions", []):
                                    sub_state = str(sub.get("state", "")).upper()
                                    if sub_state in {"TURNED_IN", "RETURNED", "SUBMITTED"}:
                                        is_submitted = True
                                        break
                        except Exception:
                            pass

                        if is_submitted or state in {"TURNED_IN", "RETURNED", "COMPLETED", "SUBMITTED"}:
                            continue

                        due_date = item.get("dueDate", {})
                        raw_due = f"{due_date.get('year')}-{due_date.get('month'):02d}-{due_date.get('day'):02d}" if due_date.get("year") else ""
                        
                        assignments.append({
                            "id": cw_id,
                            "title": item.get("title", "Untitled Assignment"),
                            "course": c_name,
                            "dueDate": raw_due,
                            "status": state
                        })
            except Exception as e:
                print(f"[GoogleClassroom] CourseWork fetch warning for course {c_id}: {e}")
                continue

        return assignments


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
                source_ref="Mock Classroom Import" if custom_payload is None else "Google Classroom API",
                status="pending",
                needs_manual_review=needs_review,
                review_reason=review_reason
            )

            val_res = SchemaValidator.validate_task(task)
            if not val_res["valid"]:
                task.needs_manual_review = True
                task.review_reason = f"Schema validation issues: {', '.join(val_res['errors'])}"

            tasks.append(task)

        return tasks
