"""Servidor de teste: serve a pasta `frontend/` e imita o contrato da API real.

Só biblioteca padrão, sem Mongo, Ollama nem FastAPI. Serve para os testes E2E do frontend
exercitarem os cenários que são difíceis de provocar na API de verdade (429, 503, 500, proxy
devolvendo HTML...). O formato das respostas segue `src/presentation/api/schemas.py`.

Gatilhos dentro do texto da pergunta:
  #429 #503 #500 #502html #badjson #slow #flaky #nocontext #xss #math
"""

import json
import mimetypes
import re
import threading
import time
import uuid
from email.parser import BytesParser
from email.policy import default as email_policy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"
ADMIN_KEY = "secret"
MAX_UPLOAD_BYTES = 1024 * 1024

SUBJECTS = [
    ("Historia", "História"),
    ("Geografia", "Geografia"),
    ("Fisica", "Física"),
    ("Quimica", "Química"),
    ("Biologia", "Biologia"),
    ("Matematica", "Matemática"),
    ("Linguagens", "Linguagens / Redação"),
    ("Geral", "Geral"),
]
SUBJECT_VALUES = {value for value, _ in SUBJECTS}

NO_CONTEXT = (
    "Não encontrei informações sobre esse tema no meu banco de dados de "
    "estudos. Tente especificar a matéria ou reformular a pergunta."
)

SOURCES = [
    {"title": "Cinemática - Cap. 1", "subject": "Fisica", "score": 0.91,
     "excerpt": "A velocidade média é a razão entre a variação do espaço e o intervalo de tempo."},
    {"title": "Cinemática - Cap. 2", "subject": "Fisica", "score": 0.84,
     "excerpt": "A aceleração média mede a variação da velocidade em um intervalo de tempo."},
]

XSS_ANSWER = (
    "Resposta **normal** antes.\n\n"
    '<img src="x" onerror="window.__xss = 1">\n\n'
    "<script>window.__xss = 2</script>\n\n"
    '[clique](javascript:window.__xss=3) e <a href="https://exemplo.org">link bom</a>\n\n'
    '<iframe src="https://exemplo.org"></iframe><style>body{display:none}</style>'
)

MATH_ANSWER = (
    "A **velocidade média** é dada por \\( v_m = \\frac{\\Delta s}{\\Delta t} \\).\n\n"
    "Em destaque:\n\n$$ a = \\frac{\\Delta v}{\\Delta t} $$\n\n"
    "Custa R$ 10 e depois R$ 20, mas $x_1$ e $x_2$ são variáveis.\n\n"
    "| Grandeza | Unidade |\n|---|---|\n| espaço | m |\n| tempo | s |\n"
)


def validation_error(field, kind="missing", **ctx):
    return 422, {"detail": [{"type": kind, "loc": ["body", field], "msg": "erro de validação", "ctx": ctx}]}


class MockApi:
    """Sobe o servidor numa thread. Os testes inspecionam `.requests` e ajustam o comportamento."""

    def __init__(self):
        self.requests = []  # [{method, path, json, headers}]
        self.sessions = {}
        self.flaky_seen = set()
        self.ready = True
        self.subjects_fail = False
        self.rate_limit_retry_after = 2
        self._server = None

    # ---- ciclo de vida
    def start(self):
        api = self

        class Handler(_Handler):
            owner = api

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return self

    def stop(self):
        if self._server:
            self._server.shutdown()
            self._server.server_close()

    @property
    def url(self):
        return f"http://127.0.0.1:{self._server.server_address[1]}"

    # ---- ajudas para os testes
    def reset(self):
        self.requests.clear()
        self.sessions.clear()
        self.flaky_seen.clear()
        self.ready = True
        self.subjects_fail = False

    def chat_posts(self):
        return [r for r in self.requests if r["method"] == "POST" and r["path"] == "/api/v1/chat/messages"]


