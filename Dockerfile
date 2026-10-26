# The API image, built from the repository root:
#   docker build -t starter-api .
FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv

WORKDIR /app/backend
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/ ./
RUN uv sync --frozen --no-dev
# Everything is installed now. Without this, each `uv run` syncs again and adds the dev tools.
ENV UV_NO_SYNC=1
# [module:ai]
# The embedding model (about 1 GB) is downloaded here on first use. Mount a volume on it so
# restarts don't download it again.
ENV EMBEDDING_CACHE_DIR=/app/models
# [/module:ai]

EXPOSE 8000
# Migrations run on every start.
CMD ["sh", "-c", "uv run alembic upgrade head && uv run uvicorn app.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
