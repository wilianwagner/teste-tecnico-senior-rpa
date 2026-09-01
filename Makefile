.PHONY: install lint format typecheck test test-integration test-all up down logs migrate

install:
	uv sync --frozen

lint:
	uv run ruff check src tests
	uv run ruff format --check src tests

format:
	uv run ruff check --fix src tests
	uv run ruff format src tests

typecheck:
	uv run mypy src

test:
	uv run pytest -m "not integration"

test-integration:
	uv run pytest -m integration

test-all:
	uv run pytest

up:
	docker compose up --build -d

down:
	docker compose down -v

logs:
	docker compose logs -f api worker

migrate:
	uv run alembic upgrade head
