
import json
import sqlite3

connection = sqlite3.connect("data/knowledge.db")

rows = connection.execute(
    """
    SELECT images_json
    FROM articles
    WHERE active = 1
    """
).fetchall()

connection.close()

image_count = 0
with_alt = 0
without_alt = 0
articles_with_images = 0

for (images_json,) in rows:
    images = json.loads(images_json or "[]")

    if images:
        articles_with_images += 1

    for image in images:
        image_count += 1

        if image.get("alt", "").strip():
            with_alt += 1
        else:
            without_alt += 1

print("Active articles:", len(rows))
print("Articles with images:", articles_with_images)
print("Total images:", image_count)
print("Images with alt text:", with_alt)
print("Images without alt text:", without_alt)
