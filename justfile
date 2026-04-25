check:
    uv run ruff check .
    uv run black --check .
    uv run pytest

format:
    uv run ruff check . --fix
    uv run black .

dev:
    uv run uvicorn ui_bot.main:app --reload --host 0.0.0.0 --port 8000

install-browser:
    uv run playwright install chromium
