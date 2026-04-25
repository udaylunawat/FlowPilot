FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src

RUN uv sync --no-dev && uv run playwright install --with-deps chromium

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "ui_bot.main:app", "--host", "0.0.0.0", "--port", "8000"]
