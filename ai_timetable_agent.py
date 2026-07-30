"""Vision-AI adapter for timetable extraction.

It speaks the widely-supported OpenAI-compatible chat-completions format so
the deployment can select its own approved provider without exposing a key in
source control. The output is constrained and validated before persistence.
"""

import base64
import json
import os
import urllib.error
import urllib.request
from pathlib import Path


WEEKDAYS = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}


class TimetableVisionAgent:
    def __init__(self):
        self._load_local_env()
        placeholders = {
            "replace_with_your_key", "your_secret_key", "your_api_key", "your_key",
            "your-vision-capable-model", "your_vision_capable_model", "your-model",
            "https://your-provider.example/v1", "https://example.com/v1"
        }

        def get_val(ai_name, openai_name):
            val1 = os.getenv(ai_name, "")
            if val1 and val1.lower() not in placeholders and val1 not in placeholders:
                return val1
            val2 = os.getenv(openai_name, "")
            if val2 and val2.lower() not in placeholders and val2 not in placeholders:
                return val2
            return val1 or val2 or ""

        self.api_key = get_val("AI_API_KEY", "OPENAI_API_KEY")
        self.base_url = get_val("AI_BASE_URL", "OPENAI_BASE_URL").rstrip("/")
        self.model = get_val("AI_MODEL", "OPENAI_MODEL")

    @staticmethod
    def _load_local_env():
        """Load a developer's local .env without adding a dependency or overwriting environment secrets."""
        env_file = Path(__file__).resolve().parent / ".env"
        if not env_file.exists():
            return
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if "=" not in line or line.lstrip().startswith("#"):
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

    @property
    def configured(self):
        placeholders = {"replace_with_your_key", "your_secret_key", "your_api_key", "your_key", "your-vision-capable-model", "your_vision_capable_model", "your-model"}
        return bool(self.api_key and self.base_url and self.model and self.api_key.lower() not in placeholders and self.model.lower() not in placeholders and self.base_url not in {"https://your-provider.example/v1", "https://example.com/v1"})

    def analyse(self, image_bytes, mime_type, context):
        instructions = """You extract a recurring weekly Indian college timetable from an uploaded image. Return ONLY valid JSON with this exact shape: {\"summary\": string, \"classes\": [{\"course\": string, \"weekday\": 0, \"start_time\": \"HH:MM\", \"end_time\": \"HH:MM\", \"room\": string, \"confidence\": \"confirmed\"|\"review\"}], \"uncertainties\": [string]}. weekday uses Monday=0 through Sunday=6. Include only actual teaching/lab sessions, not breaks. If any text, day, or time is unclear, still extract the best reading but use confidence=review and state why in uncertainties. Do not invent classes."""
        try:
            parsed = self._ask(instructions, image_bytes, mime_type, context)
        except ValueError as exc:
            parsed = self._fallback_response(str(exc), context)
        classes = parsed.get("classes", [])
        if not isinstance(classes, list):
            raise ValueError("The AI response did not contain a class list.")
        parsed["classes"] = self._normalise(classes)
        return parsed

    def analyse_attendance(self, image_bytes, mime_type, context):
        instructions = """You extract an attendance report from an uploaded Indian college portal screenshot or document. Return ONLY valid JSON with this exact shape: {\"summary\": string, \"records\": [{\"course\": string, \"conducted_classes\": 0, \"attended_classes\": 0, \"confidence\": \"confirmed\"|\"review\"}], \"uncertainties\": [string]}. Do not infer values that are absent. Mark unreadable rows review."""
        try:
            parsed = self._ask(instructions, image_bytes, mime_type, context)
        except ValueError as exc:
            return self._fallback_response(str(exc), context, records=True)
        records = []
        for row in parsed.get("records", []):
            try:
                course = str(row.get("course", "")).strip()
                conducted, attended = int(row.get("conducted_classes")), int(row.get("attended_classes"))
                if course and 0 <= attended <= conducted:
                    records.append({"course": course, "conducted_classes": conducted, "attended_classes": attended, "confidence": "confirmed" if row.get("confidence") == "confirmed" else "review"})
            except (TypeError, ValueError):
                continue
        if not records:
            raise ValueError("The AI could not identify valid attendance records. Upload a clearer screenshot showing course, attended, and conducted classes.")
        parsed["records"] = records
        return parsed

    def _ask(self, instructions, image_bytes, mime_type, context):
        if not self.configured:
            raise ValueError("AI provider not configured. The upload will be saved for manual review until a real provider is configured.")
        encoded = base64.b64encode(image_bytes).decode("ascii")
        payload = {"model": self.model, "temperature": 0, "response_format": {"type": "json_object"}, "messages": [{"role": "system", "content": instructions}, {"role": "user", "content": [{"type": "text", "text": "Student context: " + json.dumps(context)}, {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{encoded}"}}]}]}
        request = urllib.request.Request(self.base_url + "/chat/completions", data=json.dumps(payload).encode("utf-8"), headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")[:240]
            raise ValueError(f"The AI provider rejected the timetable image ({exc.code}). Check the configured provider, model, and key. {detail}")
        except urllib.error.URLError as exc:
            raise ValueError(f"Could not reach the configured AI provider: {exc.reason}")
        try:
            content = result["choices"][0]["message"]["content"]
            parsed = json.loads(content)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError("The AI returned an unreadable result. Please retry with a clearer image.") from exc
        return parsed

    def _fallback_response(self, reason, context, records=False):
        summary = "Timetable upload saved for manual review because the AI provider is not configured." if not records else "Attendance upload saved for manual review because the AI provider is not configured."
        uncertainties = [reason or "The upload could not be processed automatically.", "The app switched to a local fallback so your upload does not fail. Review the values manually before relying on them."]
        if not records:
            return {"summary": summary, "classes": [], "uncertainties": uncertainties, "fallback_used": True, "context": context}
        return {"summary": summary, "records": [], "uncertainties": uncertainties, "fallback_used": True, "context": context}

    def _normalise(self, classes):
        valid = []
        for entry in classes:
            try:
                weekday = entry.get("weekday")
                if isinstance(weekday, str):
                    clean_day = weekday.lower().strip()
                    weekday = WEEKDAYS[clean_day] if clean_day in WEEKDAYS else (int(clean_day) if clean_day.isdigit() else -1)
                weekday = int(weekday)
                course = str(entry.get("course", "")).strip()
                start, end = str(entry.get("start_time", "")).strip(), str(entry.get("end_time", "")).strip()
                if course and weekday in range(7) and len(start) == 5 and len(end) == 5:
                    valid.append({"course": course, "weekday": weekday, "start_time": start, "end_time": end, "room": str(entry.get("room", "")).strip(), "confidence": "confirmed" if entry.get("confidence") == "confirmed" else "review"})
            except (TypeError, ValueError):
                continue
        return valid
