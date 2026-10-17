
from __future__ import annotations

import asyncio
import logging
import random
import time
from collections import Counter
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from app.ingestion.parser import parse_article
from app.ingestion.sitemap import SITEMAP_URL, discover_sitemap_urls
from app.ingestion.storage import ArticleStore

logger = logging.getLogger(__name__)

USER_AGENT = "BusinessLabsKnowledgeBrain/1.0 (educational project)"
ALLOWED_HOSTS = {"support.brilliantdirectories.com"}


class Crawler:
    def __init__(
        self,
        store: ArticleStore,
        max_concurrency: int = 2,
        delay_seconds: float = 1.0,
        max_retries: int = 3,
    ) -> None:
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be at least 1")
        if delay_seconds < 0:
            raise ValueError("delay_seconds cannot be negative")
        if max_retries < 1:
            raise ValueError("max_retries must be at least 1")

        self.store = store
        self.max_concurrency = max_concurrency
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.delay_seconds = delay_seconds
        self.max_retries = max_retries

        self.robots_cache: dict[str, RobotFileParser] = {}
        self._robots_lock = asyncio.Lock()

        # Track request start times separately for each host.
        self._host_locks: dict[str, asyncio.Lock] = {}
        self._last_request_at: dict[str, float] = {}

    @staticmethod
    def _is_allowed_domain(url: str) -> bool:
        parsed = urlparse(url)

        return (
            parsed.scheme == "https"
            and parsed.hostname in ALLOWED_HOSTS
            and parsed.username is None
            and parsed.password is None
        )

    async def _wait_for_host(self, url: str) -> None:
        host = urlparse(url).netloc
        lock = self._host_locks.setdefault(host, asyncio.Lock())

        async with lock:
            loop = asyncio.get_running_loop()
            now = loop.time()
            last_request = self._last_request_at.get(host)

            if last_request is not None:
                remaining = self.delay_seconds - (now - last_request)
                if remaining > 0:
                    await asyncio.sleep(remaining)

            self._last_request_at[host] = loop.time()

    async def _fetch(
        self,
        client: httpx.AsyncClient,
        url: str,
    ) -> httpx.Response:
        if not self._is_allowed_domain(url):
            raise ValueError(f"URL is outside the allowed domain: {url}")

        for attempt in range(self.max_retries):
            try:
                await self._wait_for_host(url)
                response = await client.get(url)

                if response.status_code == 429 or response.status_code >= 500:
                    if attempt == self.max_retries - 1:
                        response.raise_for_status()

                    retry_after = response.headers.get("Retry-After")
                    try:
                        wait_seconds = (
                            float(retry_after) if retry_after else 0.0
                        )
                    except ValueError:
                        wait_seconds = 0.0

                    await asyncio.sleep(
                        max(wait_seconds, 2**attempt + random.random())
                    )
                    continue

                response.raise_for_status()
                return response

            except (httpx.TimeoutException, httpx.TransportError):
                if attempt == self.max_retries - 1:
                    raise

                await asyncio.sleep(2**attempt + random.random())

        raise RuntimeError(f"Failed to fetch URL: {url}")

    async def _allowed(
        self,
        client: httpx.AsyncClient,
        url: str,
    ) -> bool:
        if not self._is_allowed_domain(url):
            logger.warning("Skipping URL outside allowed domain: %s", url)
            return False

        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"

        async with self._robots_lock:
            if origin not in self.robots_cache:
                robots_url = f"{origin}/robots.txt"
                parser = RobotFileParser()
                parser.set_url(robots_url)

                try:
                    response = await self._fetch(client, robots_url)
                    parser.parse(response.text.splitlines())

                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code == 404:
                        # No robots.txt file means no published rules.
                        parser.parse([])
                    else:
                        logger.warning(
                            "Could not read robots.txt (%s); skipping URL",
                            exc.response.status_code,
                        )
                        return False

                except (httpx.HTTPError, RuntimeError, ValueError):
                    logger.warning(
                        "Could not retrieve robots.txt; skipping URL"
                    )
                    return False

                self.robots_cache[origin] = parser

            robots = self.robots_cache[origin]

        return robots.can_fetch(USER_AGENT, url)

    async def _process_one(
        self,
        client: httpx.AsyncClient,
        url: str,
    ) -> str:
        async with self.semaphore:
            try:
                if not await self._allowed(client, url):
                    logger.info("Skipped by domain or robots rules: %s", url)
                    return "skipped"

                response = await self._fetch(client, url)
                article = parse_article(response.text, url)

                if not article.title.strip() or not article.text.strip():
                    logger.warning("No usable article content: %s", url)
                    return "failed"

                # Do not store a canonical URL pointing to another domain.
                if not self._is_allowed_domain(article.url):
                    logger.warning(
                        "Skipping article with external canonical URL: %s",
                        article.url,
                    )
                    return "skipped"

                status = self.store.save_article(article)
                logger.info("Processed %s: %s", article.url, status)
                return status

            except (httpx.HTTPError, ValueError, RuntimeError):
                logger.exception("Failed to process %s", url)
                return "failed"

    
    async def run(
        self,
        limit: int | None = 10,
        sitemap_url: str = SITEMAP_URL,
    ) -> Counter:
        if limit is not None and limit < 1:
            raise ValueError("limit must be positive or None")

        if not self._is_allowed_domain(sitemap_url):
            raise ValueError("Sitemap URL is outside the allowed domain")

        run_id = self.store.start_crawl()
        urls: list[str] = []

        try:
            limits = httpx.Limits(
                max_connections=self.max_concurrency,
                max_keepalive_connections=self.max_concurrency,
            )

            async with httpx.AsyncClient(
                headers={"User-Agent": USER_AGENT},
                limits=limits,
                timeout=httpx.Timeout(20.0),
                follow_redirects=False,
            ) as client:
                try:
                    discovered_urls = await discover_sitemap_urls(
                        client, sitemap_url
                    )
                except Exception:
                    self.store.finish_crawl(
                        run_id=run_id,
                        discovered_count=0,
                        successful_count=0,
                        failed_count=1,
                        sitemap_complete=False,
                    )
                    raise

                urls = sorted(
                    url
                    for url in discovered_urls
                    if self._is_allowed_domain(url)
                )

                selected_urls = (
                    urls if limit is None else urls[:limit]
                )

                results = await asyncio.gather(
                    *(
                        self._process_one(client, url)
                        for url in selected_urls
                    ),
                    return_exceptions=True,
                )

            summary: Counter = Counter()
            successful_count = 0
            failed_count = 0

            for result in results:
                if isinstance(result, asyncio.CancelledError):
                    raise result

                if isinstance(result, BaseException):
                    logger.error("Unexpected crawler error: %s", result)
                    summary["failed"] += 1
                    failed_count += 1
                elif result in {"new", "changed", "unchanged"}:
                    summary[result] += 1
                    successful_count += 1
                elif result == "skipped":
                    summary["skipped"] += 1
                    failed_count += 1
                else:
                    summary["failed"] += 1
                    failed_count += 1

            self.store.finish_crawl(
                run_id=run_id,
                discovered_count=len(urls),
                successful_count=successful_count,
                failed_count=failed_count,
                sitemap_complete=True,
            )

            # Deletion detection is allowed only for a complete,
            # successful crawl of every discovered URL.
            if (
                limit is None
                and failed_count == 0
                and successful_count == len(urls)
            ):
                deactivated = self.store.deactivate_missing_articles(
                    run_id=run_id,
                    discovered_urls=set(urls),
                )
                summary["deactivated"] = deactivated
            else:
                summary["deactivated"] = 0

            summary["discovered"] = len(urls)
            summary["attempted"] = len(selected_urls)
            summary["stored"] = self.store.count_articles()

            return summary

        except BaseException:
            # Record an interrupted run as incomplete when possible.
            # Never run deletion detection from this error path.
            try:
                self.store.finish_crawl(
                    run_id=run_id,
                    discovered_count=len(urls),
                    successful_count=0,
                    failed_count=1,
                    sitemap_complete=False,
                )
            except Exception:
                logger.exception("Could not record failed crawl run")
            raise
