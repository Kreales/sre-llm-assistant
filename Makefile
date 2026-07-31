.PHONY: up down test build docs clean help

COMPOSE := docker compose
API_PORT := 8001
ES_PORT := 9200
DASH_PORT := 5601

up:
	@echo "🚀 Starting SRE LLM Assistant..."
	$(COMPOSE) up -d --build
	@echo "✅ Services starting:"
	@echo "   → API:        http://localhost:$(API_PORT)"
	@echo "   → OpenSearch: http://localhost:$(ES_PORT)"
	@echo "   → Dashboards: http://localhost:$(DASH_PORT)"

down:
	@echo "🛑 Stopping services..."
	$(COMPOSE) down -v
	@echo "✅ Cleaned."

build:
	@echo "🛠️ Building sre-api image..."
	docker build -t sre-api:latest -f Dockerfile.dev .
	@echo "✅ Built sre-api:latest"

test:
	@echo "🧪 Running tests..."
	python3 -m pytest tests/unit/ -v
	python3 -m pytest tests/integration/ -v
	@echo "✅ Tests passed."

seed:
	bash scripts/setup_opensearch.sh
	python3 scripts/seed_logs.py

docs:
	@echo "📝 Fetching OpenAPI schema..."
	mkdir -p docs
	curl -sf http://localhost:$(API_PORT)/openapi.json > docs/api.json \
		&& echo "✅ docs/api.json updated" \
		|| echo "⚠️ API not ready — skip openapi"

clean:
	@echo "🧹 Cleaning..."
	$(COMPOSE) down -v --remove-orphans || true
	docker system prune -f

help:
	@echo "Makefile for SRE LLM Assistant"
	@echo ""
	@echo "Commands:"
	@echo "  make up     — запустить инфраструктуру"
	@echo "  make down   — остановить и удалить тома"
	@echo "  make build  — собрать Docker-образ"
	@echo "  make test   — unit & integration тесты"
	@echo "  make seed   — template + тестовые логи в OpenSearch"
	@echo "  make docs   — сохранить openapi.json"
	@echo "  make clean  — очистить docker-артефакты"
	@echo "  make help   — справка"
