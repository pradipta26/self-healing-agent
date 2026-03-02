PYTHON_VERSION ?= 3.13

.PHONY: bootstrap sync lock test lint format typecheck run

bootstrap:
	@command -v uv >/dev/null || (echo "uv is not installed. Install with: brew install uv" && exit 1)
	uv python install $(PYTHON_VERSION)
	uv venv --python $(PYTHON_VERSION) .venv
	uv sync --extra dev

sync:
	uv sync --extra dev

lock:
	uv lock

test:
	uv run pytest

lint:
	uv run ruff check .

format:
	uv run ruff format .

typecheck:
	uv run mypy src

run:
	uv run self-healing-agent
