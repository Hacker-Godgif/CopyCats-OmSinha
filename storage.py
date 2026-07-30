"""Small SQLite persistence layer for the single-user StudyOS MVP.

The schema deliberately keeps source information beside student-facing facts so
that imported data can always be reviewed and corrected.
"""

import csv
import io
import json
import sqlite3
import uuid
from datetime import datetime, date, timedelta
from pathlib import Path


class StudyOSStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS profile (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    name TEXT NOT NULL DEFAULT '',
                    institution TEXT NOT NULL DEFAULT '',
                    programme TEXT NOT NULL DEFAULT '',
                    semester TEXT NOT NULL DEFAULT '',
                    language TEXT NOT NULL DEFAULT 'en',
                    daily_hours REAL NOT NULL DEFAULT 3,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS courses (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    attendance_threshold REAL NOT NULL DEFAULT 75,
                    policy_source TEXT NOT NULL DEFAULT '',
                    policy_updated_at TEXT NOT NULL DEFAULT '',
                    conducted_classes INTEGER NOT NULL DEFAULT 0,
                    attended_classes INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    course TEXT NOT NULL DEFAULT '',
                    due_at TEXT,
                    estimate_minutes INTEGER NOT NULL DEFAULT 60,
                    status TEXT NOT NULL DEFAULT 'pending',
                    source_ref TEXT NOT NULL DEFAULT 'Added by student',
                    source_confidence TEXT NOT NULL DEFAULT 'confirmed',
                    created_at TEXT NOT NULL,
                    completed_at TEXT
                );
                CREATE TABLE IF NOT EXISTS imports (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    status TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS timetable_classes (
                    id TEXT PRIMARY KEY,
                    course TEXT NOT NULL,
                    weekday INTEGER NOT NULL,
                    start_time TEXT NOT NULL,
                    end_time TEXT NOT NULL,
                    room TEXT NOT NULL DEFAULT '',
                    source_ref TEXT NOT NULL DEFAULT '',
                    confidence TEXT NOT NULL DEFAULT 'review',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS exams (
                    id TEXT PRIMARY KEY,
                    course TEXT NOT NULL,
                    title TEXT NOT NULL,
                    exam_date TEXT NOT NULL,
                    study_leave_days_before INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                );
            """)
            try:
                conn.execute("ALTER TABLE profile ADD COLUMN academic_start TEXT NOT NULL DEFAULT ''")
            except sqlite3.OperationalError:
                pass
            try:
                conn.execute("ALTER TABLE profile ADD COLUMN academic_end TEXT NOT NULL DEFAULT ''")
            except sqlite3.OperationalError:
                pass

    @staticmethod
    def _now():
        return datetime.now().isoformat(timespec="seconds")

    def get_profile(self):
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM profile WHERE id = 1").fetchone()
        return dict(row) if row else None

    def save_profile(self, data):
        now = self._now()
        values = (
            data.get("name", "").strip(), data.get("institution", "").strip(),
            data.get("programme", "").strip(), data.get("semester", "").strip(),
            data.get("language", "en"), max(0.5, min(float(data.get("daily_hours", 3)), 12)),
            data.get("academic_start", "").strip(), data.get("academic_end", "").strip(),
            now, now,
        )
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO profile (id,name,institution,programme,semester,language,daily_hours,academic_start,academic_end,created_at,updated_at)
                VALUES (1,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET name=excluded.name, institution=excluded.institution,
                    programme=excluded.programme, semester=excluded.semester, language=excluded.language,
                    daily_hours=excluded.daily_hours, academic_start=excluded.academic_start,
                    academic_end=excluded.academic_end, updated_at=excluded.updated_at
            """, values)
        return self.get_profile()

    def add_exam(self, course, title, exam_date, study_leave_days_before=1):
        course = (course or "").strip()
        title = (title or "").strip()
        if not course or not title or not exam_date:
            raise ValueError("Course, title, and exam date are required.")
        exam = {
            "id": str(uuid.uuid4()),
            "course": course,
            "title": title,
            "exam_date": exam_date,
            "study_leave_days_before": max(0, int(study_leave_days_before)),
            "created_at": self._now()
        }
        with self._connect() as conn:
            conn.execute("""INSERT INTO exams VALUES (:id, :course, :title, :exam_date, :study_leave_days_before, :created_at)""", exam)
        return exam

    def get_exams(self):
        with self._connect() as conn:
            return [dict(row) for row in conn.execute("SELECT * FROM exams ORDER BY exam_date").fetchall()]

    def delete_exam(self, exam_id):
        with self._connect() as conn:
            conn.execute("DELETE FROM exams WHERE id = ?", (exam_id,))

    def calculate_academic_attendance_projection(self):
        profile = self.get_profile() or {}
        start_str = profile.get("academic_start", "")
        end_str = profile.get("academic_end", "")
        today_dt = date.today()

        if not start_str or not end_str:
            return {"days_remaining": 0, "projections": []}

        try:
            start_dt = date.fromisoformat(start_str)
            end_dt = date.fromisoformat(end_str)
        except ValueError:
            return {"days_remaining": 0, "projections": []}

        days_remaining = max(0, (end_dt - today_dt).days)
        timetable = self.timetable()
        courses = self.courses()
        exams = self.get_exams()
        exams_by_course = {e["course"].lower(): e for e in exams}

        projections = []
        calc_start = max(today_dt, start_dt)
        calc_end = end_dt

        for course in courses:
            c_name = course["name"]
            c_key = c_name.lower().strip()
            
            exam = exams_by_course.get(c_key)
            c_end = date.fromisoformat(exam["exam_date"]) if exam and exam.get("exam_date") else calc_end
            if c_end < calc_start:
                c_end = calc_start

            future_classes = 0
            cursor = calc_start
            while cursor <= c_end:
                for slot in timetable:
                    s_course = slot["course"].lower().strip()
                    if s_course == c_key or s_course in c_key or c_key in s_course:
                        if slot["weekday"] == cursor.weekday():
                            future_classes += 1
                cursor += timedelta(days=1)

            current_conducted = course["conducted_classes"]
            current_attended = course["attended_classes"]
            thresh = course["attendance_threshold"]

            total_proj = current_conducted + future_classes
            req_total_attended = (thresh * total_proj) / 100.0
            min_future_needed = max(0, int(req_total_attended - current_attended + 0.999))
            max_bunks_allowed = max(0, future_classes - min_future_needed)

            proj_percentage = round((current_attended + future_classes) / total_proj * 100, 1) if total_proj else 0
            
            status = "safe" if min_future_needed <= 0 else ("manageable" if min_future_needed <= future_classes else "at_risk")
            status_label = f"Can bunk up to {max_bunks_allowed} class{'es' if max_bunks_allowed!=1 else ''}" if status == "safe" else (f"Must attend at least {min_future_needed} of next {future_classes} classes" if status == "manageable" else "Recovery impossible even with 100% attendance")

            projections.append({
                "course_name": c_name,
                "current_conducted": current_conducted,
                "current_attended": current_attended,
                "current_percentage": course["percentage"],
                "future_classes": future_classes,
                "total_projected_classes": total_proj,
                "min_future_classes_needed": min_future_needed,
                "max_bunks_allowed": max_bunks_allowed,
                "projected_percentage": proj_percentage,
                "status": status,
                "status_label": status_label,
                "exam_date": exam["exam_date"] if exam else None,
            })

        return {
            "days_remaining": days_remaining,
            "projections": projections
        }

    def upsert_course(self, name, conducted, attended, threshold=75, source="Student-confirmed attendance export"):
        name = (name or "").strip()
        if not name:
            raise ValueError("Each attendance row needs a course name.")
        conducted, attended = int(conducted), int(attended)
        if conducted < 0 or attended < 0 or attended > conducted:
            raise ValueError(f"Check attendance values for {name}.")
        now = self._now()
        with self._connect() as conn:
            existing = conn.execute("SELECT id FROM courses WHERE lower(name)=lower(?)", (name,)).fetchone()
            cid = existing["id"] if existing else str(uuid.uuid4())
            conn.execute("""
                INSERT INTO courses (id,name,attendance_threshold,policy_source,policy_updated_at,conducted_classes,attended_classes,updated_at)
                VALUES (?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET name=excluded.name, attendance_threshold=excluded.attendance_threshold,
                    policy_source=excluded.policy_source, policy_updated_at=excluded.policy_updated_at,
                    conducted_classes=excluded.conducted_classes, attended_classes=excluded.attended_classes, updated_at=excluded.updated_at
            """, (cid, name, float(threshold), source, now[:10], conducted, attended, now))
        return cid

    def courses(self):
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM courses ORDER BY name").fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["percentage"] = round((item["attended_classes"] / item["conducted_classes"] * 100), 1) if item["conducted_classes"] else 0
            item["classes_needed"] = max(0, int((item["attendance_threshold"] * item["conducted_classes"] - 100 * item["attended_classes"] + (100 - item["attendance_threshold"] - 0.001)) // (100 - item["attendance_threshold"]))) if item["attendance_threshold"] < 100 else 0
            result.append(item)
        return result

    def import_attendance_csv(self, csv_text, filename="attendance.csv", threshold=75):
        reader = csv.DictReader(io.StringIO(csv_text.strip()))
        if not reader.fieldnames:
            raise ValueError("Upload a CSV with Course, Conducted and Attended columns.")
        names = {h.lower().strip(): h for h in reader.fieldnames}
        course_key = next((names[k] for k in names if k in {"course", "subject", "paper"}), None)
        conducted_key = next((names[k] for k in names if k in {"conducted", "conducted classes", "total", "total classes"}), None)
        attended_key = next((names[k] for k in names if k in {"attended", "attended classes", "present"}), None)
        if not all((course_key, conducted_key, attended_key)):
            raise ValueError("Use headers: Course, Conducted, Attended.")
        count = 0
        for row in reader:
            if not any((row or {}).values()):
                continue
            self.upsert_course(row.get(course_key), row.get(conducted_key, 0), row.get(attended_key, 0), threshold)
            count += 1
        if not count:
            raise ValueError("No attendance rows were found.")
        self.log_import("attendance", filename, "confirmed", f"Imported {count} course records")
        return count

    def add_task(self, data):
        title = (data.get("title") or "").strip()
        if not title:
            raise ValueError("Task title is required.")
        task = {
            "id": str(uuid.uuid4()), "title": title, "course": (data.get("course") or "").strip(),
            "due_at": data.get("due_at") or None, "estimate_minutes": max(15, min(int(data.get("estimate_minutes", 60)), 480)),
            "status": "pending", "source_ref": data.get("source_ref") or "Added by student",
            "source_confidence": data.get("source_confidence") or "confirmed", "created_at": self._now(), "completed_at": None,
        }
        with self._connect() as conn:
            conn.execute("""INSERT INTO tasks VALUES (:id,:title,:course,:due_at,:estimate_minutes,:status,:source_ref,:source_confidence,:created_at,:completed_at)""", task)
        return task

    def tasks(self, status=None):
        query = "SELECT * FROM tasks"
        values = []
        if status:
            query += " WHERE status = ?"
            values.append(status)
        query += " ORDER BY CASE WHEN due_at IS NULL THEN 1 ELSE 0 END, due_at, created_at"
        with self._connect() as conn:
            return [dict(row) for row in conn.execute(query, values).fetchall()]

    def update_task(self, task_id, status):
        if status not in {"pending", "completed"}:
            raise ValueError("Unsupported task status.")
        with self._connect() as conn:
            result = conn.execute("UPDATE tasks SET status=?, completed_at=? WHERE id=?", (status, self._now() if status == "completed" else None, task_id))
        if not result.rowcount:
            raise ValueError("Task not found.")

    def log_import(self, kind, filename, status, summary):
        with self._connect() as conn:
            conn.execute("INSERT INTO imports VALUES (?,?,?,?,?,?)", (str(uuid.uuid4()), kind, filename, status, summary, self._now()))

    def recent_imports(self):
        with self._connect() as conn:
            return [dict(row) for row in conn.execute("SELECT * FROM imports ORDER BY created_at DESC LIMIT 5").fetchall()]

    def replace_timetable(self, classes, source_ref):
        """Replace the reviewed timetable with normalized recurring weekly classes."""
        normalized = []
        for item in classes:
            course = str(item.get("course", "")).strip()
            weekday = int(item.get("weekday", -1))
            start_time = str(item.get("start_time", "")).strip()
            end_time = str(item.get("end_time", "")).strip()
            if not course or weekday not in range(7) or not start_time or not end_time:
                continue
            normalized.append((str(uuid.uuid4()), course, weekday, start_time, end_time, str(item.get("room", "")).strip(), source_ref, str(item.get("confidence", "review")), self._now()))
        if not normalized:
            raise ValueError("The AI could not identify any recurring classes. Check the image is clear and includes day, course, and time.")
        with self._connect() as conn:
            conn.execute("DELETE FROM timetable_classes")
            conn.executemany("INSERT INTO timetable_classes VALUES (?,?,?,?,?,?,?,?,?)", normalized)
        self.log_import("timetable_image", source_ref, "needs_review", f"AI extracted {len(normalized)} weekly class slots")
        return self.timetable()

    def timetable(self):
        with self._connect() as conn:
            return [dict(row) for row in conn.execute("SELECT * FROM timetable_classes ORDER BY weekday, start_time, course").fetchall()]

    def bunk_impact(self, start_date, end_date):
        """Calculate the attendance outcome if every scheduled class is missed in a date range."""
        try:
            start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
        except ValueError:
            raise ValueError("Use valid start and end dates.")
        if end < start:
            raise ValueError("End date must be on or after the start date.")
        if (end - start).days > 60:
            raise ValueError("Choose a holiday period of 60 days or fewer.")
        courses_by_name = {item["name"].lower().strip(): item for item in self.courses()}
        timetable = self.timetable()
        if not timetable:
            raise ValueError("Upload a timetable image first so StudyOS knows which classes you would miss.")
        
        def find_course_record(t_name):
            t_clean = t_name.lower().strip()
            if t_clean in courses_by_name:
                return courses_by_name[t_clean]
            for c_name, record in courses_by_name.items():
                if t_clean in c_name or c_name in t_clean:
                    return record
            t_tokens = set(t_clean.split())
            for c_name, record in courses_by_name.items():
                c_tokens = set(c_name.split())
                if t_tokens & c_tokens:
                    return record
            return None

        missed = {}
        cursor = start
        while cursor <= end:
            for slot in timetable:
                if slot["weekday"] == cursor.weekday():
                    missed[slot["course"]] = missed.get(slot["course"], 0) + 1
            cursor += timedelta(days=1)
        impacts, unknown_courses = [], []
        for course_name, classes_missed in missed.items():
            record = find_course_record(course_name)
            if not record:
                unknown_courses.append(course_name)
                continue
            total = record["conducted_classes"] + classes_missed
            percentage = round(record["attended_classes"] / total * 100, 1) if total else 0
            safe = percentage >= record["attendance_threshold"]
            impacts.append({"course": record["name"], "classes_missed": classes_missed, "current_percentage": record["percentage"], "projected_percentage": percentage, "threshold": record["attendance_threshold"], "safe": safe})
        if not impacts:
            raise ValueError("No timetable courses match your attendance records. Import attendance using the same course names first.")
        return {"start_date": start.isoformat(), "end_date": end.isoformat(), "can_take_holiday": all(item["safe"] for item in impacts), "impacts": impacts, "unknown_timetable_courses": unknown_courses, "disclaimer": "This assumes every listed class in the selected dates is conducted and missed. Confirm holidays, cancellations, labs, and your institution's official attendance record."}
