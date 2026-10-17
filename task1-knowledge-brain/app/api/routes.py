
import os
import re
import logging
from pathlib import Path
from types import SimpleNamespace

from anthropic import Anthropic
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.answering import ABSTENTION_TEXT, answer_question
from app.escalation import EscalationQueue
from app.feedback import FeedbackStore
from app.ingestion.storage import DEFAULT_DB_PATH
from app.retrieval import search_articles
from app.vector_store import search_vector_index

router = APIRouter()

ORIGINAL_DEFAULT_DB_PATH = Path(DEFAULT_DB_PATH)
MIN_SIMILARITY_SCORE = 0.30


# Request and response models

class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class SourceResponse(BaseModel):
    id: str
    title: str
    url: str


class AskResponse(BaseModel):
    answer: str
    sources: list[SourceResponse]
    abstained: bool
    escalation_id: int | None = None


class EscalationCreateRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    reason: str = Field(min_length=1, max_length=1000)


class EscalationUpdateRequest(BaseModel):
    status: str
    resolution: str | None = Field(default=None, max_length=2000)


class EscalationResponse(BaseModel):
    id: int
    question: str
    reason: str
    status: str
    created_at: str
    updated_at: str
    resolution: str | None


class FeedbackCreateRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    answer: str = Field(min_length=1, max_length=5000)
    rating: str
    comment: str | None = Field(default=None, max_length=2000)


class FeedbackResponse(BaseModel):
    id: int
    question: str
    answer: str
    rating: str
    comment: str | None
    created_at: str


# Local mock client for testing without API credits.

class MockMessages:
    def create(self, **kwargs):
        prompt = kwargs.get("messages", [{}])[0].get("content", "")
        match = re.search(r"\[(S\d+)\]", prompt)

        if match:
            source_id = match.group(1)
            answer = (
                "Mock answer for local API testing. "
                f"Retrieved source: [{source_id}]. "
                "This is not a real Claude-generated answer."
            )
        else:
            answer = (
                "There is not enough information in the provided sources."
            )

        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=answer)]
        )


class MockClaudeClient:
    def __init__(self):
        self.messages = MockMessages()


def get_escalation_queue():
    return EscalationQueue(DEFAULT_DB_PATH)


# Health endpoint

@router.get("/health")
def health_check():
    return {"status": "ok"}


# Ask the knowledge base

@router.post("/ask", response_model=AskResponse)
def ask_question(request: AskRequest):
    mock_mode = (
        os.getenv("KNOWLEDGE_BRAIN_MOCK_MODE", "true").lower() == "true"
    )

    try:
        current_db_path = Path(DEFAULT_DB_PATH)

        if current_db_path.resolve() != ORIGINAL_DEFAULT_DB_PATH.resolve():
            sources = search_articles(
                request.question,
                db_path=current_db_path,
                top_k=5,
            )
        else:
            results = search_vector_index(request.question, top_k=5)
            sources = [
                result
                for result in results
                if result.get("score", 0.0) >= MIN_SIMILARITY_SCORE
            ]

        if not sources:
            escalation = EscalationQueue(current_db_path).create(
                question=request.question,
                reason="No sufficiently relevant source articles were found.",
            )

            return AskResponse(
                answer=ABSTENTION_TEXT,
                sources=[],
                abstained=True,
                escalation_id=escalation["id"],
            )

        client = MockClaudeClient() if mock_mode else Anthropic()

        result = answer_question(
            question=request.question,
            client=client,
            db_path=current_db_path,
            retrieved_sources=sources,
        )

        if result["abstained"]:
            escalation = EscalationQueue(current_db_path).create(
                question=request.question,
                reason=(
                    "The retrieved sources did not support a sufficiently "
                    "confident answer with valid citations."
                ),
            )
            result["escalation_id"] = escalation["id"]
        else:
            result["escalation_id"] = None

        return result

    except Exception as exc:
        logging.exception("Knowledge Brain /ask failed")
        raise HTTPException(
            status_code=502,
            detail="The answering service failed. Check the server logs.",
        ) from exc
# Escalation endpoints

@router.post(
    "/escalations",
    response_model=EscalationResponse,
    status_code=201,
)
def create_escalation(request: EscalationCreateRequest):
    try:
        return get_escalation_queue().create(
            question=request.question,
            reason=request.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/escalations", response_model=list[EscalationResponse])
def list_escalations(
    status: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
):
    try:
        return get_escalation_queue().list_items(
            status=status,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch(
    "/escalations/{escalation_id}",
    response_model=EscalationResponse,
)
def update_escalation(
    escalation_id: int,
    request: EscalationUpdateRequest,
):
    try:
        item = get_escalation_queue().update_status(
            escalation_id,
            status=request.status,
            resolution=request.resolution,
        )

        if item is None:
            raise HTTPException(
                status_code=404,
                detail="Escalation not found.",
            )

        return item

    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# Feedback endpoints

@router.post(
    "/feedback",
    response_model=FeedbackResponse,
    status_code=201,
)
def submit_feedback(request: FeedbackCreateRequest):
    try:
        return FeedbackStore(DEFAULT_DB_PATH).submit(
            question=request.question,
            answer=request.answer,
            rating=request.rating,
            comment=request.comment,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/feedback", response_model=list[FeedbackResponse])
def list_feedback(
    rating: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
):
    try:
        return FeedbackStore(DEFAULT_DB_PATH).list_items(
            rating=rating,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
