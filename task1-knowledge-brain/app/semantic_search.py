
from __future__ import annotations

import numpy as np
from sentence_transformers import SentenceTransformer

from app.ingestion.storage import DEFAULT_DB_PATH
from app.retrieval import search_articles

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

_model = None


def get_model():
    """Load the embedding model once per process."""
    global _model

    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)

    return _model


def semantic_search(
    query: str,
    db_path=DEFAULT_DB_PATH,
    top_k: int = 5,
) -> list[dict]:
    if not query.strip():
        return []

    if top_k < 1:
        raise ValueError("top_k must be at least 1")

    # Retrieve a broad candidate set from the existing SQLite search.
    candidates = search_articles(
        query,
        db_path=db_path,
        top_k=100,
    )

    if not candidates:
        return []

    model = get_model()

    query_vector = model.encode(
        query,
        normalize_embeddings=True,
    )

    article_texts = [
        f"{article['title']}\n{article['text'][:4000]}"
        for article in candidates
    ]

    article_vectors = model.encode(
        article_texts,
        normalize_embeddings=True,
    )

    scores = np.dot(article_vectors, query_vector)

    ranked = []
    for article, score in zip(candidates, scores):
        ranked.append({
            **article,
            "score": float(score),
        })

    ranked.sort(
        key=lambda article: article["score"],
        reverse=True,
    )

    return [
        {"id": f"S{i}", **article}
        for i, article in enumerate(ranked[:top_k], start=1)
    ]
