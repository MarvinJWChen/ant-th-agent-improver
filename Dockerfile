# ---- stage 1: build the SPA -------------------------------------------------
FROM node:22-slim AS web
WORKDIR /web
COPY apps/web/package*.json ./
RUN npm ci
COPY apps/web/ ./
RUN npm run build

# ---- stage 2: python runtime ------------------------------------------------
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    AGENT_IMPROVER_VAR=/app/var

WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock* ./
RUN uv sync --no-dev --frozen 2>/dev/null || uv sync --no-dev

COPY apps/api ./apps/api
COPY scripts ./scripts
COPY fixtures ./fixtures
COPY SCHEMA.md ./
COPY --from=web /web/dist ./apps/web/dist

# Seed the deterministic corpus at image build time so a cold container starts fast.
RUN uv run python -m scripts.seed --fresh || echo "seed deferred to runtime"

EXPOSE 8000
CMD ["sh", "-c", "uv run python -m scripts.seed && uv run uvicorn apps.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
