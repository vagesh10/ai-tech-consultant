
from __future__ import annotations

import json
import logging
import os
import sqlite3
import tempfile
import uuid
from pathlib import Path

import chromadb

from app.ingestion.storage import DEFAULT_DB_PATH
from app.semantic_search import get_model

VECTOR_DIR = Path("data") / "chroma"
COLLECTION_NAME = "support_articles"
ACTIVE_INDEX_FILE = "active_collection.json"

logger = logging.getLogger(__name__)


def _client(vector_dir: str | Path):
    return chromadb.PersistentClient(path=str(vector_dir))


def _active_collection_name(vector_dir: str | Path) -> str:
    """Read the active collection pointer, falling back to the legacy name."""
    pointer_path = Path(vector_dir) / ACTIVE_INDEX_FILE

    if pointer_path.exists():
        try:
            with pointer_path.open("r", encoding="utf-8") as file:
                data = json.load(file)

            name = data.get("collection_name")
            if isinstance(name, str) and name:
                return name
        except (OSError, json.JSONDecodeError, AttributeError):
            logger.warning(
                "Could not read active index pointer; using legacy collection."
            )

    return COLLECTION_NAME


def get_collection(vector_dir: str | Path = VECTOR_DIR):
    """Get the currently active persistent ChromaDB collection."""
    client = _client(vector_dir)
    name = _active_collection_name(vector_dir)

    return client.get_or_create_collection(
        name=name,
        metadata={"hnsw:space": "cosine"},
    )


def _write_active_pointer(vector_dir: str | Path, collection_name: str) -> None:
    """Atomically switch the active index pointer after a successful build."""
    directory = Path(vector_dir)
    directory.mkdir(parents=True, exist_ok=True)
    pointer_path = directory / ACTIVE_INDEX_FILE
    temporary_path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=directory,
            suffix=".tmp",
            delete=False,
        ) as file:
            json.dump({"collection_name": collection_name}, file)
            file.flush()
            os.fsync(file.fileno())
            temporary_path = Path(file.name)

        os.replace(temporary_path, pointer_path)

    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def rebuild_vector_index(
    db_path: str | Path = DEFAULT_DB_PATH,
    vector_dir: str | Path = VECTOR_DIR,
    batch_size: int = 64,
) -> int:
    """
    Build a new version of the vector index without modifying the active one.

    Switch the active pointer only after every batch has been indexed.
    If building fails, retain the previous active index.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")

    vector_path = Path(vector_dir)
    vector_path.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT url, title, text, images_json, image_text
            FROM articles
            WHERE active = 1
            ORDER BY url
            """
        ).fetchall()

    client = _client(vector_path)
    previous_name = _active_collection_name(vector_path)

    # Build a separate collection so the live index remains available.
    new_name = f"{COLLECTION_NAME}_{uuid.uuid4().hex}"
    collection = client.create_collection(
        name=new_name,
        metadata={"hnsw:space": "cosine"},
    )

    try:
        model = get_model()
        indexed_count = 0

        for start in range(0, len(rows), batch_size):
            batch = rows[start : start + batch_size]
            ids = [row[0] for row in batch]
            documents = []

            for url, title, text, images_json, image_text in batch:
                try:
                    images = json.loads(images_json or "[]")
                except (json.JSONDecodeError, TypeError):
                    images = []

                image_descriptions = [
                    image["alt"].strip()
                    for image in images
                    if isinstance(image, dict)
                    and isinstance(image.get("alt"), str)
                    and image["alt"].strip()
                ]

                document = (
                    f"Title: {title}\n"
                    f"Article content:\n{text[:4000]}"
                )

                if image_descriptions:
                    document += "\n\nImage descriptions:\n"
                    document += "\n".join(image_descriptions)

                if image_text and image_text.strip():
                    document += "\n\nText extracted from screenshots:\n"
                    document += image_text.strip()[:6000]

                documents.append(document)

            embeddings = model.encode(
                documents,
                normalize_embeddings=True,
            ).tolist()

            collection.add(
                ids=ids,
                documents=documents,
                embeddings=embeddings,
                metadatas=[
                    {"url": row[0], "title": row[1]}
                    for row in batch
                ],
            )

            indexed_count += len(batch)

        # Verify the replacement index before making it active.
        actual_count = collection.count()

        if actual_count != len(rows):
            raise RuntimeError(
                f"Index verification failed: expected {len(rows)} vectors, "
                f"found {actual_count}."
            )

        # Atomic pointer switch: searches now use the completed index.
        _write_active_pointer(vector_path, new_name)

        logger.info(
            "Activated vector index %s with %s articles.",
            new_name,
            indexed_count,
        )

    except BaseException:
        # The previous active index and pointer remain untouched.
        try:
            client.delete_collection(name=new_name)
        except Exception:
            logger.exception("Could not remove failed temporary index %s", new_name)
        raise

    # Cleanup is best-effort and happens only after activation.
    # A cleanup failure must not invalidate the newly active index.
    if previous_name != new_name:
        try:
            client.delete_collection(name=previous_name)
        except Exception:
            logger.warning(
                "Could not remove old collection %s; active index is safe.",
                previous_name,
                exc_info=True,
            )

    return indexed_count


def search_vector_index(
    query: str,
    vector_dir: str | Path = VECTOR_DIR,
    top_k: int = 5,
) -> list[dict]:
    """Search the active index by semantic similarity."""
    if top_k < 1:
        raise ValueError("top_k must be at least 1")

    if not query.strip():
        return []

    collection = get_collection(vector_dir)

    count = collection.count()
    if count == 0:
        return []

    query_embedding = get_model().encode(
        query,
        normalize_embeddings=True,
    ).tolist()

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=min(top_k, count),
        include=["documents", "metadatas", "distances"],
    )

    matches = []

    for i, metadata in enumerate(results["metadatas"][0]):
        matches.append(
            {
                "id": f"S{i + 1}",
                "title": metadata["title"],
                "url": metadata["url"],
                "text": results["documents"][0][i],
                "score": 1.0 - results["distances"][0][i],
            }
        )

    return matches
