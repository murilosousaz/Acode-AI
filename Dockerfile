FROM python:3.13-slim AS base

# Dependências de sistema exigidas pelo PyMuPDF (fitz) para build.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Instala o gerenciador de pacotes uv (usado pelo build-backend do projeto).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copia primeiro apenas os manifestos para aproveitar o cache de camadas do Docker.
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev --no-install-project || uv sync --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev || uv sync --no-dev

ENV PATH="/app/.venv/bin:${PATH}"

CMD ["python", "-m", "src.presentation.discord.main"]
