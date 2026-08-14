.PHONY: up down test build docs clean deploy help

ifneq (,$(wildcard .env))
include .env
endif

COMPOSE := docker compose
API_HOST_PORT ?= 8001
ES_HOST_PORT ?= 9200
DASHBOARDS_HOST_PORT ?= 5601
ES_HOST_LOCAL ?= http://localhost:9200
API_URL ?= http://localhost:8001

up:
	@echo "Starting SRE LLM Assistant..."
	$(COMPOSE) up -d --build
	@echo "Services:"
	@echo "  API:        http://localhost:$(API_HOST_PORT)"
	@echo "  OpenSearch: http://localhost:$(ES_HOST_PORT)"
	@echo "  Dashboards: http://localhost:$(DASHBOARDS_HOST_PORT)"

down:
	@echo "Stopping services..."
	$(COMPOSE) down -v
	@echo "Done."

build:
	@echo "Building sre-api image..."
	docker build -t sre-api:latest -f Dockerfile.dev .
	@echo "Built sre-api:latest"

test:
	@echo "Running tests..."
	python3 -m pytest tests/unit/ -v
	python3 -m pytest tests/integration/ -v
	@echo "Tests passed."

seed:
	ES_HOST=$(ES_HOST_LOCAL) bash scripts/setup_opensearch.sh
	ES_HOST=$(ES_HOST_LOCAL) python3 scripts/seed_logs.py

deploy:
	@test -n "$(SRE_API_IMAGE)" || { echo "Set SRE_API_IMAGE, e.g. ghcr.io/owner/sre-llm-assistant/sre-api:latest"; exit 1; }
	bash scripts/deploy.sh

docs:
	@echo "Fetching OpenAPI schema..."
	mkdir -p docs
	curl -sf $(API_URL)/openapi.json > docs/api.json \
		&& echo "docs/api.json updated" \
		|| echo "API not ready, skip openapi"

clean:
	@echo "Cleaning..."
	$(COMPOSE) down -v --remove-orphans || true
	docker system prune -f

help:
	@echo "Makefile for SRE LLM Assistant"
	@echo ""
	@echo "Commands:"
	@echo "  make up      - start stack"
	@echo "  make down    - stop and remove volumes"
	@echo "  make build   - build Docker image"
	@echo "  make test    - unit + integration tests"
	@echo "  make seed    - OpenSearch template + sample logs"
	@echo "  make docs    - save openapi.json"
	@echo "  make deploy  - pull GHCR image and restart stack (needs SRE_API_IMAGE)"
	@echo "  make clean   - prune docker leftovers"
	@echo "  make help    - this help"
