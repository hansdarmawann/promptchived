from types import SimpleNamespace

from promptchived.services import search as search_service
from promptchived.services.search import _rrf


def row(message_id: str) -> dict:
    return {"message_id": message_id, "snippet": message_id, "score": 0.5}


def test_rrf_rewards_results_present_in_both_rankings():
    lexical = [row("both"), row("lexical")]
    semantic = [row("semantic"), row("both")]
    ranked = _rrf(lexical, semantic, k=60)
    assert ranked[0]["message_id"] == "both"
    assert len(ranked) == 3


def test_hybrid_search_falls_back_to_keywords_when_embedding_load_fails(monkeypatch):
    keyword = row("keyword")
    monkeypatch.setattr(
        search_service,
        "get_settings",
        lambda: SimpleNamespace(search_candidates=100, rrf_k=60),
    )
    monkeypatch.setattr(search_service, "embedding_coverage", lambda session: 1.0)
    monkeypatch.setattr(
        search_service, "fulltext_candidates", lambda session, parameters, limit: [keyword]
    )

    class BrokenEmbeddingService:
        def encode_query(self, query):
            raise NotImplementedError("meta tensor")

    monkeypatch.setattr(search_service, "EmbeddingService", BrokenEmbeddingService)

    result = search_service.search(object(), "raise", mode="hybrid")

    assert result["items"] == [keyword]
    assert result["notice"] == "Embeddings are unavailable; keyword results are shown."
