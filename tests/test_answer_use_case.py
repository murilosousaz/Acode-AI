"""Caso de uso "responder dúvida" e regras do PromptBuilderService.

Python puro: não precisa de FastAPI, MongoDB nem Ollama.
"""

from src.app.dtos.chat_dto import QuestionInput
from src.app.use_cases.answer_student_question import (
    NO_CONTEXT_MESSAGE,
    AnswerStudentQuestionUseCase,
)
from src.domain.entities.chat_session import Message
from src.domain.service.prompt_builder_service import (
    FOLLOW_UP_CONTEXT_MAX_CHARS,
    FOLLOW_UP_MAX_WORDS,
    PromptBuilderService,
)
from tests.fakes import EmptyDocRepo, FakeAI, FakeChatRepo, FakeDocRepo, ScriptedDocRepo, chunk

HISTORY = [
    {"role": "user", "content": "O que é velocidade média?"},
    {"role": "assistant", "content": "É a razão entre o espaço percorrido e o tempo."},
]


# ------------------------------------------------------------ build_retrieval_query
def test_retrieval_query_first_question_is_unchanged():
    assert PromptBuilderService.build_retrieval_query([], "e a aceleração?") == "e a aceleração?"


def test_retrieval_query_short_follow_up_gets_previous_user_question():
    query = PromptBuilderService.build_retrieval_query(HISTORY, "e a aceleração?")
    assert query == "O que é velocidade média?\ne a aceleração?"


def test_retrieval_query_long_question_is_self_contained():
    question = " ".join(["palavra"] * (FOLLOW_UP_MAX_WORDS + 1))
    assert PromptBuilderService.build_retrieval_query(HISTORY, question) == question


def test_retrieval_query_limit_is_inclusive():
    question = " ".join(["palavra"] * FOLLOW_UP_MAX_WORDS)
    assert PromptBuilderService.build_retrieval_query(HISTORY, question).startswith("O que é velocidade média?")


def test_retrieval_query_uses_the_most_recent_user_message_not_the_assistant():
    history = HISTORY + [
        {"role": "user", "content": "Explique a fotossíntese"},
        {"role": "assistant", "content": "Plantas convertem luz em energia."},
    ]
    assert PromptBuilderService.build_retrieval_query(history, "dê um exemplo") == "Explique a fotossíntese\ndê um exemplo"


def test_retrieval_query_ignores_history_without_user_messages():
    history = [{"role": "assistant", "content": "Olá!"}]
    assert PromptBuilderService.build_retrieval_query(history, "e agora?") == "e agora?"


def test_retrieval_query_truncates_a_very_long_previous_question():
    history = [{"role": "user", "content": "x" * 2000}]
    query = PromptBuilderService.build_retrieval_query(history, "e agora?")
    assert query == "x" * FOLLOW_UP_CONTEXT_MAX_CHARS + "\ne agora?"


# ------------------------------------------------------------ merge_ranked_chunks
def test_merge_orders_by_score_and_limits():
    a = [chunk("a1", 0.9, "1"), chunk("a2", 0.5, "2")]
    b = [chunk("b1", 0.7, "3"), chunk("b2", 0.6, "4")]
    merged = PromptBuilderService.merge_ranked_chunks([a, b], limit=3)
    assert [c.content for c in merged] == ["a1", "b1", "b2"]


def test_merge_deduplicates_by_chunk_id_keeping_the_best_score():
    first = [chunk("trecho", 0.5, "42")]
    second = [chunk("trecho", 0.8, "42")]
    merged = PromptBuilderService.merge_ranked_chunks([first, second], limit=4)
    assert len(merged) == 1 and merged[0].metadata["score"] == 0.8


def test_merge_tie_prefers_the_first_search_and_missing_score_counts_as_zero():
    first = [chunk("da-pergunta-pura", 0.7, "1")]
    second = [chunk("da-pergunta-com-contexto", 0.7, "2"), chunk("sem-score", None, "3")]
    merged = PromptBuilderService.merge_ranked_chunks([first, second], limit=4)
    assert [c.content for c in merged] == ["da-pergunta-pura", "da-pergunta-com-contexto", "sem-score"]


