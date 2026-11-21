"""Fixtures dos testes E2E do frontend (Playwright + servidor mock).

São opcionais: sem o Playwright instalado, os arquivos de teste nem são coletados; sem o
Chromium, os testes são PULADOS. Em nenhum caso o `uv run pytest` falha por isso.
Para rodar:
    uv add --dev playwright && uv run playwright install chromium
    uv run pytest tests/e2e
"""

import importlib.util

import pytest

from tests.e2e.mock_server import MockApi

# Sem Playwright, os test_*.py (que o importam no topo) não são nem coletados.
if importlib.util.find_spec("playwright") is None:
    collect_ignore_glob = ["test_*.py"]

DESKTOP = {"width": 1100, "height": 800}
PHONE = {"width": 390, "height": 800}


@pytest.fixture(scope="session")
def mock_api():
    api = MockApi().start()
    yield api
    api.stop()


@pytest.fixture(scope="session")
def browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        try:
            instance = playwright.chromium.launch()
        except Exception as error:  # navegador não instalado
            pytest.skip(f"Chromium do Playwright indisponível ({str(error).splitlines()[0]}). Rode: playwright install chromium")
        yield instance
        instance.close()


@pytest.fixture
def context_factory(browser, mock_api):
    """Cria páginas novas (sem localStorage) e falha o teste se a página lançar erro de JavaScript."""
    mock_api.reset()
    contexts, js_errors = [], []

    def make(**options):
        options.setdefault("viewport", DESKTOP)
        options.setdefault("locale", "pt-BR")
        context = browser.new_context(base_url=mock_api.url, **options)
        contexts.append(context)
        page = context.new_page()
        page.on("pageerror", lambda error: js_errors.append(str(error)))
        page.set_default_timeout(8000)
        return page

    yield make
    for context in contexts:
        context.close()
    assert js_errors == [], f"erros de JavaScript na página: {js_errors}"


@pytest.fixture
def page(context_factory):
    return context_factory()


@pytest.fixture
def phone(context_factory):
    return context_factory(viewport=PHONE, device_scale_factor=2, is_mobile=True, has_touch=True)
