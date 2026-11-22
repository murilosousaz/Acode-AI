"""E2E da tela do aluno (index.html) contra o servidor mock."""

import json
import re

import pytest
from playwright.sync_api import expect

ANSWER = ".msg-assistant:not(.typing):not(.streaming)"  # resposta FINAL (a em andamento tem .streaming)


def open_chat(page):
    page.goto("/")
    expect(page.locator(".example").first).to_be_visible()


def ask(page, text):
    page.fill("#question", text)
    page.press("#question", "Enter")


def last_post(mock_api):
    return mock_api.chat_posts()[-1]["json"]


# ------------------------------------------------------------------ primeira tela
def test_welcome_shows_subjects_and_gabarito_examples(page):
    open_chat(page)
    expect(page.get_by_role("heading", name="Qual é a sua dúvida de hoje?")).to_be_visible()

    chips = page.locator(".chip")
    expect(chips).to_have_count(9)  # Todas + 8 matérias vindas da API
    expect(chips.first).to_contain_text("Todas")
    assert page.locator('input[name="subject"]:checked').get_attribute("value") == ""

    letters = page.locator(".example .mark").all_inner_texts()
    assert letters == ["A", "B", "C", "D", "E"]
    expect(page.locator("#send")).to_be_disabled()


def test_choosing_a_subject_changes_the_examples(page):
    open_chat(page)
    page.locator(".chip", has_text="Química").click()
    expect(page.locator(".example-text").first).to_have_text("O que é uma ligação covalente?")
    assert page.locator(".example").count() == 4


def test_subjects_fall_back_to_builtin_list_when_api_fails(context_factory, mock_api):
    mock_api.subjects_fail = True
    page = context_factory()
    open_chat(page)
    expect(page.locator(".chip")).to_have_count(9)


def test_banner_warns_when_services_are_down(context_factory, mock_api):
    mock_api.ready = False
    page = context_factory()
    page.goto("/")
    expect(page.locator("#banner")).to_contain_text("iniciando")
    page.get_by_role("button", name="Fechar aviso").click()
    expect(page.locator("#banner")).to_be_hidden()


# ------------------------------------------------------------------ perguntar e receber a resposta
def test_clicking_an_example_asks_and_renders_the_answer(page, mock_api):
    open_chat(page)
    page.locator(".example").first.click()

    expect(page.locator(ANSWER)).to_be_visible()
    expect(page.locator(".typing")).to_have_count(0)
    expect(page.locator("#welcome")).to_be_hidden()

    assert last_post(mock_api) == {"question": "O que é velocidade média?"}  # sem subject e sem session_id
    expect(page.locator(".msg-user .bubble")).to_have_text("O que é velocidade média?")
    assert page.locator(f"{ANSWER} .prose strong").count() >= 2  # negrito = marca-texto
    expect(page.locator(f"{ANSWER} .prose li")).to_have_count(2)


def test_sources_are_collapsible_and_deduplicated(page):
    open_chat(page)
    ask(page, "pergunta qualquer")
    expect(page.locator(ANSWER)).to_be_visible()

    summary = page.locator(".sources summary")
    expect(summary).to_have_text("Fontes (2)")  # o mock devolve 3, uma repetida
    expect(page.locator(".sources li").first).to_be_hidden()
    summary.click()
    expect(page.locator(".sources li").first).to_contain_text("Cinemática - Cap. 1")
    expect(page.locator(".sources li").first).to_contain_text("variação do espaço")


