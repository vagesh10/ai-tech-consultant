
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from urllib.parse import urljoin

from bs4 import BeautifulSoup


@dataclass
class Article:
    url: str
    title: str
    text: str
    images: list[dict[str, str]]
    content_hash: str
    fetched_at: str


def parse_article(html: str, page_url: str) -> Article:
    """Extract readable article content and its associated images."""
    soup = BeautifulSoup(html, "lxml")

    canonical = soup.find("link", rel="canonical")
    canonical_url = (
        urljoin(page_url, canonical["href"])
        if canonical and canonical.get("href")
        else page_url
    )

    title_tag = soup.find("h1") or soup.find("title")
    title = title_tag.get_text(" ", strip=True) if title_tag else ""

    # Remove common non-content elements before extracting article text.
    for element in soup.select(
        "script, style, noscript, nav, footer, header, "
        "aside, form, button"
    ):
        element.decompose()

    content = (
        soup.select_one("article")
        or soup.select_one('[role="main"]')
        or soup.select_one("main")
        or soup.body
        or soup
    )

    text = content.get_text(" ", strip=True)

    images: list[dict[str, str]] = []

    for image in content.find_all("img"):
        src = (
            image.get("src")
            or image.get("data-src")
            or image.get("data-original")
        )

        if not src:
            continue

        images.append(
            {
                "url": urljoin(canonical_url, src),
                "alt": image.get("alt", "").strip(),
            }
        )

    # Hash extracted content so future crawls can detect changes.
    normalized = f"{title}\n{text}\n{images}"
    content_hash = sha256(normalized.encode("utf-8")).hexdigest()

    return Article(
        url=canonical_url,
        title=title,
        text=text,
        images=images,
        content_hash=content_hash,
        fetched_at=datetime.now(timezone.utc).isoformat(),
    )
