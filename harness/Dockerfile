FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

# The virtual environment lives outside /app so the source can be bind-mounted over it.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project
COPY . .
RUN uv sync --frozen

EXPOSE 8080
HEALTHCHECK --interval=5s --timeout=3s --retries=20 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')"
CMD ["uvicorn", "harness.server:app", "--host", "0.0.0.0", "--port", "8080", "--reload", "--reload-dir", "src"]
