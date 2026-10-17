import json
import os
import sqlite3
import urllib.error
import urllib.request
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

KNOWLEDGE_BRAIN_URL = os.getenv(
    "KNOWLEDGE_BRAIN_URL",
    "http://127.0.0.1:8000",
).rstrip("/")

app = FastAPI(
    title="Meeting-to-SOW API",
    description=(
        "Analyze meeting transcripts, check product-support documentation, "
        "and create draft Statements of Work."
    ),
    version="1.2.0",
)


# ---------------------------------------------------------
# DATABASE
# ---------------------------------------------------------

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


# ---------------------------------------------------------
# REQUEST MODELS
# ---------------------------------------------------------

class TranscriptRequest(BaseModel):
    transcript: str = Field(
        min_length=1,
        description="The meeting transcript to analyze.",
    )


class SOWApprovalRequest(BaseModel):
    reviewer: str = Field(min_length=1, max_length=100)


class FollowUpRequest(BaseModel):
    transcript: str = Field(
        min_length=1,
        description="The follow-up meeting transcript.",
    )


# ---------------------------------------------------------
# DATABASE HELPERS
# ---------------------------------------------------------

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


# ---------------------------------------------------------
# TASK 1: KNOWLEDGE BRAIN INTEGRATION
# ---------------------------------------------------------

