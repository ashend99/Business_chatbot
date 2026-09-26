"""HybridRAG's pure ranking pieces and the embeddings client's batching and
retry, with OpenAI replaced by an in-process fake client."""

import uuid
from types import SimpleNamespace

import httpx
import openai
import pytest

from app.components.rag.hybrid_rag import RRF_K, HybridRAG, _tokenize
from app.services import embeddings


def chunk(content: str, index: int = 0):
    return SimpleNamespace(
        id=uuid.uuid4(), document_id=uuid.uuid4(), chunk_index=index, content=content
    )


def test_tokenize_strips_punctuation_and_stopwords_keeps_apostrophes() -> None:
    assert _tokenize("Can I order the Chocolate-Cake? It's Dula's!") == [
        "order",
        "chocolate",
        "cake",
        "dula's",
    ]


def test_bm25_ranks_keyword_match_first() -> None:
    rag = HybridRAG()
    chunks = [
        chunk("Can I pay by card? Can I pay later? Can I tip?"),
        chunk("Our refund policy allows returns within seven days."),
        chunk("Delivery is available across the city."),
    ]
    ranked = rag._bm25_rank("what is the refund policy", chunks, top_k=2)
    assert ranked[0] is chunks[1]
    assert len(ranked) == 2
    assert rag._bm25_rank("anything", [], top_k=3) == []


def test_fuse_rewards_chunks_found_by_both_rankings() -> None:
    rag = HybridRAG()
    both, dense_only, sparse_only = chunk("both"), chunk("dense"), chunk("sparse")
    fused = rag._fuse([dense_only, both], [sparse_only, both], {dense_only.id: 0.1, both.id: 0.2})

    assert [d.content for d in fused][0] == "both"
    assert fused[0].similarity_score == pytest.approx(2 / (1 + RRF_K))
    by_content = {d.content: d for d in fused}
    # dense distance only for chunks that came from the dense side
    assert by_content["dense"].metadata["dense_distance"] == 0.1
    assert "dense_distance" not in by_content["sparse"].metadata
    assert by_content["both"].metadata["document_id"] == str(both.document_id)


# ---- embeddings client ------------------------------------------------------


class FakeEmbeddingsAPI:
    def __init__(self, fail_times: int = 0) -> None:
        self.batches: list[list[str]] = []
        self.fail_times = fail_times

    async def create(self, model: str, input: list[str]):
        if self.fail_times:
            self.fail_times -= 1
            response = httpx.Response(429, request=httpx.Request("POST", "https://api.openai.test"))
            raise openai.RateLimitError("rate limited", response=response, body=None)
        self.batches.append(list(input))
        return SimpleNamespace(data=[SimpleNamespace(embedding=[float(len(t))]) for t in input])


@pytest.fixture
def fake_api(monkeypatch):
    def install(**kwargs) -> FakeEmbeddingsAPI:
        api = FakeEmbeddingsAPI(**kwargs)
        monkeypatch.setattr(embeddings, "_client", SimpleNamespace(embeddings=api))
        monkeypatch.setattr(embeddings, "INITIAL_BACKOFF_SECONDS", 0)
        return api

    return install


async def test_embed_texts_batches_and_preserves_order(fake_api, monkeypatch) -> None:
    api = fake_api()
    monkeypatch.setattr(embeddings, "BATCH_SIZE", 2)
    result = await embeddings.embed_texts(["a", "bb", "ccc", "dddd", "eeeee"])
    assert result == [[1.0], [2.0], [3.0], [4.0], [5.0]]
    assert api.batches == [["a", "bb"], ["ccc", "dddd"], ["eeeee"]]


async def test_embed_texts_empty_input_makes_no_call(fake_api) -> None:
    api = fake_api()
    assert await embeddings.embed_texts([]) == []
    assert api.batches == []


async def test_embed_texts_retries_on_rate_limit(fake_api) -> None:
    api = fake_api(fail_times=2)
    assert await embeddings.embed_texts(["x"]) == [[1.0]]
    assert api.batches == [["x"]]


async def test_embed_texts_gives_up_after_max_retries(fake_api, monkeypatch) -> None:
    fake_api(fail_times=99)
    monkeypatch.setattr(embeddings, "MAX_RETRIES", 3)
    with pytest.raises(openai.RateLimitError):
        await embeddings.embed_texts(["x"])
