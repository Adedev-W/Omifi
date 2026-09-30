FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    CV_BACKEND_HOST=0.0.0.0 \
    CV_BACKEND_PORT=8080 \
    CV_PUBLIC_BASE_URL=http://localhost:8080 \
    CV_ARTIFACT_DIR=/app/data/artifacts \
    CV_WORKSPACE_ROOT=/app \
    LATEX_BACKEND_URL=http://localhost:8080

WORKDIR /app

RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        ca-certificates \
        fontconfig \
        texlive-latex-base \
        texlive-latex-extra \
        texlive-xetex \
        fonts-dejavu \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY app ./app
COPY langflow_components ./langflow_components

RUN mkdir -p /app/data/artifacts \
    && useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8080

CMD ["uv", "run", "--no-dev", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
