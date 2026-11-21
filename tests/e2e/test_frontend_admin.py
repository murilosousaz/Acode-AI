"""E2E da Área do professor (admin/index.html): envio de PDF para indexação."""

from playwright.sync_api import expect

PDF = b"%PDF-1.4\n1 0 obj << /Type /Catalog >> endobj\n"


def open_admin(page):
    page.goto("/admin")  # o servidor redireciona para /admin/
    expect(page.get_by_role("heading", name="Enviar material de estudo")).to_be_visible()


def choose(page, name="Fisica_Cinematica.pdf", content=PDF, mime="application/pdf"):
    page.set_input_files("#file", {"name": name, "mimeType": mime, "buffer": content})


def upload_posts(mock_api):
    return [r for r in mock_api.requests if r["method"] == "POST" and r["path"] == "/api/v1/documents"]


def fill_valid(page, key="secret"):
    page.fill("#key", key)
    choose(page)


def test_page_loads_with_subjects_and_a_link_back(page):
    open_admin(page)
    assert page.locator("#subject option").count() == 9  # "Escolha a matéria" + 8
    expect(page.get_by_role("link", name="Voltar ao tutor")).to_have_attribute("href", "../")


def test_file_name_fills_subject_and_title(page):
    open_admin(page)
    choose(page, "Fisica_Cinematica.pdf")
    assert page.input_value("#subject") == "Fisica"
    assert page.input_value("#title") == "Fisica Cinematica"
    expect(page.locator("#drop-title")).to_have_text("Fisica_Cinematica.pdf")


def test_suggestions_do_not_overwrite_what_the_teacher_typed(page):
    open_admin(page)
    page.fill("#title", "Meu título")
    page.select_option("#subject", "Quimica")
    choose(page, "Fisica_Cinematica.pdf")
    assert page.input_value("#title") == "Meu título"
    assert page.input_value("#subject") == "Quimica"


def test_successful_upload_shows_result_and_sends_key_in_header(page, mock_api):
    open_admin(page)
    fill_valid(page)
    page.click("#submit")

    expect(page.locator(".result")).to_contain_text("Material indexado!")
    expect(page.locator(".result")).to_contain_text("7 trechos")
    [post] = upload_posts(mock_api)
    assert post["headers"]["x-api-key"] == "secret"
    assert post["headers"]["content-type"].startswith("multipart/form-data")

    page.get_by_role("button", name="Enviar outro material").click()
    expect(page.locator("#drop-title")).to_have_text("Escolha um PDF ou arraste até aqui")
    assert page.input_value("#title") == ""


def test_admin_key_is_never_stored_in_the_browser(page):
    open_admin(page)
    fill_valid(page)
    page.click("#submit")
    expect(page.locator(".result")).to_be_visible()
    stored = page.evaluate("JSON.stringify([localStorage, sessionStorage, document.cookie])")
    assert "secret" not in stored
    assert page.get_attribute("#key", "type") == "password"


def test_progress_is_shown_while_indexing(page):
    open_admin(page)
    fill_valid(page)
    page.fill("#title", "material lento")  # o mock demora 1,5 s
    page.click("#submit")
    expect(page.locator("#status")).to_contain_text("Enviando e indexando")
    expect(page.locator("#submit")).to_be_disabled()  # sem envio duplo
    expect(page.locator(".result")).to_be_visible()
    expect(page.locator("#submit")).to_be_enabled()


def test_wrong_key_shows_error_and_focuses_the_key_field(page):
    open_admin(page)
    fill_valid(page, key="errada")
    page.click("#submit")
    expect(page.locator(".error-title")).to_have_text("Chave de administrador incorreta")
    assert page.evaluate("document.activeElement.id") == "key"


def test_missing_fields_are_caught_before_any_request(page, mock_api):
    open_admin(page)
    page.click("#submit")
    expect(page.locator(".error-hint")).to_have_text("Digite a chave de administrador.")
    page.fill("#key", "secret")
    page.click("#submit")
    expect(page.locator(".error-hint")).to_have_text("Escolha um arquivo PDF.")
    choose(page, "arquivo_qualquer.pdf")  # matéria não reconhecida pelo nome
    page.click("#submit")
    expect(page.locator(".error-hint")).to_have_text("Escolha a matéria do material.")
    assert upload_posts(mock_api) == []


def test_non_pdf_is_rejected_in_the_browser(page, mock_api):
    open_admin(page)
    choose(page, "notas.txt", b"texto", "text/plain")
    expect(page.locator(".error-title")).to_have_text("Isso não é um PDF")
    assert upload_posts(mock_api) == []


def test_oversized_file_is_rejected_in_the_browser(page, mock_api):
    open_admin(page)
    choose(page, "Fisica_Grande.pdf", b"%PDF-" + b"0" * (26 * 1024 * 1024))
    expect(page.locator(".error-title")).to_have_text("Arquivo grande demais")
    expect(page.locator(".error-hint")).to_contain_text("25 MB")
    assert upload_posts(mock_api) == []


def test_server_side_rejections_are_explained(page):
    open_admin(page)
    page.fill("#key", "secret")

    choose(page, "Fisica_Falso.pdf", b"isto nao e um pdf de verdade")  # extensão .pdf, conteúdo não
    page.click("#submit")
    expect(page.locator(".error-title")).to_have_text("Isso não é um PDF")

    choose(page, "Fisica_Escaneado.pdf", PDF + b"NOTEXT")  # PDF sem texto extraível
    page.click("#submit")
    expect(page.locator(".error-title")).to_have_text("Não foi possível enviar")
    expect(page.locator(".error-hint")).to_contain_text("digitalizado")

    page.route("**/api/v1/documents", lambda route: route.fulfill(status=503, content_type="application/json", body='{"detail": "Endpoints administrativos desabilitados: defina ADMIN_API_KEY no servidor."}'))
    page.click("#submit")
    expect(page.locator(".error-hint")).to_contain_text("ADMIN_API_KEY")  # a mensagem do servidor é acionável
