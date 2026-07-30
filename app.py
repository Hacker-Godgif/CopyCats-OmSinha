"""StudyOS India — student-first academic planner MVP."""

import csv
import io
import os
import base64
from datetime import date, datetime, timedelta
from pathlib import Path

from flask import Flask, jsonify, render_template, request, Response

from attendance_risk_agent import AttendanceRiskAgent
from datesheet_parser import DatesheetParser
from helpdesk_agent import GroundedHelpdeskAgent
from planner_module import DeterministicConstraintSolver, PlanVerifier, ReflectionMemoryStore, FreeSlotPlanner
from schema import AttendanceRecord, Task
from storage import StudyOSStore
from ai_timetable_agent import TimetableVisionAgent

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
app = Flask(__name__)
app.config.update(MAX_CONTENT_LENGTH=2 * 1024 * 1024, JSON_SORT_KEYS=False)
store = StudyOSStore(str(DATA_DIR / "studyos.db"))
reflection_store = ReflectionMemoryStore(str(DATA_DIR / "reflection.db"))
helpdesk_agent = GroundedHelpdeskAgent(str(BASE_DIR / "campus_policies.json"))


def api_error(message, code=400):
    return jsonify({"success": False, "error": message}), code


@app.errorhandler(500)
@app.errorhandler(Exception)
def handle_exception(e):
    return jsonify({"success": False, "error": str(e) or "An internal server error occurred."}), 500


def today_iso():
    return date.today().isoformat()


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/bootstrap")
def bootstrap():
    profile = store.get_profile()
    tasks = store.tasks()
    courses = store.courses()
    urgent = [task for task in tasks if task["status"] == "pending" and task["due_at"] and task["due_at"][:10] <= (date.today() + timedelta(days=3)).isoformat()]
    today_plan = FreeSlotPlanner.suggest_free_slots(store, today_iso())
    exams = store.get_exams()
    acad_proj = store.calculate_academic_attendance_projection()
    return jsonify({
        "success": True, "profile": profile, "courses": courses, "tasks": tasks,
        "recent_imports": store.recent_imports(), "timetable": store.timetable(), "needs_onboarding": not bool(profile and profile["institution"]),
        "urgent_tasks": urgent, "today": today_iso(), "today_plan": today_plan,
        "exams": exams, "academic_projection": acad_proj,
    })


@app.get("/api/exams")
def get_exams():
    return jsonify({"success": True, "exams": store.get_exams()})


@app.post("/api/exams")
def add_exam():
    data = request.get_json(silent=True) or {}
    try:
        exam = store.add_exam(data.get("course"), data.get("title"), data.get("exam_date"), data.get("study_leave_days_before", 1))
        return jsonify({"success": True, "exam": exam}), 201
    except ValueError as exc:
        return api_error(str(exc))


@app.delete("/api/exams/<exam_id>")
def delete_exam(exam_id):
    store.delete_exam(exam_id)
    return jsonify({"success": True})


@app.route("/api/suggest-free-slots", methods=["GET", "POST"])
def suggest_free_slots():
    data = request.get_json(silent=True) or {}
    target_date = data.get("date") or request.args.get("date") or today_iso()
    plan = FreeSlotPlanner.suggest_free_slots(store, target_date)
    return jsonify({"success": True, "date": target_date, "today_plan": plan})


@app.post("/api/profile")
def save_profile():
    data = request.get_json(silent=True) or {}
    if not data.get("institution", "").strip():
        return api_error("Add your college or university so StudyOS can label its advice correctly.")
    try:
        return jsonify({"success": True, "profile": store.save_profile(data)})
    except (TypeError, ValueError):
        return api_error("Daily study time must be between 0.5 and 12 hours.")


@app.post("/api/import/attendance")
def import_attendance():
    data = request.get_json(silent=True) or {}
    try:
        count = store.import_attendance_csv(data.get("csv_text", ""), data.get("filename", "attendance.csv"), float(data.get("threshold", 75)))
        return jsonify({"success": True, "count": count, "courses": store.courses(), "message": f"Imported and confirmed {count} course records."})
    except (TypeError, ValueError) as exc:
        return api_error(str(exc))


