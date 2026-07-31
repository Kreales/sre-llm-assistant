# SRE LLM Assistant

Дипломный проект по DevOps. Идея простая: собрать логи, положить в OpenSearch,
прогнать через локальную LLM (Ollama) и получить рекомендации, что чинить.

## Что внутри

- FastAPI (`sre-api`) — эндпоинт анализа
- Fluent Bit + OpenSearch + Dashboards — логи
- Ollama (`gemma:2b`) — локальная модель
- Prometheus + Grafana — метрики
- GitHub Actions — unit-тесты и smoke на docker compose

## Как поднять

```bash
make up

# дождаться API
curl -sf http://localhost:8001/health

# шаблон индекса и тестовые ERROR-логи
bash scripts/setup_opensearch.sh
python scripts/seed_logs.py

# модель, если ещё не скачана
docker exec ollama ollama pull gemma:2b

# анализ
curl -X POST http://localhost:8001/api/v1/analyze \
  -H "Content-Type: application/json" \
  -d '{"hours": 1, "limit": 30}'
```

## Порты

| Сервис | URL |
|--------|-----|
| API / Swagger | http://localhost:8001/docs |
| OpenSearch | http://localhost:9200 |
| Dashboards | http://localhost:5601 |
| Ollama | http://localhost:11434 |
| Prometheus | http://localhost:9090/targets |
| Grafana | http://localhost:3000 (admin / admin) |

### Grafana и Prometheus

1. Prometheus: http://localhost:9090/targets — job `sre-api` должен быть UP.
2. Grafana: http://localhost:3000, логин `admin`/`admin` (можно и без логина, Viewer).
   Datasource Prometheus уже заведён через provisioning.
   Дашборд лежит в папке SRE: **SRE LLM Assistant**.
3. Чтобы на графиках что-то появилось, дерни `/health` или `/analyze`.

## API

- `GET /health`
- `POST /api/v1/analyze` — ERROR/CRITICAL из OpenSearch -> LLM

```json
{ "hours": 1, "limit": 30, "severity": "ERROR" }
```

## Make

```bash
make up       # поднять compose
make down     # остановить, снести тома
make build    # собрать образ
make test     # тесты
make seed     # template + логи
make help
```

## Структура репо

```
src/                  # приложение
scripts/              # startup, setup OS, seed
infra/                # opensearch, fluentbit, ollama, monitoring
tests/
.github/workflows/
```