def test_subject_is_sent_and_conversation_survives_reload(page, mock_api):
    open_chat(page)
    page.locator(".chip", has_text="Física").click()
    ask(page, "primeira pergunta")
    expect(page.locator(ANSWER)).to_be_visible()
    assert last_post(mock_api)["subject"] == "Fisica"
    session_id = page.evaluate("JSON.parse(localStorage.getItem('acodeai:session'))")
    assert re.fullmatch(r"[0-9a-f-]{36}", session_id)

    page.reload()
    expect(page.locator(".msg-user .bubble")).to_have_text("primeira pergunta")
    expect(page.locator(ANSWER)).to_be_visible()  # transcrição restaurada
    expect(page.locator('input[name="subject"][value="Fisica"]')).to_be_checked()

    ask(page, "segunda pergunta")
    expect(page.locator(ANSWER)).to_have_count(2)
    assert last_post(mock_api)["session_id"] == session_id  # continua a mesma sessão


def test_follow_up_shortcuts_reuse_the_session(page, mock_api):
    open_chat(page)
    ask(page, "O que é velocidade média?")
    expect(page.locator(ANSWER)).to_be_visible()

    shortcuts = page.locator("#followups button")
    assert shortcuts.all_inner_texts() == ["Explique de outro jeito", "Dê um exemplo", "Me faça uma pergunta para treinar"]
    shortcuts.nth(1).click()

    expect(page.locator(ANSWER)).to_have_count(2)
    body = last_post(mock_api)
    assert body["question"] == "Dê um exemplo" and "session_id" in body


# ------------------------------------------------------------------ streaming
def test_answer_grows_while_it_is_being_written_and_ends_with_sources(page, mock_api):
    open_chat(page)
    ask(page, "texto que cresce #trickle")

    live = page.locator(".msg-assistant.streaming")
    expect(live).to_be_visible()
    expect(live).to_have_attribute("aria-busy", "true")
    expect(page.locator(".typing")).to_have_count(0)  # o "Pensando…" sai quando o texto começa
    expect(page.get_by_role("button", name="Parar")).to_be_visible()
    expect(page.locator("#send")).to_be_disabled()  # uma pergunta de cada vez
    expect(page.locator("#followups button")).to_have_count(0)

    expect(live.locator(".prose")).to_contain_text("Sobre")  # já há texto...
    expect(page.locator(ANSWER)).to_have_count(0)  # ...mas a resposta final ainda não existe
    assert page.evaluate("document.querySelectorAll('.streaming .sources').length") == 0

    expect(page.locator(ANSWER)).to_be_visible(timeout=15000)  # termina: nó final no lugar do provisório
    expect(live).to_have_count(0)
    expect(page.locator(".sources summary")).to_have_text("Fontes (2)")
    expect(page.locator("#followups button")).to_have_count(3)
    expect(page.get_by_role("button", name="Copiar")).to_be_visible()
    assert len(mock_api.stream_posts()) == 1


def test_stop_button_discards_the_partial_answer_and_nothing_is_saved(page, mock_api):
    open_chat(page)
    ask(page, "vou parar #trickle")
    expect(page.locator(".msg-assistant.streaming .prose")).to_contain_text("Sobre")

    page.get_by_role("button", name="Parar").click()
    expect(page.locator(".error-title")).to_have_text("Pergunta cancelada")
    expect(page.locator(".msg-assistant")).to_have_count(0)  # o trecho parcial some
    expect(page.get_by_role("button", name="Tentar de novo")).to_be_visible()
    page.wait_for_timeout(500)
    assert mock_api.sessions == {}  # o servidor não gravou uma resposta pela metade
    assert page.evaluate("localStorage.getItem('acodeai:messages')") is None


def test_failure_midway_discards_the_partial_text_and_offers_retry(page, mock_api):
    open_chat(page)
    ask(page, "cai no meio #midfail")
    expect(page.locator(".error-title")).to_have_text("Tutor indisponível agora")
    expect(page.locator(".msg-assistant")).to_have_count(0)
    expect(page.get_by_role("button", name="Tentar de novo")).to_be_visible()
    assert mock_api.sessions == {}
    assert page.evaluate("localStorage.getItem('acodeai:messages')") is None


