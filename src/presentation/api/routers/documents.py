import os
import tempfile

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from src.bootstrap import Container
from src.domain.value_objects.subject import Subject
from src.presentation.api.deps import get_container, require_admin
from src.presentation.api.schemas import IngestResponse

router = APIRouter(prefix="/documents", tags=["documents"])

_CHUNK = 1024 * 1024  # 1 MB


@router.post(
    "",
    response_model=IngestResponse,
    status_code=201,
    summary="[Admin] Envia um PDF para ser indexado",
    dependencies=[Depends(require_admin)],
)
async def upload_document(
    request: Request,
    file: UploadFile = File(..., description="Arquivo PDF."),
    subject: Subject = Form(...),
    title: str = Form(..., min_length=1, max_length=200),
    container: Container = Depends(get_container),
) -> IngestResponse:
    max_bytes = container.settings.MAX_UPLOAD_MB * 1024 * 1024

    # Rejeição rápida quando o cliente já declara um corpo grande demais.
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > max_bytes + _CHUNK:
        raise HTTPException(413, f"Arquivo maior que o limite de {container.settings.MAX_UPLOAD_MB} MB.")

    filename = file.filename or "documento.pdf"
    fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)

    try:
        size = 0
        with open(tmp_path, "wb") as out:
            while chunk := await file.read(_CHUNK):
                if size == 0 and not chunk.startswith(b"%PDF-"):
                    raise HTTPException(415, "O arquivo enviado não é um PDF válido.")
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(413, f"Arquivo maior que o limite de {container.settings.MAX_UPLOAD_MB} MB.")
                out.write(chunk)

        if size == 0:
            raise HTTPException(400, "Arquivo vazio.")

        created = await container.ingest_material.execute(
            pdf_path=tmp_path, subject=subject.value, title=title.strip(), source_name=filename
        )
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    if created == 0:
        raise HTTPException(
            422, "Nenhum texto extraível no PDF (provavelmente é digitalizado). OCR ainda não é suportado."
        )

    return IngestResponse(title=title.strip(), subject=subject.value, filename=filename, chunks_created=created)
