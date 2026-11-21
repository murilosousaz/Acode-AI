"""Middleware de erros e montagem do frontend.

Usam só Starlette (base do FastAPI), sem Mongo nem Ollama.
"""

import mimetypes

from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from src.presentation.api.middleware import INTERNAL_ERROR_DETAIL, UnhandledErrorMiddleware
from src.presentation.web import mount_frontend

ORIGIN = {"Origin": "http://front.test"}


async def boom(request):
    raise RuntimeError("segredo interno: senha=123")


async def ok(request):
    return JSONResponse({"ok": True})


def build_app(*, catch_all_inside_cors: bool) -> Starlette:
    app = Starlette(routes=[Route("/boom", boom, methods=["POST"]), Route("/ok", ok, methods=["POST"])])

    def add_cors():
        app.add_middleware(CORSMiddleware, allow_origins=["http://front.test"], allow_methods=["POST"])

    # add_middleware: o último adicionado é o mais externo.
    if catch_all_inside_cors:
        app.add_middleware(UnhandledErrorMiddleware)
        add_cors()
    else:
        add_cors()
        app.add_middleware(UnhandledErrorMiddleware)
    return app


# ---------------------------------------------------------------- middleware
def test_unexpected_error_becomes_json_500_with_cors_headers():
    client = TestClient(build_app(catch_all_inside_cors=True), raise_server_exceptions=False)
    r = client.post("/boom", headers=ORIGIN)
    assert r.status_code == 500
    assert r.json() == {"detail": INTERNAL_ERROR_DETAIL}
    assert r.headers["access-control-allow-origin"] == "http://front.test"
    assert "senha" not in r.text  # detalhes técnicos não vazam


def test_wrong_order_loses_cors_headers_which_is_why_main_adds_it_before_cors():
    """Documenta o defeito original: com o catch-all FORA do CORS, o navegador não lê o 500."""
    client = TestClient(build_app(catch_all_inside_cors=False), raise_server_exceptions=False)
    r = client.post("/boom", headers=ORIGIN)
    assert r.status_code == 500
    assert "access-control-allow-origin" not in r.headers


def test_normal_responses_pass_through_untouched():
    client = TestClient(build_app(catch_all_inside_cors=True))
    r = client.post("/ok", headers=ORIGIN)
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert r.headers["access-control-allow-origin"] == "http://front.test"


async def test_error_after_response_started_is_reraised():
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        raise RuntimeError("quebrou no meio do streaming")

    sent = []

    async def send(message):
        sent.append(message)

    async def receive():
        return {"type": "http.request"}

    middleware = UnhandledErrorMiddleware(app)
    try:
        await middleware({"type": "http", "method": "GET", "path": "/x"}, receive, send)
    except RuntimeError:
        pass
    else:
        raise AssertionError("a exceção deveria ter sido propagada")
    assert [m["type"] for m in sent] == ["http.response.start"]  # nenhum 500 empilhado


async def test_non_http_scopes_are_forwarded():
    seen = []

    async def app(scope, receive, send):
        seen.append(scope["type"])

    middleware = UnhandledErrorMiddleware(app)
    await middleware({"type": "lifespan"}, None, None)
    assert seen == ["lifespan"]


# ---------------------------------------------------------------- frontend
def make_front(tmp_path):
    (tmp_path / "assets" / "js").mkdir(parents=True)
    (tmp_path / "admin").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html><title>AcodeAI</title>")
    (tmp_path / "admin" / "index.html").write_text("<!doctype html><title>Admin</title>")
    (tmp_path / "assets" / "js" / "app.js").write_text("export const x = 1;")
    (tmp_path / "assets" / "app.css").write_text("body{}")
    return tmp_path


def make_app_with_front(directory):
    async def health(request):
        return PlainTextResponse("api-ok")

    app = Starlette(routes=[Route("/health", health)])
    return app, mount_frontend(app, directory)


def test_frontend_is_served_at_root_and_admin_directory(tmp_path):
    app, mounted = make_app_with_front(make_front(tmp_path))
    client = TestClient(app)
    assert mounted
    assert "AcodeAI" in client.get("/").text
    assert "Admin" in client.get("/admin/").text
    assert client.get("/admin", follow_redirects=False).status_code in (301, 307)  # barra final


def test_api_routes_take_precedence_over_the_frontend_mount(tmp_path):
    app, _ = make_app_with_front(make_front(tmp_path))
    assert TestClient(app).get("/health").text == "api-ok"


def test_javascript_is_served_with_a_js_mime_even_if_the_system_maps_it_to_text_plain(tmp_path):
    """Regressão do Windows: .js como text/plain faz o navegador recusar módulos ES."""
    mimetypes.add_type("text/plain", ".js")
    app, _ = make_app_with_front(make_front(tmp_path))
    client = TestClient(app)
    assert client.get("/assets/js/app.js").headers["content-type"].startswith("text/javascript")
    assert client.get("/assets/app.css").headers["content-type"].startswith("text/css")


def test_unknown_files_return_404(tmp_path):
    app, _ = make_app_with_front(make_front(tmp_path))
    assert TestClient(app).get("/nao-existe.js").status_code == 404


def test_missing_frontend_directory_is_not_an_error(tmp_path):
    app, mounted = make_app_with_front(tmp_path / "vazio")
    assert mounted is False
    assert TestClient(app).get("/health").text == "api-ok"


def test_the_real_frontend_folder_is_found_by_default():
    from src.presentation.web import DEFAULT_FRONTEND_DIR

    assert (DEFAULT_FRONTEND_DIR / "index.html").is_file(), "frontend/index.html não encontrado"
