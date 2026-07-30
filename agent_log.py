"""
AgentLog — Shared structured logging system for StudyOS-India.
Every agent/module emits AgentLogEntry records through this system.
Entries are stored in-memory (with optional SQLite persistence) and
retrieved newest-first via get_recent_logs(limit).
"""

import uuid
import threading
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Callable, Any, Dict


# ---------------------------------------------------------------------------
# AgentLogEntry dataclass (matches SCHEMA.md §6)
# ---------------------------------------------------------------------------
@dataclass
class AgentLogEntry:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agent_name: str = ""
    action: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: str = "planning"   # planning | running | verifying | passed | failed
    checks_run: int = 0
    checks_passed: int = 0
    failure_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Global in-memory log store (thread-safe)
# ---------------------------------------------------------------------------
class _AgentLogStore:
    def __init__(self):
        self._entries: List[AgentLogEntry] = []
        self._lock = threading.Lock()

    def append(self, entry: AgentLogEntry):
        with self._lock:
            self._entries.append(entry)

    def get_recent(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            # newest-first
            return [e.to_dict() for e in reversed(self._entries[-limit:])]

    def get_all(self) -> List[AgentLogEntry]:
        with self._lock:
            return list(self._entries)

    def clear(self):
        with self._lock:
            self._entries.clear()


# Module-level singleton
_store = _AgentLogStore()


def get_recent_logs(limit: int = 50) -> List[Dict[str, Any]]:
    """Return the most recent log entries, newest-first."""
    return _store.get_recent(limit)


def get_all_entries() -> List[AgentLogEntry]:
    """Return all raw AgentLogEntry objects (for testing)."""
    return _store.get_all()


def clear_logs():
    """Clear all entries (for testing)."""
    _store.clear()


# ---------------------------------------------------------------------------
# emit_log — low-level entry point every agent calls
# ---------------------------------------------------------------------------
def emit_log(
    agent_name: str,
    action: str,
    status: str,
    checks_run: int = 0,
    checks_passed: int = 0,
    failure_reason: Optional[str] = None,
) -> AgentLogEntry:
    entry = AgentLogEntry(
        agent_name=agent_name,
        action=action,
        status=status,
        checks_run=checks_run,
        checks_passed=checks_passed,
        failure_reason=failure_reason,
    )
    _store.append(entry)
    return entry


# ---------------------------------------------------------------------------
# run_with_logging — decorator/helper that wraps an agent function and
# emits the required 4 log entries: planning → running → verifying → passed/failed
#
# The caller supplies a `checks_fn(result) -> (checks_run, checks_passed, failures)`
# where `failures` is a list of failure reason strings (empty = all passed).
# ---------------------------------------------------------------------------
def run_with_logging(
    agent_name: str,
    action_description: str,
    compute_fn: Callable[[], Any],
    checks_fn: Callable[[Any], tuple],  # -> (checks_run, checks_passed, [failure_reasons])
) -> Any:
    """
    Execute `compute_fn`, emit exactly 4 ordered log entries, and return the result.

    Log sequence:
      1. planning  — about to start
      2. running   — computation in progress / done
      3. verifying — running Definition-of-Done checks
      4. passed OR failed — final verdict with checks_run/checks_passed
    """
    # 1. planning
    emit_log(agent_name, f"Planning: {action_description}", "planning")

    # 2. running
    result = compute_fn()
    emit_log(agent_name, f"Computed: {action_description}", "running")

    # 3. verifying
    emit_log(agent_name, f"Verifying: {action_description}", "verifying")

    # 4. passed / failed
    checks_run, checks_passed, failures = checks_fn(result)
    if checks_passed == checks_run and checks_run > 0:
        emit_log(
            agent_name,
            f"Verified: {action_description}",
            "passed",
            checks_run=checks_run,
            checks_passed=checks_passed,
        )
    else:
        reason = "; ".join(failures) if failures else "Unknown verification failure"
        emit_log(
            agent_name,
            f"Verification failed: {action_description}",
            "failed",
            checks_run=checks_run,
            checks_passed=checks_passed,
            failure_reason=reason,
        )

    return result
