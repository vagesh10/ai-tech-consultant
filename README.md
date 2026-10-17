# AI Tech Consultant

A three-service AI Tech Consultant capstone project.

## Services

| Task | Technology | Local URL |
|---|---|---|
| Knowledge Brain | Python, FastAPI | http://127.0.0.1:8000 |
| Inbox Agent | TypeScript, Express, SQLite | http://127.0.0.1:3001 |
| Meeting-to-SOW | Python, FastAPI, SQLite | http://127.0.0.1:8002 |

## Prerequisites

- Python environment at `task1-knowledge-brain/.venv`
- Node.js and npm
- Task dependencies installed

## Start all services

From the repository root, run:

```powershell
.\start-all.ps1
```

Health checks:

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:3001/health`
- `http://127.0.0.1:8002/health`

## Run tests

Task 1:

```powershell
Set-Location task1-knowledge-brain
python -m pytest tests -q
Set-Location ..
```

Task 2:

```powershell
Set-Location task2-inbox-agent
npm run build
npm test
Set-Location ..
```

Task 3:

```powershell
Set-Location task3-meeting-to-sow
python -m pytest tests -q
Set-Location ..
```

## Current limitations

- Task 2 approval does not send an email.
- Task 3 currently uses rule-based transcript extraction and requires human approval.
- Genuine Claude generation and complete end-to-end AI workflows must be verified separately.
- Evaluation results should reflect actual measured runs, not estimates.

## Project structure

- `task1-knowledge-brain/` — support knowledge retrieval and escalation API
- `task2-inbox-agent/` — email classification, draft review, and feedback API
- `task3-meeting-to-sow/` — transcript analysis and draft SOW API

See `DESIGN.md`, `EVALS.md`, and `AI_LOG.md` for architecture, evaluations, and development notes.
