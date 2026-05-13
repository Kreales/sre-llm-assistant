.PHONY: up down logs clean seed

up:
	@echo "🚀 Поднимаем инфраструктуру..."
	docker compose up -d --wait
	@echo "✅ Stack ready. API: http://localhost:8000"

down:
	docker compose down -v

logs:
	docker compose logs -f $(service)

seed:
	@echo "📦 Генерируем синтетические логи..."
	python scripts/seed_logs.py --count 500 --services auth,payment,gateway --duration 2h

clean:
	docker compose down -v --rmi local
	docker system prune -af
