
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from app.ingestion.parser import Article

DEFAULT_DB_PATH = Path("data/knowledge.db")


class ArticleStore:
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
                CREATE TABLE IF NOT EXISTS articles (
                    url TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    text TEXT NOT NULL,
                    images_json TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    fetched_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    image_text TEXT NOT NULL DEFAULT ''
                )
                """
            )

            # Backward-compatible migration for existing databases.
            existing_article_columns = {
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(articles)"
                ).fetchall()
            }

            if "image_text" not in existing_article_columns:
                connection.execute(
                    "ALTER TABLE articles "
                    "ADD COLUMN image_text TEXT NOT NULL DEFAULT ''"
                )

            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS crawl_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    sitemap_complete INTEGER NOT NULL DEFAULT 0,
                    discovered_count INTEGER NOT NULL DEFAULT 0,
                    successful_count INTEGER NOT NULL DEFAULT 0,
                    failed_count INTEGER NOT NULL DEFAULT 0
                )
                """
            )

            existing_columns = {
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(crawl_runs)"
                ).fetchall()
            }

            migrations = {
                "successful_count": (
                    "ALTER TABLE crawl_runs "
                    "ADD COLUMN successful_count INTEGER NOT NULL DEFAULT 0"
                ),
                "failed_count": (
                    "ALTER TABLE crawl_runs "
                    "ADD COLUMN failed_count INTEGER NOT NULL DEFAULT 0"
                ),
            }

            for column_name, sql in migrations.items():
                if column_name not in existing_columns:
                    connection.execute(sql)

    def save_article(self, article: Article) -> str:
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT content_hash FROM articles WHERE url = ?",
                (article.url,),
            ).fetchone()

            if existing is None:
                status = "new"
            elif existing["content_hash"] != article.content_hash:
                status = "changed"
            else:
                status = "unchanged"

            connection.execute(
                """
                INSERT INTO articles (
                    url, title, text, images_json, content_hash,
                    fetched_at, last_seen_at, active
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT(url) DO UPDATE SET
                    title = excluded.title,
                    text = excluded.text,
                    images_json = excluded.images_json,
                    content_hash = excluded.content_hash,
                    fetched_at = excluded.fetched_at,
                    last_seen_at = excluded.last_seen_at,
                    active = 1
                """,
                (
                    article.url,
                    article.title,
                    article.text,
                    json.dumps(article.images),
                    article.content_hash,
                    article.fetched_at,
                    article.fetched_at,
                ),
            )

        return status

    def get_article(self, url: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM articles WHERE url = ? AND active = 1",
                (url,),
            ).fetchone()

        if row is None:
            return None

        result = dict(row)
        result["images"] = json.loads(result.pop("images_json"))
        return result

    def save_image_text(self, url: str, image_text: str) -> bool:
        """Save OCR text for an existing article."""
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE articles
                SET image_text = ?
                WHERE url = ? AND active = 1
                """,
                (image_text, url),
            )
            return cursor.rowcount > 0

    def get_articles_needing_ocr(self) -> list[dict]:
        """Return active articles with images but no stored OCR text."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT url, title, images_json
                FROM articles
                WHERE active = 1
                  AND images_json != '[]'
                  AND TRIM(image_text) = ''
                ORDER BY url
                """
            ).fetchall()

        results = []

        for row in rows:
            results.append(
                {
                    "url": row["url"],
                    "title": row["title"],
                    "images": json.loads(row["images_json"] or "[]"),
                }
            )

        return results

    def count_articles(self) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM articles WHERE active = 1"
            ).fetchone()

        return int(row["count"])

    def start_crawl(self) -> int:
        from datetime import datetime, timezone

        started_at = datetime.now(timezone.utc).isoformat()

        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO crawl_runs (started_at)
                VALUES (?)
                """,
                (started_at,),
            )
            return int(cursor.lastrowid)

    def finish_crawl(
        self,
        run_id: int,
        discovered_count: int,
        successful_count: int,
        failed_count: int,
        sitemap_complete: bool,
    ) -> None:
        from datetime import datetime, timezone

        completed_at = datetime.now(timezone.utc).isoformat()

        with self._connect() as connection:
            connection.execute(
                """
                UPDATE crawl_runs
                SET completed_at = ?,
                    discovered_count = ?,
                    successful_count = ?,
                    failed_count = ?,
                    sitemap_complete = ?
                WHERE id = ?
                """,
                (
                    completed_at,
                    discovered_count,
                    successful_count,
                    failed_count,
                    int(sitemap_complete),
                    run_id,
                ),
            )

    def deactivate_missing_articles(
        self,
        run_id: int,
        discovered_urls: set[str],
    ) -> int:
        """Deactivate missing articles only after a complete successful crawl."""
        with self._connect() as connection:
            run = connection.execute(
                """
                SELECT sitemap_complete, discovered_count,
                       successful_count, failed_count, completed_at
                FROM crawl_runs
                WHERE id = ?
                """,
                (run_id,),
            ).fetchone()

            if run is None:
                raise ValueError("Unknown crawl run")

            if (
                not run["completed_at"]
                or not run["sitemap_complete"]
                or run["failed_count"] != 0
                or run["successful_count"] != run["discovered_count"]
                or run["discovered_count"] != len(discovered_urls)
            ):
                raise ValueError(
                    "Cannot deactivate articles after an incomplete crawl"
                )

            rows = connection.execute(
                "SELECT url FROM articles WHERE active = 1"
            ).fetchall()

            missing_urls = [
                row["url"]
                for row in rows
                if row["url"] not in discovered_urls
            ]

            if not missing_urls:
                return 0

            connection.executemany(
                "UPDATE articles SET active = 0 WHERE url = ?",
                [(url,) for url in missing_urls],
            )

            return len(missing_urls)
