"""Serve o frontend estático (pasta `frontend/`) na raiz da API.

Na mesma origem da API não há CORS para configurar: `http://localhost:8000/`
abre o tutor e `http://localhost:8000/admin/` abre a área do professor.
"""

import logging
import mimetypes
from pathlib import Path
from typing import Optional

from starlette.applications import Starlette
from starlette.staticfiles import StaticFiles

logger = logging.getLogger(__name__)

# <raiz do projeto>/src/presentation/web.py -> parents[2] é a raiz.
DEFAULT_FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"

# No Windows o Python lê os tipos MIME do registro do sistema; se `.js` vier como
# `text/plain`, o navegador recusa os módulos ES e a página fica em branco.
_MIME_TYPES = {
    ".js": "text/javascript",
    ".mjs": "text/javascript",
    ".css": "text/css",
    ".svg": "image/svg+xml",
    ".woff2": "font/woff2",
    ".json": "application/json",
}


def mount_frontend(app: Starlette, directory: Optional[Path] = None) -> bool:
    """Monta o frontend em `/`. Devolve False (sem erro) se a pasta não existir.

    Chame DEPOIS de registrar os routers da API: a montagem em `/` captura tudo
    o que sobrar, então as rotas da API precisam ser avaliadas antes.
    """
    directory = Path(directory) if directory else DEFAULT_FRONTEND_DIR
    if not (directory / "index.html").is_file():
        logger.warning("Frontend não encontrado em '%s'; a API será servida sem interface web.", directory)
        return False

    for extension, mime in _MIME_TYPES.items():
        mimetypes.add_type(mime, extension)

    app.mount("/", StaticFiles(directory=directory, html=True), name="frontend")
    return True
