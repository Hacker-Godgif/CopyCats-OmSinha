# StudyOS India

StudyOS India is a student-first academic workspace for tracking attendance,
deadlines, weekly study plans, and campus-policy questions. This MVP stores its
data locally in `data/studyos.db`.

## Run locally

```powershell
.\.venv\Scripts\python.exe app.py
```

Open `http://127.0.0.1:5000` in a browser.

If the virtual environment has not been created yet:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Core student workflow

1. Set up the college, programme, semester, and realistic daily study time.
2. Import attendance with `Course,Conducted,Attended` columns.
3. Add small tasks with their course, due date, and estimate.
4. Generate a weekly plan, complete tasks, and export upcoming deadlines to a
   calendar file.
5. Ask policy questions only as a starting point; verify time-sensitive rules
   with the official college portal or examination cell.

## Trust and privacy

- The MVP is single-user and stores profile, attendance, and task data locally.
- Policy documents bundled in `campus_policies.json` are demonstration content,
  not a substitute for institution-specific notices.
- The UI deliberately shows source and threshold information, and does not
  claim a task or calculation is verified unless the backend has produced it.

## Enable timetable and attendance image AI

StudyOS uses a configurable, OpenAI-compatible vision endpoint. Copy
`.env.example` to a local `.env` file and set the values supplied by the AI
provider you choose:

```text
AI_API_KEY=your_secret_key
AI_BASE_URL=https://your-provider.example/v1
AI_MODEL=your_vision_capable_model
```

Do not commit or paste a real API key into source code, chat, screenshots, or
repositories. After configuration, use **Upload timetable image** and **Upload
attendance image**. The AI extracts recurring classes and attendance records;
review the result before relying on the holiday/bunk calculation.

## Verification

```powershell
.\.venv\Scripts\python.exe -m unittest discover -v
```

The original test suite verifies ingestion, attendance risk, planner,
reflection, helpdesk grounding, and activity logging.