class _Handler(BaseHTTPRequestHandler):
    owner: MockApi
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):  # silencia o log de acesso
        pass

    # ---- infraestrutura
    def _send(self, status, body=b"", content_type="application/json", headers=None):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length) if length else b""

    def _record(self, payload=None):
        self.owner.requests.append({
            "method": self.command,
            "path": urlparse(self.path).path,
            "json": payload,
            "headers": {k.lower(): v for k, v in self.headers.items()},
        })

    # ---- rotas
    def do_GET(self):
        path = urlparse(self.path).path
        self._record()
        if path == "/api/v1/subjects":
            if self.owner.subjects_fail:
                return self._send(500, {"detail": "Erro interno do servidor."})
            return self._send(200, [{"value": v, "label": label} for v, label in SUBJECTS])
        if path == "/health/ready":
            ok = self.owner.ready
            return self._send(200 if ok else 503, {"status": "ready" if ok else "unavailable",
                                                   "checks": {"mongodb": "ok", "ollama": "ok" if ok else "unavailable"}})
        if path == "/health":
            return self._send(200, {"status": "ok"})
        if match := re.fullmatch(r"/api/v1/chat/sessions/([\w-]+)", path):
            sid = match.group(1)
            return self._send(200, {"session_id": sid, "messages": self.owner.sessions.get(sid, [])})
        if path.startswith("/api/") or path.startswith("/health"):
            return self._send(404, {"detail": "Not Found"})
        return self._static(path)

    def do_DELETE(self):
        path = urlparse(self.path).path
        self._record()
        if match := re.fullmatch(r"/api/v1/chat/sessions/([\w-]+)", path):
            self.owner.sessions.pop(match.group(1), None)
            return self._send(204, b"", content_type="application/json")
        return self._send(404, {"detail": "Not Found"})

    def do_POST(self):
        path = urlparse(self.path).path
        raw = self._read_body()
        if path == "/api/v1/chat/messages":
            return self._chat(raw)
        if path == "/api/v1/documents":
            return self._upload(raw)
        self._record()
        return self._send(404, {"detail": "Not Found"})

    # ---- chat
    def _chat(self, raw):
        try:
            payload = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            payload = None
        self._record(payload)
        if not isinstance(payload, dict):
            return self._send(*validation_error("question", "json_invalid"))

        question = payload.get("question")
        if not isinstance(question, str) or not question.strip():
            return self._send(*validation_error("question", "string_too_short"))
        if len(question) > 2000:
            return self._send(*validation_error("question", "string_too_long", max_length=2000))
        subject = payload.get("subject")
        if subject is not None and subject not in SUBJECT_VALUES:
            return self._send(*validation_error("subject", "enum"))
        session_id = payload.get("session_id")
        if session_id is not None:
            try:
                uuid.UUID(str(session_id))
            except ValueError:
                return self._send(*validation_error("session_id", "uuid_parsing"))

        text = question.strip()
        if "#429" in text:
            return self._send(429, {"detail": "Limite de perguntas por minuto atingido."},
                              headers={"Retry-After": str(self.owner.rate_limit_retry_after)})
        if "#503" in text:
            return self._send(503, {"detail": "O serviço de IA está indisponível no momento. Tente novamente em instantes."})
        if "#500" in text:
            return self._send(500, {"detail": "Erro interno do servidor."})
        if "#502html" in text:
            return self._send(502, b"<html><body><h1>502 Bad Gateway</h1></body></html>", content_type="text/html")
        if "#badjson" in text:
            return self._send(200, {"unexpected": True})
        if "#flaky" in text and text not in self.owner.flaky_seen:
            self.owner.flaky_seen.add(text)
            return self._send(503, {"detail": "O serviço de IA está indisponível no momento. Tente novamente em instantes."})
        if "#slow" in text:
            time.sleep(3)

        sid = session_id or str(uuid.uuid4())
        if "#nocontext" in text:
            answer, sources = NO_CONTEXT, []
        elif "#xss" in text:
            answer, sources = XSS_ANSWER, SOURCES[:1]
        elif "#math" in text:
            answer, sources = MATH_ANSWER, SOURCES
        else:
            answer = (f"Sobre **{text[:40]}**:\n\n- A **velocidade média** divide o espaço pelo tempo.\n"
                      "- A unidade no SI é **m/s**.\n\nExemplo: 120 km em 2 h dá 60 km/h.")
            sources = SOURCES + SOURCES[:1]  # fonte repetida: o front deve deduplicar

        if sources:  # igual à API real: sem contexto, a troca não entra no histórico
            now = "2026-11-20T12:00:00Z"
            history = self.owner.sessions.setdefault(sid, [])
            history += [{"role": "user", "content": text, "timestamp": now},
                        {"role": "assistant", "content": answer, "timestamp": now}]
        return self._send(200, {"session_id": sid, "answer": answer, "sources": sources})

    # ---- upload de PDF (área do professor)
    def _upload(self, raw):
        self._record()
        if self.headers.get("X-API-Key") != ADMIN_KEY:
            return self._send(401, {"detail": "Chave de API inválida ou ausente."})
        if len(raw) > MAX_UPLOAD_BYTES + 1024 * 1024:
            return self._send(413, {"detail": "Arquivo maior que o limite de 1 MB."})

        message = BytesParser(policy=email_policy).parsebytes(
            b"Content-Type: " + self.headers["Content-Type"].encode() + b"\r\n\r\n" + raw
        )
        fields, file_part = {}, None
        for part in message.iter_parts():
            name = part.get_param("name", header="content-disposition")
            if part.get_filename():
                file_part = part
            else:
                fields[name] = part.get_content()
        if file_part is None:
            return self._send(*validation_error("file"))
        subject, title = fields.get("subject"), (fields.get("title") or "").strip()
        if subject not in SUBJECT_VALUES:
            return self._send(*validation_error("subject", "enum"))
        if not title:
            return self._send(*validation_error("title", "string_too_short"))

        content = file_part.get_payload(decode=True) or b""
        if not content:
            return self._send(400, {"detail": "Arquivo vazio."})
        if not content.startswith(b"%PDF-"):
            return self._send(415, {"detail": "O arquivo enviado não é um PDF válido."})
        if len(content) > MAX_UPLOAD_BYTES:
            return self._send(413, {"detail": "Arquivo maior que o limite de 1 MB."})
        if b"NOTEXT" in content:
            return self._send(422, {"detail": "Nenhum texto extraível no PDF (provavelmente é digitalizado). OCR ainda não é suportado."})
        if "lento" in title:
            time.sleep(1.5)
        return self._send(201, {"title": title, "subject": subject,
                                "filename": file_part.get_filename(), "chunks_created": 7})

    # ---- arquivos estáticos
    def _static(self, path):
        if path == "/admin":
            return self._send(307, b"", headers={"Location": "/admin/"})
        relative = path.lstrip("/") or "index.html"
        target = (FRONTEND_DIR / relative).resolve()
        if target.is_dir():
            target = target / "index.html"
        if FRONTEND_DIR not in target.parents and target != FRONTEND_DIR or not target.is_file():
            return self._send(404, b"Not Found", content_type="text/plain")
        kind = {".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml", ".woff2": "font/woff2"}.get(
            target.suffix, mimetypes.guess_type(target.name)[0] or "application/octet-stream")
        return self._send(200, target.read_bytes(), content_type=kind)
