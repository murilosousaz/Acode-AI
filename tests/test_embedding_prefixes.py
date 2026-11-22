"""Prefixos de embedding (nomic-embed-text) e a checagem de compatibilidade do banco.

Python puro: não precisa de FastAPI, MongoDB nem Ollama.
"""

import pytest

from src.app.dtos.chat_dto import QuestionInput
from src.app.use_cases.answer_student_question import AnswerStudentQuestionUseCase
from src.app.use_cases.check_embedding_compatibility import CheckEmbeddingCompatibilityUseCase
from src.domain.entities.document import DocumentChunk
from src.domain.service.chunk_factory import build_chunks
from tests.fakes import FakeAI, FakeChatRepo, FakeDocRepo

NOMIC = {"query_prefix": "search_query: ", "document_prefix": "search_document: "}


def stored(repo: FakeDocRepo, count: int, model=None, prefix=None):
    for i in range(count):
        meta = {"title": "T", "source_file": "t.pdf"}
        if model is not None:
            meta["embedding_model"] = model
        if prefix is not None:
            meta["embedding_document_prefix"] = prefix
        repo.saved.append(DocumentChunk(content=f"c{i}", embedding=[], metadata=meta))
    return repo


async def check(repo, **ai_options):
    return await CheckEmbeddingCompatibilityUseCase(repo, FakeAI(**ai_options)).execute()


# ------------------------------------------------------------ a pergunta usa o papel "query"
async def test_the_student_question_is_embedded_as_a_query():
    ai = FakeAI()
    use_case = AnswerStudentQuestionUseCase(FakeDocRepo(), FakeChatRepo(), ai, ai)
    await use_case.execute(QuestionInput("s1", "O que é velocidade média?"))
    assert ai.embed_purposes == ["query"]


async def test_streaming_also_embeds_as_a_query_including_the_follow_up_variant():
    from src.domain.entities.chat_session import Message

    ai, chat_repo = FakeAI(), FakeChatRepo()
    await chat_repo.add_messages("s1", [Message("user", "O que é velocidade média?"), Message("assistant", "...")])
    use_case = AnswerStudentQuestionUseCase(FakeDocRepo(), chat_repo, ai, ai)
    await use_case.stream(QuestionInput("s1", "e a aceleração?"))
    assert ai.embed_purposes == ["query"] and len(ai.embed_calls[0]) == 2  # um único pedido, duas variantes


# ------------------------------------------------------------ registro gravado em cada chunk
def test_chunks_record_how_they_were_vectorized():
    chunks = build_chunks(
        ["a", "b"], [[0.1], [0.2]], title="Cinemática", subject="Fisica", source_file="f.pdf",
        embedding_model="nomic-embed-text", document_prefix="search_document: ",
    )
    assert [c.content for c in chunks] == ["a", "b"] and [c.embedding for c in chunks] == [[0.1], [0.2]]
    assert chunks[1].metadata == {
        "title": "Cinemática", "subject": "Fisica", "chunk_index": 1, "source_file": "f.pdf",
        "embedding_model": "nomic-embed-text", "embedding_document_prefix": "search_document: ",
    }


def test_chunks_without_prefix_record_an_empty_prefix_not_a_missing_one():
    [chunk] = build_chunks(["a"], [[0.1]], title="T", subject="Geral", source_file="f", embedding_model="m", document_prefix="")
    assert chunk.metadata["embedding_document_prefix"] == ""  # "" (sem prefixo) ≠ ausente (anterior ao registro)


def test_mismatched_texts_and_vectors_are_refused():
    with pytest.raises(ValueError, match="2 textos, mas 1 vetores"):
        build_chunks(["a", "b"], [[0.1]], title="T", subject="Geral", source_file="f", embedding_model="m", document_prefix="")


# ------------------------------------------------------------ checagem de compatibilidade
async def test_empty_database_is_fine():
    report = await check(FakeDocRepo())
    assert report.ok and report.total == 0 and report.lines() == []


async def test_legacy_chunks_are_fine_while_no_prefix_is_configured():
    report = await check(stored(FakeDocRepo(), 10))  # sem registro nenhum, como antes desta versão
    assert report.ok and report.total == 10 and report.stale == 0


async def test_enabling_prefixes_without_reingesting_is_reported():
    report = await check(stored(FakeDocRepo(), 10), **NOMIC)  # chunks antigos, prefixo recém-ligado
    assert not report.ok and report.stale == 10 and report.total == 10
    [line] = report.lines()
    assert "10 de 10 trechos" in line and "search_document: " in line and "ingest_bulks_pdf" in line
    assert "anterior ao registro" in line


async def test_after_reingesting_with_prefixes_everything_matches():
    repo = stored(FakeDocRepo(), 6, model="fake-embed", prefix="search_document: ")
    report = await check(repo, **NOMIC)
    assert report.ok and report.stale == 0


async def test_partial_reingestion_counts_only_the_stale_part():
    repo = stored(FakeDocRepo(), 4, model="fake-embed", prefix="search_document: ")
    stored(repo, 3)  # ainda não reingeridos
    report = await check(repo, **NOMIC)
    assert (report.total, report.stale) == (7, 3)


async def test_turning_prefixes_back_off_is_also_reported():
    repo = stored(FakeDocRepo(), 5, model="fake-embed", prefix="search_document: ")
    report = await check(repo)  # config sem prefixo, banco com prefixo
    assert report.stale == 5 and not report.ok


async def test_a_different_embedding_model_is_reported():
    repo = stored(FakeDocRepo(), 5, model="outro-modelo", prefix="")
    report = await check(repo)
    assert report.stale == 5 and "outro-modelo" in report.lines()[0]


async def test_only_one_of_the_two_prefixes_is_a_warning_even_with_a_clean_database():
    for options, side in (({"query_prefix": "search_query: "}, "de pergunta"), ({"document_prefix": "search_document: "}, "de documento")):
        report = await check(FakeDocRepo(), **options)
        assert not report.ok and report.stale == 0
        assert f"Só o prefixo {side}" in report.lines()[0]
