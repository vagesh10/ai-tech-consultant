
from app.vector_store import search_vector_index, get_collection

print("Indexed vectors:", get_collection().count())
print("\nTop 5 semantic search results:")

results = search_vector_index(
    "How can I collect money from customers?",
    top_k=5,
)

for result in results:
    print(f"Score: {result['score']:.3f}")
    print(f"Title: {result['title']}")
    print(f"URL: {result['url']}")
    print("-" * 60)
