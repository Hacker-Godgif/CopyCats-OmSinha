# StudyOS-India Shared Schema Specification

This document defines the core data contracts for StudyOS-India agents (Ingestion, Planner, Helpdesk, Notification, and UI).

---

## 1. Task

Represents an academic task, assignment, or deadline parsed from syllabi, timetables, or Classroom imports.

```typescript
interface Task {
  id: string;                      // Unique ID (UUIDv4)
  title: string;                   // Title or description of the task
  course: string;                  // Subject / Course name or code (e.g., "CS101", "Mathematics-III")
  due_at: string | null;           // ISO 8601 DateTime string (e.g., "2026-08-15T23:59:00Z") or YYYY-MM-DD
  source_ref: string;              // Line/page reference (e.g. "Syllabus.pdf page 3, line 12") or "Mock Classroom Import"
  status: 'pending' | 'completed' | 'in_progress';
  needs_manual_review: boolean;    // Flagged true if parser low confidence or malformed
  review_reason?: string | null;   // Explanation if needs_manual_review is true
  created_at: string;              // ISO 8601 DateTime string
}
```

---

## 2. AttendanceRecord

Represents subject-wise class attendance status extracted from attendance sheets.

```typescript
interface AttendanceRecord {
  id: string;                      // Unique ID (UUIDv4)
  student_id?: string;             // Optional Student Identifier
  course: string;                  // Subject / Course name or code
  conducted_classes: number;       // Total number of classes conducted
  attended_classes: number;        // Total number of classes attended
  percentage: number;              // Calculated percentage: (attended_classes / conducted_classes) * 100
  needs_manual_review: boolean;    // True if conducted < attended, conducted == 0, or parsing low confidence
  review_reason?: string | null;   // Explanation if parsing is suspect
  updated_at: string;              // ISO 8601 DateTime string
}
```

---

## 3. ExamEvent

Represents an exam scheduled in a datesheet along with computed study leave days.

```typescript
interface ExamEvent {
  id: string;                      // Unique ID (UUIDv4)
  class_id: string;                // Identifier for the class/section/batch (e.g., "CSE-2026-A")
  course: string;                  // Subject / Course name or code
  exam_date: string;               // ISO 8601 Date string (YYYY-MM-DD)
  study_leave_days_before: number; // Exact free calendar days between previous exam (or term start) and this exam date
  needs_manual_review: boolean;    // Flagged true if date parsing uncertain or overlapping dates
  review_reason?: string | null;   // Explanation if needs_manual_review is true
}
```

---

## 4. PlanDiff

Represents the incremental schedule or task changes produced when adjusting study plans.

```typescript
interface PlanDiff {
  id: string;                      // Unique ID (UUIDv4)
  generated_at: string;            // ISO 8601 DateTime string
  added_tasks: Task[];             // Newly created tasks added to plan
  modified_tasks: Task[];          // Updated tasks
  removed_task_ids: string[];      // IDs of removed tasks
  summary: string;                 // Human-readable summary of modifications
}
```

---

## 5. HelpdeskAnswer

Represents an AI/system response to student inquiries with source citations.

```typescript
interface HelpdeskAnswer {
  id: string;                      // Unique ID (UUIDv4)
  query: string;                   // Original student query
  answer: string;                  // Generated response text
  sources: string[];               // List of source citations/references
  confidence: number;              // Confidence score between 0.0 and 1.0
  needs_manual_review: boolean;    // Flagged true if confidence < threshold or query ambiguous
  review_reason?: string | null;   // Reason for manual review flag
}
```

---

## 6. AgentLogEntry

Represents a structured log entry emitted by agents during planning, execution, and verification phases.

```typescript
interface AgentLogEntry {
  id: string;                      // Unique ID (UUIDv4)
  agent_name: str;                 // e.g. "Attendance-Risk Agent"
  action: str;                     // e.g. "Generated AttendanceRecord for Physics"
  timestamp: string;               // ISO 8601 DateTime string
  status: 'planning' | 'running' | 'verifying' | 'passed' | 'failed';
  checks_run: number;              // Number of assertions run against output
  checks_passed: number;           // Number of assertions passed
  failure_reason: string | null;   // One sentence explanation if status = failed
}
```

