
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from app.ingestion.storage import DEFAULT_DB_PATH


STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can",
    "do", "for", "from", "how", "i", "in", "is", "it", "me",
    "of", "on", "or", "please", "the", "this", "to", "what",
    "when", "where", "which", "with", "you", "your",
}


def tokenize(text: str) -> list[str]:
    """Normalize text into searchable words."""
    words = re.findall(r"[a-z0-9]+", text.lower())
    return [word for word in words if word not in STOPWORDS]


def search_articles(
    query: str,
    db_path: str | Path = DEFAULT_DB_PATH,
    top_k: int = 5,
) -> list[dict]:
    """Search active SQLite articles and return ranked sources."""
    if top_k < 1:
        raise ValueError("top_k must be at least 1")

    query_terms = set(tokenize(query))
    if not query_terms:
        return []

    database_path = Path(db_path)
    if not database_path.exists():
        return []

    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT url, title, text
            FROM articles
            WHERE active = 1
            """
        ).fetchall()

    ranked = []

    for row in rows:
        title = row["title"] or ""
        text = row["text"] or ""

        title_terms = set(tokenize(title))
        body_terms = set(tokenize(text))

        title_matches = query_terms & title_terms
        body_matches = query_terms & body_terms

        # Title matches carry more weight than body matches.
        score = (
            3 * len(title_matches) + len(body_matches)
        ) / (4 * len(query_terms))

        if not score:
            continue

        # Prefer articles whose title matches the full query phrase.
        if query.strip() and query.lower().strip() in title.lower():
            score += 0.5

        ranked.append(
            {
                "title": title,
                "url": row["url"],
                "text": text,
                "score": score,
            }
        )

    ranked.sort(
        key=lambda article: (
            article["score"],
            article["title"].lower(),
        ),
        reverse=True,
    )

    results = []
    for index, article in enumerate(ranked[:top_k], start=1):
        results.append(
            {
                "id": f"S{index}",
                **article,
            }
        )

    return results