def check_product_feasibility(request_text: str) -> dict:
    """
    Ask Task 1 whether retrieved support documentation supports
    a potential product-settings solution.

    An unavailable or mock response is not treated as verified
    evidence that a feature is supported.
    """

    payload = json.dumps(
        {
            "question": (
                "Assess whether the following requested feature may be "
                "possible using existing Brilliant Directories product "
                "settings rather than custom development. Use only the "
                "retrieved support documentation and cite its sources. "
                "If the evidence is insufficient, explicitly state that "
                "the answer is unknown. Do not invent product capabilities. "
                f"Request: {request_text}"
            )
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        f"{KNOWLEDGE_BRAIN_URL}/ask",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            result = json.loads(response.read().decode("utf-8"))

        answer = result.get("answer", "")
        sources = result.get("sources", [])
        abstained = result.get("abstained", True)

        # Task 1 may be running in mock mode. Do not mistake its
        # local test response for an actual product feasibility answer.
        is_mock_response = (
            "not a real Claude-generated answer" in answer.lower()
        )

        if abstained or is_mock_response or not sources:
            status = "unknown"
        else:
            status = "review_required"

        return {
            "status": status,
            "answer": answer,
            "sources": sources,
            "abstained": abstained,
            "mock_response": is_mock_response,
            "note": (
                "A human must verify the cited documentation before "
                "deciding whether custom development is required."
            ),
        }

    except (
        urllib.error.URLError,
        TimeoutError,
        json.JSONDecodeError,
    ) as exc:
        return {
            "status": "unavailable",
            "answer": "",
            "sources": [],
            "abstained": True,
            "mock_response": False,
            "note": (
                "Knowledge Brain could not be reached. "
                f"Error type: {type(exc).__name__}."
            ),
        }


# ---------------------------------------------------------
# HEALTH CHECK
# ---------------------------------------------------------

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


# ---------------------------------------------------------
# ANALYZE TRANSCRIPT
# ---------------------------------------------------------

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
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc


# ---------------------------------------------------------
# GENERATE SOW
# ---------------------------------------------------------

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
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    # Check the knowledge base before finalizing the draft.
    feasibility = check_product_feasibility(request.transcript)

    notes = [
        "This is a draft SOW generated using rule-based extraction.",
        (
            "Confirm scope, deliverables, estimates, and commercial terms "
            "before approval."
        ),
        "No effort, cost, or delivery timeline has been invented.",
        (
            "Product feasibility status: "
            f"{feasibility['status']}."
        ),
    ]

    if feasibility["status"] != "review_required":
        notes.append(
            "Product-settings feasibility remains unverified."
        )

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
        "notes": notes,
    }

    try:
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO sows (
                    id,
                    status,
                    project_name,
                    scope_json,
                    deliverables_json,
                    assumptions_json,
                    exclusions_json,
                    open_questions_json,
                    source_transcript,
                    review_required,
                    approved_by,
                    notes_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        raise HTTPException(
            status_code=500,
            detail="SOW could not be retrieved.",
        )

    saved_sow["product_feasibility"] = feasibility
    return saved_sow

# ---------------------------------------------------------
# GET SOW
# ---------------------------------------------------------

@app.get("/sow/{sow_id}")
def get_sow(sow_id: str):
    sow = fetch_sow(sow_id)

    if sow is None:
        raise HTTPException(
            status_code=404,
            detail="SOW not found.",
        )

    return sow


# ---------------------------------------------------------
# FOLLOW-UP MEETING
# ---------------------------------------------------------


@app.post("/sow/{sow_id}/follow-up")
def follow_up_sow(sow_id: str, request: FollowUpRequest):
    previous = fetch_sow(sow_id)

    if previous is None:
        raise HTTPException(status_code=404, detail="SOW not found.")

    if previous["status"] != "pending_review":
        raise HTTPException(
            status_code=409,
            detail="Only a SOW pending review can be updated.",
        )

    if not request.transcript.strip():
        raise HTTPException(
            status_code=422,
            detail="Follow-up transcript cannot be empty.",
        )

    try:
        analysis = analyze_transcript(request.transcript)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    def merge_items(old_items, new_items):
        """Preserve existing items and append new items without duplicates."""
        merged = list(old_items)
        seen = {item["text"].strip().casefold() for item in merged}

        for item in new_items:
            key = item["text"].strip().casefold()
            if key not in seen:
                merged.append(item)
                seen.add(key)

        return merged

    # Preserve the existing scope and add new requirements.
    updated_scope = merge_items(previous["scope"], analysis["scope"])

    previous_scope_text = {item["text"] for item in previous["scope"]}
    updated_scope_text = {item["text"] for item in updated_scope}

    changes = {
        "added_scope": sorted(updated_scope_text - previous_scope_text),
        "removed_scope": [],
        "scope_unchanged": updated_scope_text == previous_scope_text,
        "note": (
            "Existing scope is preserved automatically. "
            "Potential removals must be confirmed by a human reviewer."
        ),
    }

    # Merge the remaining sections rather than overwriting earlier decisions.
    updated_deliverables = merge_items(
        previous["deliverables"], analysis["deliverables"]
    )
    updated_assumptions = merge_items(
        previous["assumptions"], analysis["assumptions"]
    )
    updated_exclusions = merge_items(
        previous["exclusions"], analysis["exclusions"]
    )
    updated_questions = merge_items(
        previous["open_questions"], analysis["open_questions"]
    )

    feasibility = check_product_feasibility(request.transcript)

    combined_transcript = (
        previous["source_transcript"].rstrip()
        + "\n\n--- Follow-up meeting ---\n"
        + request.transcript.strip()
    )

    notes = list(previous["notes"])
    notes.extend([
        "Updated using a follow-up meeting transcript.",
        "Existing scope was preserved; new items were merged without duplicates.",
        "Review possible removals and all changes before approval.",
        "Effort estimates, costs, and delivery dates require human validation.",
        f"Latest product feasibility status: {feasibility['status']}.",
    ])

    try:
        with get_connection() as connection:
            cursor = connection.execute(
                """
                UPDATE sows
                SET scope_json = ?,
                    deliverables_json = ?,
                    assumptions_json = ?,
                    exclusions_json = ?,
                    open_questions_json = ?,
                    source_transcript = ?,
                    notes_json = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status = 'pending_review'
                """,
                (
                    json.dumps(updated_scope),
                    json.dumps(updated_deliverables),
                    json.dumps(updated_assumptions),
                    json.dumps(updated_exclusions),
                    json.dumps(updated_questions),
                    combined_transcript,
                    json.dumps(notes),
                    sow_id,
                ),
            )

            if cursor.rowcount == 0:
                raise HTTPException(
                    status_code=409,
                    detail="SOW status changed; reload it before updating.",
                )

    except HTTPException:
        raise
    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=500,
            detail="Could not update the SOW.",
        ) from exc

    updated_sow = fetch_sow(sow_id)

    return {
        "sow": updated_sow,
        "changes": changes,
        "product_feasibility": feasibility,
        "review_required": True,
    }


# ---------------------------------------------------------
# HUMAN APPROVAL
# ---------------------------------------------------------

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