def test_falls_back_to_the_classic_endpoint_when_the_api_has_no_streaming(page, mock_api):
    mock_api.stream_enabled = False
    open_chat(page)
    ask(page, "primeira")
    expect(page.locator(ANSWER)).to_be_visible()
    ask(page, "segunda")
    expect(page.locator(ANSWER)).to_have_count(2)

    assert len(mock_api.stream_posts()) == 1  # só a primeira tentou o stream; depois o front lembra
    classic = [r for r in mock_api.chat_posts() if r["path"] == "/api/v1/chat/messages"]
    assert [r["json"]["question"] for r in classic] == ["primeira", "segunda"]
    expect(page.locator(".error")).to_have_count(0)


def test_streaming_can_be_turned_off_in_config_js(page, mock_api):
    page.route("**/config.js", lambda route: route.fulfill(content_type="text/javascript", body="window.ACODEAI = { apiBase: '', stream: false };"))
    open_chat(page)
    ask(page, "sem streaming")
    expect(page.locator(ANSWER)).to_be_visible()
    assert mock_api.stream_posts() == []
    assert [r["path"] for r in mock_api.chat_posts()] == ["/api/v1/chat/messages"]


def test_math_and_html_safety_also_hold_for_the_text_that_arrives_in_pieces(page):
    open_chat(page)
    ask(page, "#math #trickle")
    live_text = page.locator(".msg-assistant.streaming .prose")
    expect(live_text).to_be_visible()
    # nenhum LaTeX "cru" quebrado nem script executado no meio do caminho
    assert page.evaluate("window.__xss") is None
    expect(page.locator(f"{ANSWER} .katex").first).to_be_visible(timeout=20000)
    assert page.locator(f"{ANSWER} .katex").count() >= 4


# ------------------------------------------------------------------ campo de pergunta
def test_enter_sends_and_shift_enter_breaks_the_line(page, mock_api):
    open_chat(page)
    page.fill("#question", "linha 1")
    page.press("#question", "Shift+Enter")
    page.keyboard.type("linha 2")
    assert page.input_value("#question") == "linha 1\nlinha 2"
    assert mock_api.chat_posts() == []

    page.press("#question", "Enter")
    expect(page.locator(ANSWER)).to_be_visible()
    assert last_post(mock_api)["question"] == "linha 1\nlinha 2"
    expect(page.locator("#question")).to_have_value("")


def test_send_is_blocked_for_empty_and_over_limit_questions(page, mock_api):
    open_chat(page)
    send = page.locator("#send")
    expect(send).to_be_disabled()
    page.fill("#question", "   ")
    expect(send).to_be_disabled()

    page.fill("#question", "x" * 1700)
    expect(page.locator("#counter")).to_have_text("1700/2000")
    expect(send).to_be_enabled()

    page.fill("#question", "x" * 2001)
    expect(page.locator("#counter")).to_have_class(re.compile("over"))
    expect(send).to_be_disabled()
    page.press("#question", "Enter")
    assert mock_api.chat_posts() == []


def test_enter_inserts_a_newline_on_touch_devices(phone, mock_api):
    open_chat(phone)
    phone.fill("#question", "oi")
    phone.press("#question", "Enter")
    assert phone.input_value("#question") == "oi\n"  # no celular Enter só quebra a linha; quem envia é o botão
    assert mock_api.chat_posts() == []
    phone.tap("#send")
    expect(phone.locator(ANSWER)).to_be_visible()


# ------------------------------------------------------------------ erros
def test_rate_limit_shows_countdown_then_allows_retry(page, mock_api):
    mock_api.rate_limit_retry_after = 2
    open_chat(page)
    ask(page, "#429 muitas")

    expect(page.locator(".error-title")).to_have_text("Muitas perguntas seguidas")
    retry = page.get_by_role("button", name="Tentar de novo")
    expect(retry).to_be_disabled()
    expect(page.locator(".error-hint")).to_contain_text("perguntar de novo em")
    page.fill("#question", "outra coisa")
    expect(page.locator("#send")).to_be_disabled()  # nem digitando dá para furar o limite

    expect(page.locator(".error-hint")).to_contain_text("Pronto!", timeout=6000)
    expect(retry).to_be_enabled()
    expect(page.locator("#send")).to_be_enabled()
    retry.click()
    expect(page.locator(".error-title")).to_have_text("Muitas perguntas seguidas")  # o mock responde 429 de novo
    assert len(mock_api.chat_posts()) == 2
    expect(page.locator(".msg-user")).to_have_count(1)  # a pergunta não duplica


