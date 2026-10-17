
import json
import sqlite3
from io import BytesIO
from urllib.parse import urlparse

import httpx
import pytesseract
from PIL import Image, UnidentifiedImageError

pytesseract.pytesseract.tesseract_cmd = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)

DB_PATH = "data/knowledge.db"
ARTICLE_TITLE = '"Publish Date" Functionality For The  Admin Blog'
MAX_IMAGES = 5
MAX_IMAGE_BYTES = 10 * 1024 * 1024

with sqlite3.connect(DB_PATH) as connection:
    row = connection.execute(
        """
        SELECT title, url, images_json
        FROM articles
        WHERE active = 1 AND title = ?
        LIMIT 1
        """,
        (ARTICLE_TITLE,),
    ).fetchone()

if row is None:
    raise SystemExit("Target article not found in the database.")

title, article_url, images_json = row
images = json.loads(images_json or "[]")

print(f"Article: {title}")
print(f"Article URL: {article_url}")
print(f"Images found: {len(images)}")

headers = {"User-Agent": "KnowledgeBrainOCR/1.0"}

with httpx.Client(
    timeout=20.0,
    follow_redirects=True,
    headers=headers,
) as client:
    for index, image_info in enumerate(images[:MAX_IMAGES], start=1):
        image_url = image_info.get("url", "")

        # Avoid unexpected non-HTTP URLs.
        if urlparse(image_url).scheme != "https":
            print(f"\nImage {index}: skipped (not HTTPS)")
            continue

        print(f"\n--- Image {index} ---")
        print("URL:", image_url)

        try:
            with client.stream("GET", image_url) as response:
                response.raise_for_status()

                content_type = response.headers.get(
                    "content-type", ""
                ).lower()

                if not content_type.startswith("image/"):
                    print("Skipped: response is not an image.")
                    continue

                image_bytes = bytearray()

                for chunk in response.iter_bytes():
                    image_bytes.extend(chunk)

                    if len(image_bytes) > MAX_IMAGE_BYTES:
                        raise ValueError("Image exceeds 10 MB limit.")

            with Image.open(BytesIO(image_bytes)) as source:
                source.verify()

            with Image.open(BytesIO(image_bytes)) as source:
                image = source.convert("RGB")

            extracted_text = pytesseract.image_to_string(
                image,
                lang="eng",
            ).strip()

            print("Extracted text:")
            print(extracted_text or "[No readable text detected]")

        except (
            httpx.HTTPError,
            OSError,
            ValueError,
            UnidentifiedImageError,
            pytesseract.TesseractError,
        ) as error:
            print(f"Image processing failed: {error}")
