
from types import SimpleNamespace

from app.answering import ABSTENTION_TEXT, answer_question
from app.ingestion.parser import parse_article
from app.ingestion.storage import ArticleStore
from app.retrieval import search_articles


class FakeMessages:
    def __init__(self, answer):
        self.answer = answer
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=self.answer)]
        )


class FakeClaudeClient:
    def __init__(self, answer):
        self.messages = FakeMessages(answer)


def create_test_database(tmp_path):
    store = ArticleStore(tmp_path / "knowledge.db")

    article = parse_article(
        """
        <html>
          <body>
            <main>
              <h1>Configure Payments</h1>
              <p>Open payment settings to configure payment options.</p>
            </main>
          </body>
        </html>
        """,
        "https://support.brilliantdirectories.com/support/payments",
    )

    store.save_article(article)
    return store.db_path, article


def test_retrieval_returns_relevant_article(tmp_path):
    db_path, article = create_test_database(tmp_path)

    results = search_articles(
        "configure payment settings",
        db_path=db_path,
    )

    assert len(results) == 1
    assert results[0]["id"] == "S1"
    assert results[0]["url"] == article.url
    assert results[0]["score"] > 0


def test_retrieval_returns_no_results_for_unrelated_query(tmp_path):
    db_path, _ = create_test_database(tmp_path)

    results = search_articles(
        "quantum spacecraft engine",
        db_path=db_path,
    )

    assert results == []


def test_answer_includes_valid_citation(tmp_path):
    db_path, article = create_test_database(tmp_path)
    client = FakeClaudeClient(
        "Open payment settings to configure payment options [S1]."
    )

    result = answer_question(
        "How do I configure payment settings?",
        client=client,
        db_path=db_path,
    )

    assert result["abstained"] is False
    assert "[S1]" in result["answer"]
    assert result["sources"] == [
        {
            "id": "S1",
            "title": "Configure Payments",
            "url": article.url,
        }
    ]
    assert client.messages.calls == 1


def test_answer_with_invalid_citation_abstains(tmp_path):
    db_path, _ = create_test_database(tmp_path)
    client = FakeClaudeClient("Change account settings [S99].")

    result = answer_question(
        "How do I configure payment settings?",
        client=client,
        db_path=db_path,
    )

    assert result["abstained"] is True
    assert result["answer"] == ABSTENTION_TEXT
    assert result["sources"] == []


def test_no_retrieved_evidence_does_not_call_claude(tmp_path):
    db_path, _ = create_test_database(tmp_path)
    client = FakeClaudeClient("This should never be returned.")

    result = answer_question(
        "quantum spacecraft engine",
        client=client,
        db_path=db_path,
    )

    assert result["abstained"] is True
    assert result["sources"] == []
    assert client.messages.calls == 0


def test_model_abstention_is_preserved(tmp_path):
    db_path, _ = create_test_database(tmp_path)
    client = FakeClaudeClient(
        "There is not enough information in the provided sources."
    )

    result = answer_question(
        "How do I configure payment settings?",
        client=client,
        db_path=db_path,
    )

    assert result["abstained"] is True
    assert result["sources"] == []
    assert client.messages.calls == 1
