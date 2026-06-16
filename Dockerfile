FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

WORKDIR /app

# Layer 1: sync deps only (no project source yet) so Docker cache is reused
# when only source files change and pyproject.toml/uv.lock are unchanged.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

# Layer 2: source + install the project package itself (hatchling editable).
COPY src/ ./src/
RUN uv sync --frozen --no-dev

# Non-root user — principle of least privilege.
RUN adduser --disabled-password --gecos '' appuser
USER appuser

# IMPORTANT: CMD uses shell form (not exec form) so the shell expands ${PORT:-8000}.
# Exec form ["uvicorn", "--port", "${PORT:-8000}"] passes the literal string,
# which uvicorn rejects. Shell form runs: sh -c "uvicorn ... --port <value>".
# Railway injects PORT at runtime; the :-8000 default covers local docker run.
CMD sh -c "/app/.venv/bin/uvicorn analyst.api:app --host 0.0.0.0 --port ${PORT:-8000}"
