# SRE LLM Assistant

Дипломный проект по DevOps. Идея простая: собрать логи, положить в OpenSearch,
прогнать через локальную LLM (Ollama) и получить рекомендации, что чинить.

## Что внутри

- FastAPI (`sre-api`) — эндпоинт анализа
- Fluent Bit + OpenSearch + Dashboards — логи
- Ollama (`llama3.2:3b`) — локальная модель (оптимально для CPU, ~6 GB RAM)
- Prometheus + Grafana — метрики
- GitHub Actions — unit-тесты, smoke на docker compose, сборка образа в GHCR и деплой

## Как поднять

```bash
make up

# дождаться API
curl -sf http://localhost:8001/health

# шаблон индекса и тестовые ERROR-логи
bash scripts/setup_opensearch.sh
python scripts/seed_logs.py

# модель, если ещё не скачана (нужно ~2 GB на диске, ~3 GB RAM в работе)
docker exec ollama ollama pull llama3.2:3b

# анализ
curl -X POST http://localhost:8001/api/v1/analyze \
  -H "Content-Type: application/json" \
  -d '{"hours": 1, "limit": 10}'
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
| cAdvisor | http://localhost:8080 |

### Grafana и Prometheus

1. Prometheus: http://localhost:9090/targets — jobs `sre-api` и `cadvisor` должны быть UP.
2. Grafana: http://localhost:3000, логин `admin`/`admin` (можно и без логина, Viewer).
   Datasource Prometheus уже заведён через provisioning.
   Дашборд лежит в папке SRE: **SRE LLM Assistant**.
3. Чтобы на графиках что-то появилось: `make demo` (или `bash scripts/demo_metrics.sh`).
   Скрипт ~90 секунд бьёт `/health`, `/metrics`, `/analyze`, OpenSearch, Prometheus и Grafana.
   Длительность и параллельность: `LOADGEN_DURATION=120 LOADGEN_CONCURRENCY=6 make demo`.

## API

- `GET /health`
- `POST /api/v1/analyze` — ERROR/CRITICAL из OpenSearch -> LLM

```json
{ "hours": 1, "limit": 10, "severity": "ERROR" }
```

## Make

```bash
make up       # поднять compose
make down     # остановить, снести тома
make build    # собрать образ
make test     # тесты
make seed     # template + логи
make deploy   # выкатить образ из GHCR (нужен SRE_API_IMAGE)
make help
```

## CI/CD

Пайплайн в `.github/workflows/ci.yml`:

1. **unit-tests** — pytest, на каждый push и PR
2. **integration-smoke** — поднять OpenSearch + Ollama + API и прогнать `/health` и `/analyze`
3. **build-and-push** — после тестов на `main` собрать `sre-api` и запушить в GitHub Container Registry
4. **deploy** — по SSH на сервер: `git pull`, `docker compose pull`, `up -d`, проверка `/health`

На PR деплой не запускается. Пока не задан `DEPLOY_PATH`, job **deploy** пропускается — образ всё равно уходит в GHCR. Ручной запуск: Actions → CI/CD Pipeline → Run workflow.

### Секреты и переменные

GitHub → Settings → Environments → `production`:

| Тип | Имя | Назначение |
|-----|-----|------------|
| Secret | `DEPLOY_HOST` | IP или DNS сервера |
| Secret | `DEPLOY_USER` | SSH-пользователь |
| Secret | `DEPLOY_SSH_KEY` | приватный ключ (без пароля) |
| Variable | `DEPLOY_PATH` | путь к клону репо, например `/home/ubuntu/sre-llm-assistant` |
| Variable | `DEPLOY_PORT` | SSH-порт, по умолчанию `22` |

На сервере заранее: Docker, Docker Compose, клон репо, `.env` (см. `.env.example`), `vm.max_map_count=262144` для OpenSearch.

Образ: `ghcr.io/<owner>/sre-llm-assistant/sre-api:<sha>` и `:latest`. После первого пуша в GHCR привяжи пакет к репозиторию (Package settings → Connect repository), иначе сервер не сможет его скачать.

## Структура репо

```
src/                  # приложение
scripts/              # startup, setup OS, seed
infra/                # opensearch, fluentbit, ollama, monitoring
tests/
.github/workflows/
```
