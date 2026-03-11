#!/bin/sh

set -eu

workers="${WEB_CONCURRENCY:-}"

if [ -z "$workers" ]; then
  workers="$(python - <<'PY'
import os

cpu_target = (os.cpu_count() or 1) * 2 + 1
pool_size = int(os.getenv("POOL_SIZE", "10"))
max_overflow = int(os.getenv("MAX_OVERFLOW", "5"))
connection_budget = int(os.getenv("DB_CONNECTION_BUDGET", "60"))
per_worker_connections = max(1, pool_size + max_overflow)
budget_cap = max(1, connection_budget // per_worker_connections)

print(max(1, min(cpu_target, budget_cap)))
PY
)"
fi

exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers "$workers" --loop uvloop --http httptools --log-level info