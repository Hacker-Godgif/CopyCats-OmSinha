"""
StudyOS-India Shared Schema Definition and Validator
Implements Task, AttendanceRecord, ExamEvent, PlanDiff, and HelpdeskAnswer shapes.
"""

from dataclasses import dataclass, asdict, field
from typing import List, Optional, Dict, Any
from datetime import datetime, date
import uuid


@dataclass
class Task:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    course: str = ""
    due_at: Optional[str] = None  # ISO 8601 string or YYYY-MM-DD
    source_ref: str = ""           # e.g., "Syllabus.pdf page 2, line 14" or "Mock Classroom Import"
    status: str = "pending"        # 'pending', 'completed', 'in_progress'
    needs_manual_review: bool = False
    review_reason: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AttendanceRecord:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    course: str = ""
    conducted_classes: int = 0
    attended_classes: int = 0
    percentage: float = 0.0
    student_id: Optional[str] = None
    needs_manual_review: bool = False
    review_reason: Optional[str] = None
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ExamEvent:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    class_id: str = ""
    course: str = ""
    exam_date: str = ""            # YYYY-MM-DD
    study_leave_days_before: int = 0
    needs_manual_review: bool = False
    review_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PlanDiff:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    added_tasks: List[Dict[str, Any]] = field(default_factory=list)
    modified_tasks: List[Dict[str, Any]] = field(default_factory=list)
    removed_task_ids: List[str] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class HelpdeskAnswer:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    query: str = ""
    answer: str = ""
    sources: List[str] = field(default_factory=list)
    confidence: float = 1.0
    needs_manual_review: bool = False
    review_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SchemaValidator:
    """Validator enforcing StudyOS-India schema requirements."""

    @staticmethod
    def validate_task(obj: Any) -> Dict[str, Any]:
        data = obj.to_dict() if hasattr(obj, 'to_dict') else obj
        errors = []
        if not data.get("title"):
            errors.append("Task title is required")
        if not data.get("course"):
            errors.append("Task course is required")
        if not data.get("source_ref"):
            errors.append("Task source_ref is required")
        if data.get("status") not in ["pending", "completed", "in_progress"]:
            errors.append(f"Invalid task status: {data.get('status')}")
        
        # Check due_at format if present
        due = data.get("due_at")
        if due:
            try:
                # Accept ISO format or YYYY-MM-DD
                if "T" in due:
                    datetime.fromisoformat(due.replace("Z", "+00:00"))
                else:
                    datetime.strptime(due, "%Y-%m-%d")
            except Exception:
                errors.append(f"Invalid due_at date format: {due}")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "object_type": "Task"
        }

    @staticmethod
    def validate_attendance_record(obj: Any) -> Dict[str, Any]:
        data = obj.to_dict() if hasattr(obj, 'to_dict') else obj
        errors = []
        if not data.get("course"):
            errors.append("Attendance course is required")
        
        conducted = data.get("conducted_classes", 0)
        attended = data.get("attended_classes", 0)

        if not isinstance(conducted, int) or conducted < 0:
            errors.append("conducted_classes must be a non-negative integer")
        if not isinstance(attended, int) or attended < 0:
            errors.append("attended_classes must be a non-negative integer")
        if isinstance(conducted, int) and isinstance(attended, int) and attended > conducted:
            errors.append(f"attended_classes ({attended}) cannot exceed conducted_classes ({conducted})")
        if conducted == 0 and attended > 0:
            errors.append("conducted_classes is 0 but attended_classes > 0")

        # Validate percentage calculation consistency
        if conducted > 0 and isinstance(attended, int) and isinstance(conducted, int):
            expected_pct = round((attended / conducted) * 100, 2)
            actual_pct = round(float(data.get("percentage", 0.0)), 2)
            if abs(expected_pct - actual_pct) > 0.5:
                errors.append(f"Percentage mismatch: recorded {actual_pct}%, calculated {expected_pct}%")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "object_type": "AttendanceRecord"
        }

    @staticmethod
    def validate_exam_event(obj: Any) -> Dict[str, Any]:
        data = obj.to_dict() if hasattr(obj, 'to_dict') else obj
        errors = []
        if not data.get("class_id"):
            errors.append("Exam class_id is required")
        if not data.get("course"):
            errors.append("Exam course is required")
        
        exam_date = data.get("exam_date")
        if not exam_date:
            errors.append("Exam exam_date is required")
        else:
            try:
                datetime.strptime(exam_date, "%Y-%m-%d")
            except Exception:
                errors.append(f"Invalid exam_date format (expected YYYY-MM-DD): {exam_date}")

        if not isinstance(data.get("study_leave_days_before"), int):
            errors.append("study_leave_days_before must be an integer")
        elif data.get("study_leave_days_before") < 0:
            errors.append("study_leave_days_before cannot be negative")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "object_type": "ExamEvent"
        }

    @staticmethod
    def validate_plan_diff(obj: Any) -> Dict[str, Any]:
        data = obj.to_dict() if hasattr(obj, 'to_dict') else obj
        errors = []
        if not isinstance(data.get("added_tasks"), list):
            errors.append("added_tasks must be a list")
        if not isinstance(data.get("modified_tasks"), list):
            errors.append("modified_tasks must be a list")
        if not isinstance(data.get("removed_task_ids"), list):
            errors.append("removed_task_ids must be a list")
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "object_type": "PlanDiff"
        }

    @staticmethod
    def validate_helpdesk_answer(obj: Any) -> Dict[str, Any]:
        data = obj.to_dict() if hasattr(obj, 'to_dict') else obj
        errors = []
        if not data.get("query"):
            errors.append("Helpdesk query is required")
        if not data.get("answer"):
            errors.append("Helpdesk answer is required")
        conf = data.get("confidence", 1.0)
        if not (0.0 <= conf <= 1.0):
            errors.append("confidence score must be between 0.0 and 1.0")
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "object_type": "HelpdeskAnswer"
        }

    @classmethod
    def validate(cls, obj: Any) -> Dict[str, Any]:
        """Auto-detect object type and validate."""
        data = obj.to_dict() if hasattr(obj, 'to_dict') else obj
        if "due_at" in data or "source_ref" in data or isinstance(obj, Task):
            return cls.validate_task(obj)
        elif "conducted_classes" in data or isinstance(obj, AttendanceRecord):
            return cls.validate_attendance_record(obj)
        elif "study_leave_days_before" in data or isinstance(obj, ExamEvent):
            return cls.validate_exam_event(obj)
        elif "added_tasks" in data or isinstance(obj, PlanDiff):
            return cls.validate_plan_diff(obj)
        elif "confidence" in data or isinstance(obj, HelpdeskAnswer):
            return cls.validate_helpdesk_answer(obj)
        else:
            return {"valid": False, "errors": ["Unknown schema object type"], "object_type": "Unknown"}
