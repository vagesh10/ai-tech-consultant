
from app.ingestion.parser import parse_article
from app.ingestion.storage import ArticleStore
from app.semantic_search import semantic_search


def test_semantic_search_returns_ranked_articles(tmp_path, monkeypatch):
    db_path = tmp_path / "semantic.db"
    store = ArticleStore(db_path)

    article = parse_article(
        """
        <html><body><main>
        <h1>Configure Payments</h1>
        <p>Open payment settings to configure payment options.</p>
        </main></body></html>
        """,
        "https://support.brilliantdirectories.com/support/payments",
    )
    store.save_article(article)

    class FakeModel:
        def encode(self, texts, normalize_embeddings=True):
            import numpy as np

            if isinstance(texts, str):
                return np.array([1.0, 0.0])

            return np.array([[1.0, 0.0] for _ in texts])

    monkeypatch.setattr(
        "app.semantic_search.get_model",
        lambda: FakeModel(),
    )

    results = semantic_search(
        "How do I set up payments?",
        db_path=db_path,
    )

    assert len(results) == 1
    assert results[0]["url"] == article.url
    assert results[0]["score"] > 0
