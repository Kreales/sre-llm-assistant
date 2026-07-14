import requests
import json
import random
from datetime import datetime, timedelta

ES_URL = "http://localhost:9200"
INDEX = "sre-logs-" + datetime.now().strftime("%Y.%m.%d")

ERROR_SCENARIOS = [
    {"level": "ERROR", "message": "ConnectionRefusedError: Connection to postgres:5432 refused"},
    {"level": "ERROR", "message": "OOMKilled: Container exceeded memory limit (512Mi)"},
    {"level": "CRITICAL", "message": "Disk space low on /var/lib/docker: 98% used"},
    {"level": "ERROR", "message": "Timeout: Upstream service 'payment-gateway' did not respond within 30s"},
    {"level": "CRITICAL", "message": "Pod restarting repeatedly: CrashLoopBackOff"},
    {"level": "ERROR", "message": "Failed to connect to Redis: Connection timeout"},
    {"level": "ERROR", "message": "Authentication failed: Invalid JWT token signature"},
    {"level": "CRITICAL", "message": "Database disk full: WAL files consuming 95% space"},
]

SERVICES = ["auth-service", "payment-gateway", "user-api", "notification-worker", "storage-api"]

def generate_recent_log():
    scenario = random.choice(ERROR_SCENARIOS)
    service = random.choice(SERVICES)
    # Логи за последние 5 минут
    timestamp = datetime.utcnow() - timedelta(minutes=random.randint(0, 5))
    return {
        "@timestamp": timestamp.isoformat(),
        "level": scenario["level"],
        "service": service,
        "pod": f"{service}-pod-{random.randint(1, 10)}",
        "message": scenario["message"],
        "host": "node-1"
    }

def send_bulk_logs(logs, batch_size=1000):
    """
    Отправляет логи через Bulk API
    """
    total_sent = 0
    total_logs = len(logs)

    for i in range(0, len(logs), batch_size):
        batch = logs[i:i + batch_size]

        bulk_body = ""
        for log in batch:
            bulk_body += json.dumps({"index": {"_index": INDEX}}) + "\n"
            bulk_body += json.dumps(log) + "\n"

        headers = {'Content-Type': 'application/x-ndjson'}
        response = requests.post(f"{ES_URL}/_bulk", data=bulk_body, headers=headers)

        if response.status_code != 200:
            print(f"❌ Bulk request failed: {response.status_code}, {response.text}")
            continue

        res_data = response.json()
        if res_data.get("errors"):
            print("⚠️ Some items in bulk request had errors:")
            for item in res_data['items']:
                if item.get('index', {}).get('error'):
                    print(f"  Error: {item['index']['error']}")
        else:
            sent = len(batch)
            total_sent += sent
            print(f"✅ Sent batch of {sent} logs ({total_sent}/{total_logs})")

def main():
    print("🚀 Starting bulk log generation (fresh ERROR/CRITICAL logs)...")
    
    # Генерируем 100 логов за последние 5 минут
    logs = [generate_recent_log() for _ in range(100)]
    
    print(f"📦 Generated {len(logs)} fresh logs. Sending via Bulk API...")
    send_bulk_logs(logs, batch_size=500)
    
    print("🏁 Bulk log generation done.")

if __name__ == "__main__":
    main()
