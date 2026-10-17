
from __future__ import annotations

import asyncio
import logging
from io import BytesIO
from urllib.parse import urlparse

import httpx
import pytesseract
from PIL import Image, UnidentifiedImageError

from app.ingestion.storage import ArticleStore, DEFAULT_DB_PATH

TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

MAX_IMAGES_PER_ARTICLE = 10
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_ARTICLES_PER_RUN = 5

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH


def is_useful_image(url: str) -> bool:
    """Skip known decorative or repeated images."""
    parsed = urlparse(url)
    path = parsed.path.lower()

    # Known generic banner repeated across folder pages.
    if path.endswith("/marketplacebannertest6.jpg"):
        return False

    return parsed.scheme == "https" and bool(parsed.hostname)


def extract_text(image_bytes: bytes) -> str:
    """Extract readable English text from an image."""
    with Image.open(BytesIO(image_bytes)) as source:
        image = source.convert("RGB")

    return pytesseract.image_to_string(
        image,
        lang="eng",
    ).strip()


async def download_image(
    client: httpx.AsyncClient,
    url: str,
) -> bytes | None:
    """Download an image over HTTPS with a size limit."""
    if not is_useful_image(url):
        logger.info("Skipping excluded image: %s", url)
        return None

    try:
        async with client.stream("GET", url) as response:
            response.raise_for_status()

            content_type = response.headers.get(
                "content-type", ""
            ).lower()

            if not content_type.startswith("image/"):
                logger.warning("Skipping non-image response: %s", url)
                return None

            data = bytearray()

            async for chunk in response.aiter_bytes():
                data.extend(chunk)

                if len(data) > MAX_IMAGE_BYTES:
                    logger.warning("Image exceeds 10 MB: %s", url)
                    return None

            return bytes(data)

    except httpx.HTTPError as exc:
        logger.warning("Download failed for %s: %s", url, exc)
        return None


async def process_article(
    client: httpx.AsyncClient,
    store: ArticleStore,
    article: dict,
) -> bool:
    """OCR useful article images and save the extracted text."""
    extracted_parts: list[str] = []
    seen_urls: set[str] = set()

    useful_images = []

    for image_info in article["images"]:
        image_url = image_info.get("url", "").strip()

        if not image_url or not is_useful_image(image_url):
            continue

        # Avoid downloading the same URL more than once per article.
        if image_url in seen_urls:
            continue

        seen_urls.add(image_url)
        useful_images.append(image_info)

    for index, image_info in enumerate(
        useful_images[:MAX_IMAGES_PER_ARTICLE],
        start=1,
    ):
        image_url = image_info.get("url", "")
        image_bytes = await download_image(client, image_url)

        if image_bytes is None:
            continue

        try:
            text = await asyncio.to_thread(
                extract_text,
                image_bytes,
            )
        except (
            OSError,
            ValueError,
            UnidentifiedImageError,
            pytesseract.TesseractError,
        ) as exc:
            logger.warning("OCR failed for %s: %s", image_url, exc)
            continue

        if text:
            extracted_parts.append(
                f"Image {index}\n"
                f"URL: {image_url}\n"
                f"{text}"
            )

    if not extracted_parts:
        logger.info("No OCR text found: %s", article["title"])
        return False

    image_text = "\n\n".join(extracted_parts)

    saved = store.save_image_text(
        article["url"],
        image_text,
    )

    if saved:
        logger.info(
            "Saved OCR text for %s (%s characters)",
            article["title"],
            len(image_text),
        )
    else:
        logger.warning(
            "Could not save OCR text; article may be inactive: %s",
            article["url"],
        )

    return saved


async def main() -> None:
    store = ArticleStore(DEFAULT_DB_PATH)

    try:
        candidates = store.get_articles_needing_ocr()

        # Ignore articles that contain only excluded images.
        articles = [
            article
            for article in candidates
            if any(
                is_useful_image(image.get("url", ""))
                for image in article["images"]
            )
        ][:MAX_ARTICLES_PER_RUN]

        if not articles:
            logger.info("No eligible articles currently need OCR.")
            return

        logger.info("Processing %s articles.", len(articles))

        headers = {
            "User-Agent": (
                "BusinessLabsKnowledgeBrain/1.0 "
                "(educational project)"
            )
        }

        async with httpx.AsyncClient(
            headers=headers,
            timeout=httpx.Timeout(20.0),
            follow_redirects=True,
        ) as client:
            for article in articles:
                await process_article(client, store, article)

        logger.info("OCR batch completed.")

    finally:
        close = getattr(store, "close", None)
        if callable(close):
            close()


if __name__ == "__main__":
    asyncio.run(main())
