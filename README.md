# SRE LLM Assistant

AI-powered log analysis and remediation for Site Reliability Engineering.

Дипломный DevOps-проект: сбор логов → OpenSearch → анализ через локальную LLM (Ollama) → рекомендации SRE.

## Стек

- **API:** FastAPI (`sre-api`)
- **Логи:** Fluent Bit → OpenSearch + Dashboards
- **LLM:** Ollama (`gemma:2b`)
- **Мониторинг:** Prometheus + Grafana
- **CI:** GitHub Actions (`docker compose` smoke + unit-тесты)

## Быстрый старт

```bash
# 1. Поднять инфраструктуру
make up

# 2. Дождаться health API
curl -sf http://localhost:8001/health

# 3. Создать index template и засеять тестовые ERROR-логи
bash scripts/setup_opensearch.sh
python scripts/seed_logs.py

# 4. (опционально) Скачать модель
docker exec ollama ollama pull gemma:2b

# 5. Анализ инцидента
curl -X POST http://localhost:8001/api/v1/analyze \
  -H "Content-Type: application/json" \
  -d '{"hours": 1, "limit": 30}'
```

## Сервисы

| Сервис | URL |
|--------|-----|
| API / Swagger | http://localhost:8001/docs |
| OpenSearch | http://localhost:9200 |
| Dashboards | http://localhost:5601 |
| Ollama | http://localhost:11434 |
| Prometheus | http://localhost:9090 |
| Grafana | http://localhost:3000 (admin/admin) |

## API

- `GET /health` — health-check
- `POST /api/v1/analyze` — выборка ERROR/CRITICAL логов из OpenSearch и анализ через LLM

Тело запроса:

```json
{ "hours": 1, "limit": 30, "severity": "ERROR" }
```

## Make-команды

```bash
make up       # поднять docker compose
make down     # остановить и удалить тома
make build    # собрать образ sre-api
make test     # unit + integration тесты
make help     # справка
```

## Структура

```
src/                  # FastAPI приложение
scripts/              # startup, setup OpenSearch, seed логов
infra/                # OpenSearch, Fluent Bit, Ollama, monitoring
tests/                # unit + integration
.github/workflows/    # CI
```