@app.post("/api/import/google-classroom")
def import_google_classroom():
    from classroom_importer import ClassroomImporter
    data = request.get_json(silent=True) or {}
    custom_payload = data.get("assignments")
    imported_tasks = ClassroomImporter.import_mock_assignments(custom_payload)
    
    existing = store.tasks()
    existing_keys = {(t["title"].lower().strip(), (t.get("course") or "").lower().strip()) for t in existing}

    added_tasks = []
    urgent_cutoff = (date.today() + timedelta(days=3)).isoformat()
    urgent_count = 0

    for t in imported_tasks:
        key = (t.title.lower().strip(), (t.course or "").lower().strip())
        if key in existing_keys:
            continue  # Exclude assignments that are already imported or completed

        due_str = t.due_at or ""
        is_urgent = bool(due_str and due_str[:10] <= urgent_cutoff)
        if is_urgent:
            urgent_count += 1
            
        saved_task = store.add_task({
            "title": t.title,
            "course": t.course,
            "due_at": t.due_at,
            "estimate_minutes": 60,
            "source_ref": "Google Classroom API",
            "source_confidence": "review" if t.needs_manual_review else "confirmed"
        })
        saved_task["is_urgent"] = is_urgent
        added_tasks.append(saved_task)

    store.log_import("google_classroom", "Google Classroom API", "confirmed", f"Imported {len(added_tasks)} new assignments ({urgent_count} urgent)")
    return jsonify({
        "success": True,
        "count": len(added_tasks),
        "urgent_count": urgent_count,
        "tasks": added_tasks,
        "message": f"Synced {len(added_tasks)} remaining assignments from Google Classroom ({urgent_count} urgent)." if added_tasks else "All Google Classroom assignments are up to date! No pending assignments left to sync."
    })


@app.get("/api/auth/google/status")
def google_status():
    client_id = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
    user_email = session.get("google_user_email")
    return jsonify({
        "configured": bool(client_id),
        "client_id": client_id if client_id else None,
        "authenticated": bool(user_email),
        "user_email": user_email
    })


@app.post("/api/auth/google/logout")
def google_logout():
    session.pop("google_user_email", None)
    return jsonify({"success": True, "message": "Signed out of Google Classroom."})


@app.get("/api/auth/google/login")
def google_login():
    from classroom_importer import GoogleAuthManager
    redirect_uri = url_for("google_callback", _external=True)
    client_id = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
    if not client_id:
        return jsonify({
            "success": False,
            "configured": False,
            "login_url": None,
            "message": "GOOGLE_CLIENT_ID is not configured in .env file yet."
        })
    login_url = GoogleAuthManager.get_login_url(redirect_uri)
    return jsonify({"success": True, "configured": True, "login_url": login_url})


@app.get("/api/auth/google/callback")
def google_callback():
    from classroom_importer import GoogleAuthManager, ClassroomImporter
    code = request.args.get("code")
    if not code:
        return redirect("/?error=missing_code")
    redirect_uri = url_for("google_callback", _external=True)
    try:
        tokens = GoogleAuthManager.exchange_code_for_tokens(code, redirect_uri)
        access_token = tokens.get("access_token")
        if not access_token:
            return redirect("/?error=no_token")
        raw_assignments = GoogleAuthManager.fetch_live_assignments(access_token)
        imported_tasks = ClassroomImporter.import_mock_assignments(raw_assignments if raw_assignments else None)
        
        existing = store.tasks()
        existing_keys = {(t["title"].lower().strip(), (t.get("course") or "").lower().strip()) for t in existing}

        urgent_cutoff = (date.today() + timedelta(days=3)).isoformat()
        urgent_count = 0
        for t in imported_tasks:
            key = (t.title.lower().strip(), (t.course or "").lower().strip())
            if key in existing_keys:
                continue

            due_str = t.due_at or ""
            if due_str and due_str[:10] <= urgent_cutoff:
                urgent_count += 1
            store.add_task({
                "title": t.title,
                "course": t.course,
                "due_at": t.due_at,
                "estimate_minutes": 60,
                "source_ref": "Google Classroom API (Live OAuth)",
                "source_confidence": "review" if t.needs_manual_review else "confirmed"
            })
        return redirect("/?notice=google_sync_success")
    except Exception as exc:
        return redirect("/?error=auth_failed")


