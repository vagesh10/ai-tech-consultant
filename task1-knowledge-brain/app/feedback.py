
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.ingestion.storage import DEFAULT_DB_PATH


class FeedbackStore:
    VALID_RATINGS = {"positive", "negative"}

    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self):
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self):
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    rating TEXT NOT NULL
                        CHECK (rating IN ('positive', 'negative')),
                    comment TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )

    def submit(
        self,
        question: str,
        answer: str,
        rating: str,
        comment: str | None = None,
    ) -> dict:
        question = question.strip()
        answer = answer.strip()
        rating = rating.strip().lower()
        comment = comment.strip() if comment else None

        if not question:
            raise ValueError("Question cannot be empty.")

        if not answer:
            raise ValueError("Answer cannot be empty.")

        if rating not in self.VALID_RATINGS:
            raise ValueError("Rating must be 'positive' or 'negative'.")

        created_at = datetime.now(timezone.utc).isoformat()

        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO feedback
                    (question, answer, rating, comment, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (question, answer, rating, comment, created_at),
            )
            feedback_id = cursor.lastrowid

        return self.get(feedback_id)

    def get(self, feedback_id: int) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM feedback WHERE id = ?",
                (feedback_id,),
            ).fetchone()

        return dict(row) if row else None

    def list_items(
        self,
        rating: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        if not 1 <= limit <= 500:
            raise ValueError("Limit must be between 1 and 500.")

        if rating is not None:
            rating = rating.strip().lower()
            if rating not in self.VALID_RATINGS:
                raise ValueError("Invalid rating.")

        with self._connect() as connection:
            if rating:
                rows = connection.execute(
                    """
                    SELECT * FROM feedback
                    WHERE rating = ?
                    ORDER BY id DESC LIMIT ?
                    """,
                    (rating, limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT * FROM feedback
                    ORDER BY id DESC LIMIT ?
                    """,
                    (limit,),
                ).fetchall()

        return [dict(row) for row in rows]
