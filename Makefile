.PHONY: install
install:
	uv sync

.PHONY: lint
lint:
	uv run ruff check

.PHONY: typecheck
typecheck:
	uv run ty check

.PHONY: format
format:
	uv run ruff format

.PHONY: test
test:
	uv run pytest

.PHONY: migrate
migrate:
	uv run madmp-api migrate

.PHONY: db
db:
	docker compose up -d db

.PHONY: requirements
requirements:
	uv pip compile pyproject.toml > requirements.txt

.PHONY: dev
dev:
	uv run uvicorn madmp_api:create_app --reload --proxy-headers --host "0.0.0.0" --port 8000

.PHONY: build
build:
	uv build
