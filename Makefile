.PHONY: install lint typecheck test up down e2e clean

install:
	uv sync --all-packages

lint:
	uv run ruff check packages/

typecheck:
	uv run mypy --strict packages/tilth/src packages/tilth-server/src packages/tilth-mcp/src

test:
	uv run python -m pytest packages/tilth/tests -v
	uv run python -m pytest packages/tilth-server/tests -v
	uv run python -m pytest packages/tilth-mcp/tests -v

up:
	docker compose up -d --build

down:
	docker compose down -v

e2e: up
	@echo "Waiting for services to be healthy..."
	@for i in $$(seq 1 60); do \
		curl -sf http://localhost:8001/healthz > /dev/null 2>&1 && \
		curl -sf http://localhost:8002/healthz > /dev/null 2>&1 && \
		break; \
		sleep 1; \
	done
	uv run pytest e2e/ -v || (docker compose down -v && exit 1)
	docker compose down -v

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
