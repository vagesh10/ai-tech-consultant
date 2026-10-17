
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.ingestion.storage import DEFAULT_DB_PATH


class EscalationQueue:
    """SQLite-backed queue for questions that need human review."""

    VALID_STATUSES = {"pending", "in_progress", "resolved"}

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
                CREATE TABLE IF NOT EXISTS escalations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending'
                        CHECK (
                            status IN (
                                'pending',
                                'in_progress',
                                'resolved'
                            )
                        ),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    resolution TEXT
                )
                """
            )

    def create(self, question: str, reason: str) -> dict:
        question = question.strip()
        reason = reason.strip()

        if not question:
            raise ValueError("Question cannot be empty")

        if not reason:
            raise ValueError("Escalation reason cannot be empty")

        now = datetime.now(timezone.utc).isoformat()

        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO escalations (
                    question, reason, status, created_at, updated_at
                )
                VALUES (?, ?, 'pending', ?, ?)
                """,
                (question, reason, now, now),
            )
            escalation_id = cursor.lastrowid

        return self.get(escalation_id)

    def get(self, escalation_id: int) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM escalations WHERE id = ?",
                (escalation_id,),
            ).fetchone()

        return dict(row) if row else None

    def list_items(
        self,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        if limit < 1 or limit > 500:
            raise ValueError("Limit must be between 1 and 500")

        if status is not None and status not in self.VALID_STATUSES:
            raise ValueError("Invalid escalation status")

        with self._connect() as connection:
            if status:
                rows = connection.execute(
                    """
                    SELECT * FROM escalations
                    WHERE status = ?
                    ORDER BY created_at ASC
                    LIMIT ?
                    """,
                    (status, limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT * FROM escalations
                    ORDER BY created_at ASC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()

        return [dict(row) for row in rows]

    def update_status(
        self,
        escalation_id: int,
        status: str,
        resolution: str | None = None,
    ) -> dict | None:
        if status not in self.VALID_STATUSES:
            raise ValueError("Invalid escalation status")

        now = datetime.now(timezone.utc).isoformat()
        cleaned_resolution = (
            resolution.strip() if resolution is not None else None
        )

        if status == "resolved" and not cleaned_resolution:
            raise ValueError(
                "A resolution note is required when resolving an escalation"
            )

        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE escalations
                SET status = ?, updated_at = ?, resolution = ?
                WHERE id = ?
                """,
                (status, now, cleaned_resolution, escalation_id),
            )

            if cursor.rowcount == 0:
                return None

        return self.get(escalation_id)