def test_service_unavailable_then_retry_succeeds_without_duplicating_the_question(page, mock_api):
    open_chat(page)
    ask(page, "pergunta #flaky")
    expect(page.locator(".error-title")).to_have_text("Tutor indisponível agora")
    expect(page.locator(".error-hint")).to_contain_text("serviço de IA")

    page.get_by_role("button", name="Tentar de novo").click()
    expect(page.locator(ANSWER)).to_be_visible()
    expect(page.locator(".error")).to_have_count(0)
    expect(page.locator(".msg-user")).to_have_count(1)
    assert len(mock_api.chat_posts()) == 2


@pytest.mark.parametrize(
    ("trigger", "title"),
    [
        ("#500", "Algo falhou no servidor"),
        ("#502html", "Algo falhou no servidor"),  # proxy devolvendo HTML
        ("#badjson", "Resposta inesperada do servidor"),
    ],
)
def test_server_failures_show_a_friendly_message(page, trigger, title):
    open_chat(page)
    ask(page, f"pergunta {trigger}")
    expect(page.locator(".error-title")).to_have_text(title)
    expect(page.get_by_role("button", name="Tentar de novo")).to_be_visible()
    expect(page.locator("body")).not_to_contain_text("Traceback")


def test_network_failure_shows_connection_message(page):
    open_chat(page)
    page.route("**/api/v1/chat/messages/stream", lambda route: route.abort())
    ask(page, "oi")
    expect(page.locator(".error-title")).to_have_text("Sem conexão com o servidor")
    page.unroute("**/api/v1/chat/messages/stream")
    page.get_by_role("button", name="Tentar de novo").click()
    expect(page.locator(ANSWER)).to_be_visible()


def test_server_validation_error_puts_the_question_back_in_the_field(page):
    open_chat(page)
    page.route(
        "**/api/v1/chat/messages/stream",
        lambda route: route.fulfill(
            status=422,
            content_type="application/json",
            body=json.dumps({"detail": [{"type": "string_too_long", "loc": ["body", "question"], "msg": "x", "ctx": {"max_length": 2000}}]}),
        ),
    )
    ask(page, "minha pergunta")
    expect(page.locator(".error-hint")).to_contain_text("2000 caracteres")
    expect(page.locator("#question")).to_have_value("minha pergunta")  # nada se perde
    expect(page.locator(".msg-user")).to_have_count(0)
    expect(page.get_by_role("button", name="Tentar de novo")).to_have_count(0)


def test_a_new_question_after_an_error_replaces_the_failed_one(page):
    open_chat(page)
    ask(page, "primeira #500")
    expect(page.locator(".error")).to_be_visible()
    ask(page, "segunda")
    expect(page.locator(ANSWER)).to_be_visible()
    expect(page.locator(".msg-user")).to_have_count(1)
    expect(page.locator(".msg-user .bubble")).to_have_text("segunda")


def test_slow_answer_can_be_cancelled_and_retried(page, mock_api):
    open_chat(page)
    ask(page, "demorada #slow")
    expect(page.locator(".typing")).to_be_visible()
    page.get_by_role("button", name="Cancelar").click()

    expect(page.locator(".error-title")).to_have_text("Pergunta cancelada")
    expect(page.locator(".typing")).to_have_count(0)
    expect(page.locator("#send")).to_be_disabled()  # campo vazio, nada a enviar
    page.fill("#question", "outra")
    expect(page.locator("#send")).to_be_enabled()  # liberado para uma nova pergunta


