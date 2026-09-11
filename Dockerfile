# Образ FastAPI-сервиса sre-api.
FROM python:3.10-slim

WORKDIR /app

# curl нужен для healthcheck в docker-compose.
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src/
COPY scripts ./scripts/

# startup.sh ждёт OpenSearch и запускает uvicorn.
RUN chmod +x ./scripts/setup_opensearch.sh ./scripts/startup.sh \
    && chmod +x ./scripts/seed_logs.py || true

EXPOSE 8000

CMD ["./scripts/startup.sh"]
