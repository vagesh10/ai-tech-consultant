import json
import os
import sqlite3
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.analyzer import analyze_transcript


BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = Path(
    os.getenv("SOW_DB_PATH", str(BASE_DIR / "data" / "sows.db"))
)
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="Meeting-to-SOW API",
    description="Analyze meeting transcripts and create draft Statements of Work.",
    version="1.1.0",
)


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database() -> None:
    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS sows (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                project_name TEXT NOT NULL,
                scope_json TEXT NOT NULL,
                deliverables_json TEXT NOT NULL,
                assumptions_json TEXT NOT NULL,
                exclusions_json TEXT NOT NULL,
                open_questions_json TEXT NOT NULL,
                source_transcript TEXT NOT NULL,
                review_required INTEGER NOT NULL,
                approved_by TEXT,
                notes_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


@app.on_event("startup")
def startup() -> None:
    initialize_database()


class TranscriptRequest(BaseModel):
    transcript: str = Field(
        min_length=1,
        description="The meeting transcript to analyze.",
    )


class SOWApprovalRequest(BaseModel):
    reviewer: str = Field(min_length=1, max_length=100)


def row_to_sow(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "status": row["status"],
        "project_name": row["project_name"],
        "scope": json.loads(row["scope_json"]),
        "deliverables": json.loads(row["deliverables_json"]),
        "assumptions": json.loads(row["assumptions_json"]),
        "exclusions": json.loads(row["exclusions_json"]),
        "open_questions": json.loads(row["open_questions_json"]),
        "source_transcript": row["source_transcript"],
        "review_required": bool(row["review_required"]),
        "approved_by": row["approved_by"],
        "notes": json.loads(row["notes_json"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def fetch_sow(sow_id: str) -> dict | None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM sows WHERE id = ?",
            (sow_id,),
        ).fetchone()

    return row_to_sow(row) if row else None


@app.get("/health")
def health():
    try:
        with get_connection() as connection:
            connection.execute("SELECT 1")
        return {
            "status": "healthy",
            "service": "meeting-to-sow",
            "database": "connected",
        }
    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=503,
            detail="Database unavailable.",
        ) from exc


@app.post("/analyze")
def analyze(request: TranscriptRequest):
    if not request.transcript.strip():
        raise HTTPException(
            status_code=422,
            detail="Transcript cannot be empty or whitespace only.",
        )

    try:
        return analyze_transcript(request.transcript)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/sow/generate")
def generate_sow(request: TranscriptRequest):
    if not request.transcript.strip():
        raise HTTPException(
            status_code=422,
            detail="Transcript cannot be empty or whitespace only.",
        )

    try:
        analysis = analyze_transcript(request.transcript)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    sow = {
        "id": str(uuid4()),
        "status": "pending_review",
        "project_name": "Untitled Project",
        "scope": analysis["scope"],
        "deliverables": analysis["deliverables"],
        "assumptions": analysis["assumptions"],
        "exclusions": analysis["exclusions"],
        "open_questions": analysis["open_questions"],
        "source_transcript": request.transcript,
        "review_required": True,
        "approved_by": None,
        "notes": [
            "This is a draft SOW generated using rule-based extraction.",
            "Confirm scope, deliverables, estimates, and commercial terms before approval.",
            "No effort, cost, or delivery timeline has been invented.",
        ],
    }

    try:
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO sows (
                    id, status, project_name, scope_json,
                    deliverables_json, assumptions_json, exclusions_json,
                    open_questions_json, source_transcript,
                    review_required, approved_by, notes_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sow["id"],
                    sow["status"],
                    sow["project_name"],
                    json.dumps(sow["scope"]),
                    json.dumps(sow["deliverables"]),
                    json.dumps(sow["assumptions"]),
                    json.dumps(sow["exclusions"]),
                    json.dumps(sow["open_questions"]),
                    sow["source_transcript"],
                    1,
                    None,
                    json.dumps(sow["notes"]),
                ),
            )
    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=500,
            detail="Could not save the SOW.",
        ) from exc

    saved_sow = fetch_sow(sow["id"])
    if saved_sow is None:
        raise HTTPException(status_code=500, detail="SOW could not be retrieved.")

    return saved_sow


@app.get("/sow/{sow_id}")
def get_sow(sow_id: str):
    sow = fetch_sow(sow_id)

    if sow is None:
        raise HTTPException(status_code=404, detail="SOW not found.")

    return sow


@app.post("/sow/{sow_id}/approve")
def approve_sow(sow_id: str, request: SOWApprovalRequest):
    reviewer = request.reviewer.strip()
    if not reviewer:
        raise HTTPException(
            status_code=422,
            detail="Reviewer name cannot be empty.",
        )

    try:
        with get_connection() as connection:
            cursor = connection.execute(
                """
                UPDATE sows
                SET status = 'approved',
                    approved_by = ?,
                    review_required = 0,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status = 'pending_review'
                """,
                (reviewer, sow_id),
            )

            if cursor.rowcount == 0:
                row = connection.execute(
                    "SELECT status FROM sows WHERE id = ?",
                    (sow_id,),
                ).fetchone()

                if row is None:
                    raise HTTPException(
                        status_code=404,
                        detail="SOW not found.",
                    )

                raise HTTPException(
                    status_code=409,
                    detail="Only SOWs pending review can be approved.",
                )

    except HTTPException:
        raise
    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=500,
            detail="Could not update SOW approval.",
        ) from exc

    sow = fetch_sow(sow_id)
    return {
        "message": "SOW approved.",
        "sow": sow,
    }
