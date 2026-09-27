# Dependencies are installed in their own layer, so code changes rebuild in seconds.
FROM python:3.13-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY src src
COPY alembic alembic
COPY alembic.ini ./
RUN uv sync --locked --no-dev


FROM python:3.13-slim
RUN useradd --system --uid 10001 app
WORKDIR /app
COPY --from=build --chown=app:app /app /app
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

# Apply migrations, then serve. --proxy-headers makes the client IP (used for
# unique-visitor counting) the real one when running behind a reverse proxy.
CMD ["sh", "-c", "alembic upgrade head && uvicorn utm_tracker.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]
