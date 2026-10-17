
import json
import sqlite3

connection = sqlite3.connect("data/knowledge.db")

rows = connection.execute(
    """
    SELECT title, url, images_json
    FROM articles
    WHERE active = 1
    ORDER BY title
    """
).fetchall()

connection.close()

shown = 0

for title, article_url, images_json in rows:
    for image in json.loads(images_json or "[]"):
        if not image.get("alt", "").strip():
            print(f"Article: {title}")
            print(f"Article URL: {article_url}")
            print(f"Image URL: {image.get('url', '')}")
            print("-" * 60)

            shown += 1
            if shown >= 15:
                break

    if shown >= 15:
        break

print(f"Displayed {shown} images without alt text.")
