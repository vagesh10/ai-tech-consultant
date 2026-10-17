
import argparse
import asyncio
import logging

from app.ingestion.crawler import Crawler
from app.ingestion.storage import ArticleStore


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest the Brilliant Directories help center."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum number of article URLs to process; use -1 for all.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Delay before fetching each article, in seconds.",
    )
    args = parser.parse_args()

    if args.limit == 0 or args.limit < -1:
        parser.error("--limit must be positive or -1")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    store = ArticleStore()
    crawler = Crawler(store, delay_seconds=args.delay)

    summary = asyncio.run(
        crawler.run(limit=None if args.limit == -1 else args.limit)
    )

    print("\nCrawl summary")
    for key, value in sorted(summary.items()):
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