@app.post("/api/analyze/timetable-image")
def analyze_timetable_image():
    data = request.get_json(silent=True) or {}
    image_base64 = data.get("image_base64", "")
    mime_type = data.get("mime_type", "image/jpeg")
    if mime_type not in {"image/jpeg", "image/png", "image/webp"}:
        return api_error("Upload a PNG, JPG, or WEBP timetable image.")
    try:
        image_bytes = base64.b64decode(image_base64, validate=True)
    except (ValueError, TypeError):
        return api_error("The selected image could not be read.")
    if not image_bytes or len(image_bytes) > 8 * 1024 * 1024:
        return api_error("Use an image smaller than 8 MB.")
    profile = store.get_profile() or {}
    try:
        result = TimetableVisionAgent().analyse(image_bytes, mime_type, {"institution": profile.get("institution", "not supplied"), "programme": profile.get("programme", "not supplied"), "semester": profile.get("semester", "not supplied")})
        if result.get("classes"):
            timetable = store.replace_timetable(result["classes"], data.get("filename", "timetable image"))
        else:
            timetable = store.timetable()
            result.setdefault("uncertainties", []).append("No recurring classes were detected automatically. Please review the image manually and add the timetable manually if needed.")
            result["summary"] = result.get("summary", "Timetable upload needs manual review.")
        return jsonify({"success": True, "analysis": result, "timetable": timetable, "notice": "Review every extracted class before relying on holiday or attendance advice."})
    except ValueError as exc:
        return api_error(str(exc))


@app.post("/api/analyze/attendance-image")
def analyze_attendance_image():
    data = request.get_json(silent=True) or {}
    image_base64, mime_type = data.get("image_base64", ""), data.get("mime_type", "image/jpeg")
    if mime_type not in {"image/jpeg", "image/png", "image/webp"}:
        return api_error("Upload a PNG, JPG, or WEBP attendance image.")
    try:
        image_bytes = base64.b64decode(image_base64, validate=True)
        if not image_bytes or len(image_bytes) > 8 * 1024 * 1024:
            raise ValueError("Use an image smaller than 8 MB.")
        profile = store.get_profile() or {}
        result = TimetableVisionAgent().analyse_attendance(image_bytes, mime_type, {"institution": profile.get("institution", "not supplied"), "programme": profile.get("programme", "not supplied")})
        threshold = float(data.get("threshold", 75))
        for row in result["records"]:
            store.upsert_course(row["course"], row["conducted_classes"], row["attended_classes"], threshold, "AI-extracted attendance image — review recommended")
        store.log_import("attendance_image", data.get("filename", "attendance image"), "needs_review", f"AI extracted {len(result['records'])} attendance records")
        return jsonify({"success": True, "analysis": result, "courses": store.courses(), "notice": "Review each imported attendance value against your portal before making absence decisions."})
    except (ValueError, TypeError) as exc:
        return api_error(str(exc))


@app.post("/api/bunk-check")
def bunk_check():
    data = request.get_json(silent=True) or {}
    try:
        return jsonify({"success": True, "result": store.bunk_impact(data.get("start_date", ""), data.get("end_date", ""))})
    except ValueError as exc:
        return api_error(str(exc))


@app.post("/api/courses/<course_id>/attendance")
def update_attendance(course_id):
    data = request.get_json(silent=True) or {}
    course = next((course for course in store.courses() if course["id"] == course_id), None)
    if not course:
        return api_error("Course not found.", 404)
    try:
        store.upsert_course(course["name"], data.get("conducted_classes"), data.get("attended_classes"), data.get("attendance_threshold", course["attendance_threshold"]), data.get("policy_source", course["policy_source"] or "Student-confirmed attendance export"))
        return jsonify({"success": True, "courses": store.courses()})
    except (TypeError, ValueError) as exc:
        return api_error(str(exc))


@app.post("/api/tasks")
def add_task():
    try:
        task = store.add_task(request.get_json(silent=True) or {})
        return jsonify({"success": True, "task": task}), 201
    except (TypeError, ValueError) as exc:
        return api_error(str(exc))


