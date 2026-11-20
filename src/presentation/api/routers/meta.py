import asyncio
import logging
from typing import List

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from src.bootstrap import Container
from src.domain.value_objects.subject import Subject
from src.presentation.api.deps import get_container
from src.presentation.api.schemas import SubjectOut

logger = logging.getLogger(__name__)

api_router = APIRouter(tags=["meta"])
health_router = APIRouter(prefix="/health", tags=["health"])


@api_router.get("/subjects", response_model=List[SubjectOut], summary="Matérias disponíveis para filtro")
async def list_subjects() -> List[SubjectOut]:
    return [SubjectOut(value=s.value, label=s.label) for s in Subject]


@health_router.get("", summary="Liveness")
async def liveness() -> dict:
    return {"status": "ok"}


@health_router.get("/ready", summary="Readiness (MongoDB e Ollama)")
async def readiness(container: Container = Depends(get_container)):
    async def run(name, check):
        try:
            await asyncio.wait_for(check(), timeout=5)
            return name, "ok"
        except Exception as e:  # noqa: BLE001 — qualquer falha = não pronto
            logger.warning("Readiness: %s falhou: %s", name, e)
            return name, "unavailable"

    results = dict(await asyncio.gather(*(run(n, c) for n, c in container.readiness_checks.items())))
    ready = all(v == "ok" for v in results.values())
    return JSONResponse(
        status_code=200 if ready else 503,
        content={"status": "ready" if ready else "unavailable", "checks": results},
    )
