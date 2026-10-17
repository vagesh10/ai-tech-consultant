
from __future__ import annotations

import asyncio
import logging

from app.ingestion.crawler import Crawler
from app.ingestion.storage import ArticleStore, DEFAULT_DB_PATH
from app.scripts.build_vector_index import rebuild_vector_index

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


async def main() -> None:
    store = ArticleStore(DEFAULT_DB_PATH)
    crawler = Crawler(
        store=store,
        max_concurrency=2,
        delay_seconds=1.0,
        max_retries=3,
    )

    try:
        summary = await crawler.run(limit=None)
        logger.info("Daily crawl summary: %s", dict(summary))

        # Do not rebuild the index if any URLs failed or were skipped.
        failed = summary.get("failed", 0) + summary.get("skipped", 0)

        if failed:
            logger.error(
                "Sync had %s failed/skipped URLs. "
                "Keeping the existing vector index.",
                failed,
            )
            raise RuntimeError("Daily synchronization was incomplete")

        indexed = rebuild_vector_index(db_path=DEFAULT_DB_PATH)
        logger.info("Daily synchronization completed. Indexed %s articles.", indexed)

    finally:
        close = getattr(store, "close", None)
        if callable(close):
            close()


if __name__ == "__main__":
    asyncio.run(main())
