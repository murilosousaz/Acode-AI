import json

import httpx
import pytest
from openai import AsyncOpenAI

from src.domain.errors import AIServiceUnavailableError
from src.infrastructure.adapters.ollama_adapter import OllamaAdapter


def make_adapter(handler, **kwargs) -> OllamaAdapter:
    adapter = OllamaAdapter(
        base_url="http://ollama.test/v1", chat_model="chat-m", embedding_model="embed-m", **kwargs
    )
    adapter.client = AsyncOpenAI(
        api_key="x",
        base_url="http://ollama.test/v1",
        max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    return adapter


def embed_response(n, dim):
    return httpx.Response(200, json={
        "object": "list", "model": "embed-m", "usage": {"prompt_tokens": 1, "total_tokens": 1},
        "data": [{"object": "embedding", "index": i, "embedding": [0.0] * dim} for i in range(n)],
    })


async def test_embeddings_are_batched_and_ordered():
    sizes = []

    def handler(request):
        payload = json.loads(request.content)
        sizes.append(len(payload["input"]))
        assert payload["model"] == "embed-m" and "dimensions" not in payload
        return embed_response(len(payload["input"]), 4)

    adapter = make_adapter(handler, embedding_dimensions=4, embedding_batch_size=2)
    vectors = await adapter.generate_embeddings(["a", "b", "c", "d", "e"])
    assert len(vectors) == 5 and sizes == [2, 2, 1]


async def test_dimension_mismatch_fails_loudly():
    adapter = make_adapter(lambda r: embed_response(1, 4), embedding_dimensions=768)
    with pytest.raises(ValueError, match="EMBEDDING_DIMENSIONS=768"):
        await adapter.generate_embeddings(["a"])


async def test_missing_model_becomes_ai_unavailable():
    adapter = make_adapter(lambda r: httpx.Response(404, json={"error": {"message": "model not found"}}))
    with pytest.raises(AIServiceUnavailableError, match="ollama pull embed-m"):
        await adapter.generate_embeddings(["a"])
    with pytest.raises(AIServiceUnavailableError, match="ollama pull chat-m"):
        await adapter.generate_chat_completion([{"role": "user", "content": "oi"}])


async def test_connection_error_becomes_ai_unavailable():
    def handler(request):
        raise httpx.ConnectError("refused")

    adapter = make_adapter(handler)
    with pytest.raises(AIServiceUnavailableError):
        await adapter.generate_chat_completion([{"role": "user", "content": "oi"}])
    with pytest.raises(AIServiceUnavailableError):
        await adapter.ping()


async def test_embedding_retries_on_5xx_then_succeeds(monkeypatch):
    calls = {"n": 0}

    async def no_sleep(_):
        pass

    monkeypatch.setattr("src.infrastructure.adapters.ollama_adapter.asyncio.sleep", no_sleep)

    def handler(request):
        calls["n"] += 1
        return httpx.Response(500, json={"error": {"message": "busy"}}) if calls["n"] < 3 else embed_response(1, 4)

    adapter = make_adapter(handler, embedding_dimensions=4)
    assert len(await adapter.generate_embeddings(["a"])) == 1 and calls["n"] == 3


async def test_chat_returns_stripped_content_and_sends_max_tokens():
    def handler(request):
        payload = json.loads(request.content)
        assert payload["model"] == "chat-m" and payload["max_tokens"] == 2048
        return httpx.Response(200, json={
            "id": "1", "object": "chat.completion", "created": 0, "model": "chat-m",
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": "  olá  "}}],
        })

    adapter = make_adapter(handler)
    assert await adapter.generate_chat_completion([{"role": "user", "content": "oi"}]) == "olá"


def chat_ok(content):
    return httpx.Response(200, json={
        "id": "1", "object": "chat.completion", "created": 0, "model": "chat-m",
        "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": content}}],
    })


async def test_chat_5xx_from_ollama_becomes_ai_unavailable():
    adapter = make_adapter(lambda r: httpx.Response(500, json={"error": {"message": "runner crashed"}}))
    with pytest.raises(AIServiceUnavailableError, match="500"):
        await adapter.generate_chat_completion([{"role": "user", "content": "oi"}])


async def test_chat_4xx_is_not_reported_as_service_unavailable():
    """400 = prompt inválido (bug nosso): continua um erro interno, não 'tente de novo'."""
    from openai import BadRequestError

    adapter = make_adapter(lambda r: httpx.Response(400, json={"error": {"message": "bad request"}}))
    with pytest.raises(BadRequestError):
        await adapter.generate_chat_completion([{"role": "user", "content": "oi"}])


async def test_empty_model_answer_becomes_ai_unavailable():
    adapter = make_adapter(lambda r: chat_ok("   "))
    with pytest.raises(AIServiceUnavailableError, match="vazia"):
        await adapter.generate_chat_completion([{"role": "user", "content": "oi"}])


async def test_embedding_5xx_after_all_retries_becomes_ai_unavailable(monkeypatch):
    async def no_sleep(_):
        pass

    monkeypatch.setattr("src.infrastructure.adapters.ollama_adapter.asyncio.sleep", no_sleep)
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(503, json={"error": {"message": "busy"}})

    adapter = make_adapter(handler, max_retries=3)
    with pytest.raises(AIServiceUnavailableError):
        await adapter.generate_embeddings(["a"])
    assert calls["n"] == 3