def test_waiting_indicator_shows_elapsed_time_and_a_hint_for_slow_answers(page):
    page.clock.install()  # relógio falso: os 15 s de espera passam em milissegundos
    open_chat(page)
    ask(page, "demorada #slow")
    expect(page.locator(".typing")).to_contain_text("Pensando…")
    expect(page.locator(".typing")).not_to_contain_text("carregar")

    page.clock.run_for(16_000)
    expect(page.locator(".typing-text")).to_have_text("Pensando… 16s")
    expect(page.locator(".typing-hint")).to_contain_text("primeira resposta costuma demorar mais")
    expect(page.locator(ANSWER)).to_be_visible(timeout=6000)  # o mock responde depois de 3 s reais
    expect(page.locator(".typing")).to_have_count(0)


# ------------------------------------------------------------------ conteúdo da resposta
def test_answers_without_sources_offer_a_way_forward(page, mock_api):
    open_chat(page)
    page.locator(".chip", has_text="Física").click()
    ask(page, "fora do material #nocontext")

    expect(page.locator(".help")).to_contain_text("palavras que aparecem nos livros")
    expect(page.locator("#followups button")).to_have_count(0)  # sem fontes, sem atalhos
    assert last_post(mock_api)["subject"] == "Fisica"

    page.get_by_role("button", name="Buscar em todas as matérias").click()
    expect(page.locator(ANSWER)).to_have_count(2)
    assert "subject" not in last_post(mock_api)


def test_math_is_rendered_and_prices_stay_plain_text(page):
    open_chat(page)
    ask(page, "#math")
    expect(page.locator(f"{ANSWER} .katex").first).to_be_visible()

    assert page.locator(f"{ANSWER} .katex").count() >= 4  # v_m, a (destaque), x_1, x_2
    assert page.locator(f"{ANSWER} .katex-display").count() == 1
    expect(page.locator(ANSWER)).to_contain_text("R$ 10 e depois R$ 20")
    expect(page.locator(f"{ANSWER} .table-wrap table")).to_be_visible()
    assert "\\frac" not in page.locator(f"{ANSWER} .prose").inner_text()  # nenhum LaTeX cru à mostra


def test_answer_html_is_sanitized(page):
    """A resposta da IA é texto não confiável: nada de script, imagem, iframe, estilo ou javascript:."""
    open_chat(page)
    ask(page, "#xss")
    expect(page.locator(ANSWER)).to_contain_text("Resposta normal antes.")
    page.wait_for_timeout(300)  # dá tempo de um onerror disparar, se existisse

    assert page.evaluate("window.__xss") is None
    prose = page.locator(f"{ANSWER} .prose")
    for forbidden in ("img", "script", "iframe", "style"):
        assert prose.locator(forbidden).count() == 0, forbidden
    assert prose.locator('a[href^="javascript"]').count() == 0

    good = prose.locator("a", has_text="link bom")
    assert good.get_attribute("target") == "_blank"
    assert "noopener" in good.get_attribute("rel")


def test_copy_button_gives_feedback(page):
    page.context.grant_permissions(["clipboard-read", "clipboard-write"])
    open_chat(page)
    ask(page, "copiar")
    page.get_by_role("button", name="Copiar").click()
    expect(page.get_by_role("button", name="Copiado!")).to_be_visible()
    assert "velocidade média" in page.evaluate("navigator.clipboard.readText()")


