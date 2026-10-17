
from __future__ import annotations

import asyncio
import random
import xml.etree.ElementTree as ET
from urllib.parse import urldefrag, urlparse

import httpx

SITEMAP_URL = (
    "https://support.brilliantdirectories.com/support/sitemap.xml"
)

USER_AGENT = "BusinessLabsKnowledgeBrain/1.0 (educational project)"
ALLOWED_HOSTS = {"support.brilliantdirectories.com"}


def normalize_url(url: str) -> str:
    """Remove fragments and surrounding whitespace."""
    return urldefrag(url.strip())[0]


def is_allowed_url(url: str) -> bool:
    """Allow HTTPS URLs only on the approved support host."""
    parsed = urlparse(url)

    return (
        parsed.scheme == "https"
        and parsed.hostname in ALLOWED_HOSTS
        and parsed.username is None
        and parsed.password is None
    )


async def fetch_sitemap(
    client: httpx.AsyncClient,
    url: str,
    max_retries: int = 3,
    delay_seconds: float = 1.0,
) -> httpx.Response:
    """Fetch a sitemap with retry handling and basic throttling."""
    if not is_allowed_url(url):
        raise ValueError(f"URL is outside the allowed domain: {url}")

    if max_retries < 1:
        raise ValueError("max_retries must be at least 1")

    if delay_seconds < 0:
        raise ValueError("delay_seconds cannot be negative")

    for attempt in range(max_retries):
        if delay_seconds:
            await asyncio.sleep(delay_seconds)

        try:
            response = await client.get(url)

            if response.status_code == 429 or response.status_code >= 500:
                if attempt == max_retries - 1:
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

            # Check the final URL in case redirects were enabled
            # by a caller-provided HTTP client.
            if not is_allowed_url(str(response.url)):
                raise ValueError(
                    f"Sitemap redirected outside the allowed domain: "
                    f"{response.url}"
                )

            return response

        except (httpx.TimeoutException, httpx.TransportError):
            if attempt == max_retries - 1:
                raise

            await asyncio.sleep(2**attempt + random.random())

    raise RuntimeError(f"Failed to fetch sitemap: {url}")


async def discover_sitemap_urls(
    client: httpx.AsyncClient,
    sitemap_url: str = SITEMAP_URL,
    max_sitemaps: int = 100,
    delay_seconds: float = 1.0,
) -> list[str]:
    """Discover unique, approved page URLs from a sitemap tree."""
    if max_sitemaps < 1:
        raise ValueError("max_sitemaps must be at least 1")

    if not is_allowed_url(sitemap_url):
        raise ValueError(
            f"Sitemap URL is outside the allowed domain: {sitemap_url}"
        )

    pending = [normalize_url(sitemap_url)]
    visited_sitemaps: set[str] = set()
    page_urls: set[str] = set()

    while pending:
        current = pending.pop(0)

        if current in visited_sitemaps:
            continue

        if len(visited_sitemaps) >= max_sitemaps:
            raise ValueError("Maximum sitemap limit reached")

        if not is_allowed_url(current):
            raise ValueError(
                f"Nested sitemap URL is outside the allowed domain: "
                f"{current}"
            )

        visited_sitemaps.add(current)

        response = await fetch_sitemap(
            client,
            current,
            delay_seconds=delay_seconds,
        )

        try:
            root = ET.fromstring(response.content)
        except ET.ParseError as exc:
            raise ValueError(
                f"Invalid sitemap XML at {current}"
            ) from exc

        root_type = root.tag.rsplit("}", 1)[-1]

        if root_type not in {"urlset", "sitemapindex"}:
            raise ValueError(
                f"Unexpected sitemap root: {root_type}"
            )

        for element in root:
            element_type = element.tag.rsplit("}", 1)[-1]

            loc = next(
                (
                    child.text.strip()
                    for child in element
                    if child.tag.rsplit("}", 1)[-1] == "loc"
                    and child.text
                    and child.text.strip()
                ),
                None,
            )

            if not loc:
                continue

            loc = normalize_url(loc)

            if not is_allowed_url(loc):
                raise ValueError(
                    f"Sitemap contains a URL outside the allowed domain: "
                    f"{loc}"
                )

            if element_type == "sitemap":
                if loc not in visited_sitemaps and loc not in pending:
                    pending.append(loc)

            elif element_type == "url":
                page_urls.add(loc)

    return sorted(page_urls)


async def main() -> None:
    limits = httpx.Limits(
        max_connections=1,
        max_keepalive_connections=1,
    )

    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        limits=limits,
        timeout=httpx.Timeout(20.0),
        follow_redirects=False,
    ) as client:
        urls = await discover_sitemap_urls(client)

    print(f"Discovered {len(urls)} unique page URLs.")
    for url in urls[:10]:
        print(url)


if __name__ == "__main__":
    asyncio.run(main())
