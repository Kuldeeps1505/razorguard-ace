.PHONY: help install dev frontend test test-unit test-integration lint format typecheck \
        migrate migrate-create docker-up docker-down docker-logs seed smoke clean

# ── Default ───────────────────────────────────────────────────
help:
	@echo ""
	@echo "  RazorGuard ACE — Development Commands"
	@echo ""
	@echo "  Setup"
	@echo "    make install          Install all dependencies"
	@echo "    make dev              Start local API server (uvicorn --reload)"
	@echo "    make frontend         Start control-plane UI (vite :5173)"
	@echo ""
	@echo "  Testing"
	@echo "    make test             Run full test suite"
	@echo "    make test-unit        Unit tests only (no infra needed)"
	@echo "    make test-integration Integration tests (needs Docker)"
	@echo ""
	@echo "  Code quality"
	@echo "    make lint             Ruff lint check"
	@echo "    make format           Ruff format"
	@echo "    make typecheck        Mypy type check"
	@echo ""
	@echo "  Database"
	@echo "    make migrate          Run pending Alembic migrations"
	@echo "    make migrate-create m='description'  Create new migration"
	@echo ""
	@echo "  Docker"
	@echo "    make docker-up        Start all services (API + worker + UI :3000)"
	@echo "    make docker-down      Stop all services"
	@echo "    make docker-logs      Tail all service logs"
	@echo ""
	@echo "  Demo"
	@echo "    make seed             Seed demo data"
	@echo "    make smoke            Run smoke tests against running stack"
	@echo ""

# ── Setup ─────────────────────────────────────────────────────
install:
	pip install -e ".[dev]"
	pre-commit install

dev:
	uvicorn apps.api.main:app --reload --host 0.0.0.0 --port 8000

frontend:
	cd frontend && npm install && npm run dev

# ── Testing ───────────────────────────────────────────────────
test:
	pytest tests/ -v --tb=short

test-unit:
	pytest tests/unit/ -v --tb=short --no-cov

test-integration:
	pytest tests/integration/ -v --tb=short

test-security:
	pytest tests/security/ -v --tb=short

# ── Code quality ──────────────────────────────────────────────
lint:
	ruff check src/ apps/ tests/

format:
	ruff format src/ apps/ tests/
	ruff check --fix src/ apps/ tests/

typecheck:
	mypy src/ apps/

# ── Database ──────────────────────────────────────────────────
migrate:
	alembic upgrade head

migrate-create:
	alembic revision --autogenerate -m "$(m)"

migrate-down:
	alembic downgrade -1

# ── Docker ────────────────────────────────────────────────────
docker-up:
	docker compose up -d
	@echo "Waiting for services to be healthy..."
	@sleep 5
	@docker compose ps

docker-down:
	docker compose down

docker-down-v:
	docker compose down -v   # also removes volumes

docker-logs:
	docker compose logs -f

docker-build:
	docker compose build

# ── Demo / seed ───────────────────────────────────────────────
seed:
	docker compose exec api python /app/scripts/seed_demo.py

seed-local:
	python scripts/seed_demo.py

smoke:
	bash scripts/smoke_test.sh

# ── Clean ─────────────────────────────────────────────────────
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true
	find . -name "*.pyc" -delete 2>/dev/null; true
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
