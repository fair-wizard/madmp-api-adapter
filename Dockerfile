# syntax=docker/dockerfile:1

# Build stage: resolve and install dependencies with uv into /app/.venv.
FROM python:3.13-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11.7 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependencies first, without the project itself: this layer is rebuilt
# only when pyproject.toml or uv.lock change, not on every source edit.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --locked --no-dev --no-install-project

COPY . /app

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev


# Runtime stage: the virtualenv and the app, no uv and no build tooling.
FROM python:3.13-slim-bookworm AS runtime

LABEL org.opencontainers.image.title="maDMP API" \
      org.opencontainers.image.description="RDA Common maDMP API adapter for DSW / FAIR Wizard" \
      org.opencontainers.image.source="https://github.com/fair-wizard/madmp-api-adapter" \
      org.opencontainers.image.licenses="MIT"

RUN groupadd --system --gid 1001 madmp \
    && useradd --system --uid 1001 --gid madmp --no-create-home madmp

WORKDIR /app

COPY --from=builder --chown=madmp:madmp /app /app

# Put the virtualenv first so `python`, `uvicorn` and `madmp-api` resolve to
# it without needing `uv run` at runtime.
# FORWARDED_ALLOW_IPS lets uvicorn trust X-Forwarded-Proto from the
# reverse proxy in front of the container, so derived DMP ids use the
# public scheme. Narrow it to the proxy address where that is known.
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FORWARDED_ALLOW_IPS="*"

USER madmp

EXPOSE 8000

# Reports that the process is serving, not that DSW and PostgreSQL are
# reachable -- /openapi.json touches neither, so a failing upstream shows
# up as a 502 on /dmps rather than as an unhealthy container.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request as u, sys; sys.exit(0 if u.urlopen('http://127.0.0.1:8000/openapi.json', timeout=3).status == 200 else 1)"]

# The store schema is created and migrated automatically on startup.
ENTRYPOINT []
CMD ["uvicorn", "--factory", "madmp_api:create_app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--proxy-headers"]
