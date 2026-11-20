import secrets
from typing import Optional

from fastapi import Depends, Header, HTTPException, Request

from src.bootstrap import Container


def get_container(request: Request) -> Container:
    return request.app.state.container


def client_key(request: Request) -> str:
    # Atrás de um proxy reverso, rode o uvicorn com --proxy-headers para que
    # este IP seja o do cliente real e não o do proxy.
    return request.client.host if request.client else "unknown"


async def enforce_rate_limit(request: Request, container: Container = Depends(get_container)) -> None:
    result = container.rate_limiter.check(client_key(request))
    if not result.allowed:
        wait = int(result.retry_after) + 1
        raise HTTPException(
            status_code=429,
            detail=f"Limite de perguntas por minuto atingido. Tente novamente em {wait}s.",
            headers={"Retry-After": str(wait)},
        )


async def require_admin(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    container: Container = Depends(get_container),
) -> None:
    expected = container.settings.ADMIN_API_KEY
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="Endpoints administrativos desabilitados: defina ADMIN_API_KEY no servidor.",
        )
    if not x_api_key or not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=401, detail="Chave de API inválida ou ausente.")