def test_merge_of_a_single_list_keeps_order():
    only = [chunk("x", 0.9, "1"), chunk("y", 0.8, "2")]
    assert PromptBuilderService.merge_ranked_chunks([only], limit=4) == only


# ------------------------------------------------------------ caso de uso
def make_use_case(doc_repo=None, ai=None, chat_repo=None):
    chat_repo = chat_repo or FakeChatRepo()
    ai = ai or FakeAI()
    return AnswerStudentQuestionUseCase(doc_repo or FakeDocRepo(), chat_repo, ai, ai), chat_repo, ai


async def test_first_question_embeds_only_the_question_and_saves_the_exchange():
    use_case, chat_repo, ai = make_use_case()
    result = await use_case.execute(QuestionInput("s1", "O que é velocidade média?", "Fisica"))

    assert ai.embed_calls == [["O que é velocidade média?"]]
    assert result.answer and result.sources[0].title == "Cinemática"
    assert [m.role for m in chat_repo.data["s1"]] == ["user", "assistant"]


async def test_follow_up_searches_with_and_without_the_previous_question():
    docs = ScriptedDocRepo([[chunk("lixo", 0.55, "9")], [chunk("trecho de velocidade", 0.8, "1")]])
    use_case, chat_repo, ai = make_use_case(doc_repo=docs)
    await chat_repo.add_messages("s1", [Message("user", "O que é velocidade média?"), Message("assistant", "...")])

    result = await use_case.execute(QuestionInput("s1", "dê um exemplo"))

    # um único pedido de embeddings, com a pergunta pura e a versão com contexto
    assert ai.embed_calls == [["dê um exemplo", "O que é velocidade média?\ndê um exemplo"]]
    assert len(docs.calls) == 2
    # o trecho do assunto anterior (maior score) vence o ruído da pergunta solta
    assert [s.excerpt for s in result.sources] == ["trecho de velocidade", "lixo"]


async def test_new_topic_with_short_question_still_prefers_its_own_results():
    docs = ScriptedDocRepo([
        [chunk("Napoleão foi...", 0.88, "10"), chunk("Império francês...", 0.81, "11")],
        [chunk("velocidade média...", 0.7, "1"), chunk("Napoleão foi...", 0.86, "10")],
    ])
    use_case, chat_repo, _ = make_use_case(doc_repo=docs)
    await chat_repo.add_messages("s1", [Message("user", "O que é velocidade média?"), Message("assistant", "...")])

    result = await use_case.execute(QuestionInput("s1", "Quem foi Napoleão?"))

    assert [s.excerpt for s in result.sources][:2] == ["Napoleão foi...", "Império francês..."]
    assert sum(1 for s in result.sources if s.excerpt.startswith("Napoleão")) == 1  # sem duplicar


async def test_subject_filter_is_sent_to_every_search():
    docs = ScriptedDocRepo([[chunk("a", 0.9, "1")], [chunk("b", 0.8, "2")]])
    use_case, chat_repo, _ = make_use_case(doc_repo=docs)
    await chat_repo.add_messages("s1", [Message("user", "Q1"), Message("assistant", "A1")])
    await use_case.execute(QuestionInput("s1", "e agora?", "Fisica"))
    assert docs.calls == ["Fisica", "Fisica"]


async def test_history_goes_to_the_prompt_but_the_prompt_question_is_the_raw_one():
    use_case, chat_repo, ai = make_use_case()
    await chat_repo.add_messages("s1", [Message("user", "O que é velocidade média?"), Message("assistant", "Resposta 1")])
    await use_case.execute(QuestionInput("s1", "e a aceleração?"))

    sent = ai.chat_calls[0]
    assert [m["role"] for m in sent] == ["system", "user", "assistant", "user"]
    assert sent[-1]["content"].endswith("DÚVIDA DO ESTUDANTE:\ne a aceleração?")  # sem a pergunta anterior colada


async def test_without_relevant_chunks_the_default_message_is_returned_and_nothing_is_saved():
    use_case, chat_repo, ai = make_use_case(doc_repo=EmptyDocRepo())
    result = await use_case.execute(QuestionInput("s1", "algo fora do material"))

    assert result.answer == NO_CONTEXT_MESSAGE and result.sources == []
    assert ai.chat_calls == [] and "s1" not in chat_repo.data
