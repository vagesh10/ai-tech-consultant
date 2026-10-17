
from app.ingestion.parser import parse_article
from app.ingestion.storage import ArticleStore


def test_parse_article_extracts_content_and_images():
    html = """
    <html>
      <head>
        <title>Fallback title</title>
        <link rel="canonical" href="/support/article-1">
      </head>
      <body>
        <nav>Navigation text</nav>
        <main>
          <h1>Configure Payments</h1>
          <p>Open the payment settings page.</p>
          <img src="/images/settings.png" alt="Payment settings">
        </main>
        <footer>Footer text</footer>
      </body>
    </html>
    """

    article = parse_article(
        html,
        "https://support.brilliantdirectories.com/support/article-1",
    )

    assert article.title == "Configure Payments"
    assert "payment settings page" in article.text
    assert "Navigation text" not in article.text
    assert "Footer text" not in article.text

    assert article.images == [
        {
            "url": "https://support.brilliantdirectories.com/images/settings.png",
            "alt": "Payment settings",
        }
    ]

    assert len(article.content_hash) == 64


def test_identical_content_has_same_hash():
    html = """
    <html>
      <body>
        <main>
          <h1>Help</h1>
          <p>Example content</p>
        </main>
      </body>
    </html>
    """

    first = parse_article(html, "https://example.com/help")
    second = parse_article(html, "https://example.com/help")

    assert first.content_hash == second.content_hash


def test_storage_detects_new_and_unchanged_articles(tmp_path):
    store = ArticleStore(tmp_path / "test.db")

    html = """
    <html>
      <body>
        <main>
          <h1>Help</h1>
          <p>Example content</p>
        </main>
      </body>
    </html>
    """

    article = parse_article(html, "https://example.com/help")

    assert store.save_article(article) == "new"
    assert store.save_article(article) == "unchanged"
    assert store.count_articles() == 1

    stored = store.get_article(article.url)

    assert stored is not None
    assert stored["title"] == "Help"


def test_storage_detects_changed_content(tmp_path):
    store = ArticleStore(tmp_path / "test.db")

    first = parse_article(
        "<main><h1>Help</h1><p>Old content</p></main>",
        "https://example.com/help",
    )

    second = parse_article(
        "<main><h1>Help</h1><p>Updated content</p></main>",
        "https://example.com/help",
    )

    assert store.save_article(first) == "new"
    assert store.save_article(second) == "changed"
    assert store.count_articles() == 1

    stored = store.get_article(second.url)

    assert stored is not None
    assert "Updated content" in stored["text"]


def test_storage_keeps_different_articles_separate(tmp_path):
    store = ArticleStore(tmp_path / "test.db")

    first = parse_article(
        "<main><h1>Payments</h1><p>Payment guide</p></main>",
        "https://example.com/payments",
    )

    second = parse_article(
        "<main><h1>Profiles</h1><p>Profile guide</p></main>",
        "https://example.com/profiles",
    )

    assert store.save_article(first) == "new"
    assert store.save_article(second) == "new"
    assert store.count_articles() == 2

    assert store.get_article(first.url)["title"] == "Payments"
    assert store.get_article(second.url)["title"] == "Profiles"
    
import pytest

from app.ingestion.crawler import Crawler


def test_crawler_rejects_external_domains(tmp_path):
    store = ArticleStore(tmp_path / "crawler.db")
    crawler = Crawler(store, delay_seconds=0)

    assert crawler._is_allowed_domain(
        "https://support.brilliantdirectories.com/support/home"
    )

    assert not crawler._is_allowed_domain(
        "https://example.com/support/home"
    )

    assert not crawler._is_allowed_domain(
        "http://support.brilliantdirectories.com/support/home"
    )


def test_crawler_rejects_invalid_configuration(tmp_path):
    store = ArticleStore(tmp_path / "crawler.db")

    with pytest.raises(ValueError, match="max_concurrency"):
        Crawler(store, max_concurrency=0)

    with pytest.raises(ValueError, match="delay_seconds"):
        Crawler(store, delay_seconds=-1)

    with pytest.raises(ValueError, match="max_retries"):
        Crawler(store, max_retries=0)


def test_crawler_rejects_invalid_limit(tmp_path):
    store = ArticleStore(tmp_path / "crawler.db")
    crawler = Crawler(store, delay_seconds=0)

    with pytest.raises(ValueError, match="limit must be positive"):
        import asyncio
        asyncio.run(crawler.run(limit=0))

def test_partial_crawl_cannot_deactivate_articles(tmp_path):
    import pytest

    from app.ingestion.parser import parse_article

    store = ArticleStore(tmp_path / "sync.db")

    article = parse_article(
        "<main><h1>Existing</h1><p>Keep this article</p></main>",
        "https://support.brilliantdirectories.com/support/existing",
    )
    store.save_article(article)

    run_id = store.start_crawl()
    store.finish_crawl(
        run_id=run_id,
        discovered_count=10,
        successful_count=5,
        failed_count=0,
        sitemap_complete=True,
    )

    with pytest.raises(ValueError, match="incomplete crawl"):
        store.deactivate_missing_articles(
            run_id,
            {
                "https://support.brilliantdirectories.com/support/other"
            },
        )

    assert store.get_article(article.url) is not None

def test_complete_crawl_deactivates_missing_articles(tmp_path):
    from app.ingestion.parser import parse_article

    store = ArticleStore(tmp_path / "sync.db")

    existing = parse_article(
        "<main><h1>Old article</h1><p>Old content</p></main>",
        "https://support.brilliantdirectories.com/support/old",
    )
    current = parse_article(
        "<main><h1>Current article</h1><p>Current content</p></main>",
        "https://support.brilliantdirectories.com/support/current",
    )

    store.save_article(existing)
    store.save_article(current)

    # A complete crawl discovers and successfully processes only
    # the current article.
    run_id = store.start_crawl()
    store.finish_crawl(
        run_id=run_id,
        discovered_count=1,
        successful_count=1,
        failed_count=0,
        sitemap_complete=True,
    )

    deactivated = store.deactivate_missing_articles(
        run_id,
        {current.url},
    )

    assert deactivated == 1
    assert store.get_article(existing.url) is None
    assert store.get_article(current.url) is not None
    assert store.count_articles() == 1



def test_storage_preserves_article_images(tmp_path):
    store = ArticleStore(tmp_path / "images.db")

    html = """
    <html>
      <body>
        <main>
          <h1>Configure Payments</h1>
          <p>Open payment settings.</p>
          <img src="/images/payment-settings.png"
               alt="Payment settings screen">
        </main>
      </body>
    </html>
    """

    article = parse_article(
        html,
        "https://support.brilliantdirectories.com/support/payments",
    )

    store.save_article(article)
    stored = store.get_article(article.url)

    assert stored is not None
    assert stored["images"] == [
        {
            "url": (
                "https://support.brilliantdirectories.com/"
                "images/payment-settings.png"
            ),
            "alt": "Payment settings screen",
        }
    ]