@app.patch("/api/tasks/<task_id>")
def update_task(task_id):
    try:
        store.update_task(task_id, (request.get_json(silent=True) or {}).get("status", ""))
        return jsonify({"success": True, "tasks": store.tasks()})
    except ValueError as exc:
        return api_error(str(exc), 404 if "not found" in str(exc).lower() else 400)


@app.post("/api/generate-plan")
def generate_plan():
    profile = store.get_profile() or {"daily_hours": 3}
    pending = store.tasks("pending")
    if not pending:
        return api_error("Add a task or import a document before generating a plan.")
    start = (request.get_json(silent=True) or {}).get("start_date", today_iso())
    try:
        start_dt = datetime.strptime(start, "%Y-%m-%d").date()
    except ValueError:
        return api_error("Start date must use YYYY-MM-DD.")
    task_objects = [Task(id=t["id"], title=t["title"], course=t["course"] or "General", due_at=t["due_at"], source_ref=t["source_ref"], status=t["status"]) for t in pending]
    daily_hours = {(start_dt + timedelta(days=i)).isoformat(): float(profile["daily_hours"]) for i in range(7)}
    risk_courses = [c["name"] for c in store.courses() if c["percentage"] < c["attendance_threshold"]]
    slots, diff = DeterministicConstraintSolver.create_weekly_plan(task_objects, daily_hours, start, risk_courses)
    return jsonify({"success": True, "scheduled_slots": slots, "plan_diff": diff.to_dict(), "verifier": PlanVerifier.verify_plan(slots, daily_hours), "generated_for": start})


@app.post("/api/attendance/risk")
def attendance_risk():
    data = request.get_json(silent=True) or {}
    try:
        record = AttendanceRecord(course=data.get("course", "Course"), conducted_classes=int(data.get("conducted_classes")), attended_classes=int(data.get("attended_classes")))
        result = AttendanceRiskAgent.evaluate_attendance(record, remaining_classes=int(data.get("remaining_classes", 0)), condonation_deadline=data.get("condonation_deadline"))
        return jsonify({"success": True, "analysis": result})
    except (TypeError, ValueError):
        return api_error("Enter valid attended, conducted, and remaining class counts.")


@app.get("/api/policy-sources")
def policy_sources():
    return jsonify({"success": True, "sources": [{"id": p["doc_id"], "title": p["title"], "section": p["section"], "updated_at": "2026-07-30", "note": "Demo policy content — confirm against your institution's official notice."} for p in helpdesk_agent.policies]})


@app.post("/api/helpdesk/query")
def helpdesk_query():
    query = (request.get_json(silent=True) or {}).get("query", "")
    result = helpdesk_agent.answer_query(query)
    result["policy_notice"] = "Verify time-sensitive rules with your college's official portal or examination cell."
    return jsonify(result)


@app.post("/api/reflect")
def reflect():
    summary, diff = reflection_store.reflect()
    return jsonify({"success": True, "summary": summary, "plan_diff": diff.to_dict()})


@app.get("/api/calendar.ics")
def calendar_export():
    tasks = [task for task in store.tasks("pending") if task["due_at"]]
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//StudyOS India//EN"]
    for task in tasks:
        due = task["due_at"][:10].replace("-", "")
        lines.extend(["BEGIN:VEVENT", f"UID:{task['id']}@studyos", f"DTSTART;VALUE=DATE:{due}", f"SUMMARY:{task['title'].replace(',', ' ')}", f"DESCRIPTION:Course: {task['course']}", "END:VEVENT"])
    lines.append("END:VCALENDAR")
    return Response("\r\n".join(lines), mimetype="text/calendar", headers={"Content-Disposition": "attachment; filename=studyos-deadlines.ics"})


# Kept for compatibility with the earlier prototype's document parser endpoints.
@app.post("/api/parse-datesheet")
def parse_datesheet():
    data = request.get_json(silent=True) or {}
    text = data.get("text", "")
    if not text:
        return api_error("Paste datesheet text or use the import workflow.")
    exams = DatesheetParser.parse_datesheet_text(text, class_id=data.get("class_id", ""), term_start_date=data.get("term_start_date", today_iso()))
    return jsonify({"success": True, "exam_events": [exam.to_dict() for exam in exams]})


@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "StudyOS India"})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5000")), debug=True)