# ------------------------------------------------------------------ nova conversa
def test_new_conversation_asks_for_confirmation_and_clears_everything(page, mock_api):
    open_chat(page)
    ask(page, "uma pergunta")
    expect(page.locator(ANSWER)).to_be_visible()
    session_id = page.evaluate("JSON.parse(localStorage.getItem('acodeai:session'))")

    page.get_by_role("button", name="Nova conversa").click()
    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible()
    dialog.get_by_role("button", name="Cancelar").click()
    expect(page.locator(ANSWER)).to_be_visible()  # cancelar mantém tudo

    page.get_by_role("button", name="Nova conversa").click()
    page.get_by_role("button", name="Apagar e começar").click()
    expect(page.locator("#welcome")).to_be_visible()
    expect(page.locator(".msg")).to_have_count(0)
    assert page.evaluate("localStorage.getItem('acodeai:session')") is None
    assert page.evaluate("localStorage.getItem('acodeai:messages')") is None
    page.wait_for_timeout(200)
    deletes = [r for r in mock_api.requests if r["method"] == "DELETE"]
    assert [d["path"] for d in deletes] == [f"/api/v1/chat/sessions/{session_id}"]

    ask(page, "outra conversa")
    expect(page.locator(ANSWER)).to_be_visible()
    assert "session_id" not in last_post(mock_api)  # sessão nova


def test_conversation_is_restored_from_the_server_when_local_transcript_is_gone(page, mock_api):
    open_chat(page)
    ask(page, "pergunta guardada")
    expect(page.locator(ANSWER)).to_be_visible()
    page.evaluate("localStorage.removeItem('acodeai:messages')")  # só a sessão fica
    page.reload()
    expect(page.locator(".msg-user .bubble")).to_have_text("pergunta guardada")
    expect(page.locator(f"{ANSWER} .prose")).to_contain_text("velocidade média")
    expect(page.locator(".help")).to_have_count(0)  # sem fontes guardadas ≠ "sem resultado"


# ------------------------------------------------------------------ layout e acessibilidade
def test_phone_layout_has_no_horizontal_scroll_even_with_wide_content(phone):
    open_chat(phone)
    assert phone.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    phone.fill("#question", "#math")
    phone.tap("#send")
    expect(phone.locator(f"{ANSWER} .katex").first).to_be_visible()
    assert phone.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


def test_accessibility_basics(page):
    open_chat(page)
    assert page.get_attribute("html", "lang") == "pt-BR"
    expect(page.get_by_role("textbox", name="Sua dúvida")).to_be_visible()
    expect(page.get_by_role("button", name="Enviar pergunta")).to_be_visible()
    expect(page.get_by_role("group", name="Matéria da pergunta")).to_be_visible()
    assert page.get_by_role("radio").count() == 9
    log = page.get_by_role("log", name="Conversa")
    assert log.get_attribute("aria-live") == "polite"

    ask(page, "oi")
    expect(page.locator(ANSWER)).to_be_visible()
    expect(page.locator(f"{ANSWER} .sr-only").first).to_have_text("Resposta do AcodeAI: ")
    expect(page.locator(".msg-user .sr-only")).to_have_text("Você perguntou: ")


def test_skip_link_is_the_first_tab_stop_and_focus_returns_to_the_field_after_answers(page):
    open_chat(page)
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.className") == "skip"
    page.keyboard.press("Enter")
    assert page.evaluate("document.activeElement.id") == "question"

    # clicar numa sugestão faz o botão sumir; o foco não pode se perder no <body>
    page.locator(".example").first.click()
    expect(page.locator(ANSWER)).to_be_visible()
    assert page.evaluate("document.activeElement.id") == "question"
    page.get_by_role("button", name="Dê um exemplo").click()
    expect(page.locator(ANSWER)).to_have_count(2)
    assert page.evaluate("document.activeElement.id") == "question"


def test_keyboard_only_flow_with_the_subject_radios(page, mock_api):
    open_chat(page)
    page.locator('input[name="subject"]:checked').focus()
    page.keyboard.press("ArrowRight")  # radios nativos: setas trocam a matéria
    assert page.locator('input[name="subject"]:checked').get_attribute("value") == "Historia"
    page.fill("#question", "pelo teclado")
    page.press("#question", "Enter")
    expect(page.locator(ANSWER)).to_be_visible()
    assert last_post(mock_api)["subject"] == "Historia"
