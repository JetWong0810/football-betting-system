#!/bin/bash
# Wait for MySQL to be ready before starting the app
set -e

HOST="${MYSQL_HOST:-mysql}"
PORT="${MYSQL_PORT:-3306}"
MAX_RETRIES=30
RETRY_INTERVAL=2

echo "Waiting for MySQL at $HOST:$PORT..."

for i in $(seq 1 $MAX_RETRIES); do
    if python3 -c "
import pymysql
try:
    conn = pymysql.connect(host='$HOST', port=$PORT, user='${MYSQL_USER:-root}', password='${MYSQL_PASSWORD:-}', connect_timeout=3)
    conn.close()
    exit(0)
except:
    exit(1)
" 2>/dev/null; then
        echo "MySQL is ready!"
        exec "$@"
    fi
    echo "  Attempt $i/$MAX_RETRIES - MySQL not ready, retrying in ${RETRY_INTERVAL}s..."
    sleep $RETRY_INTERVAL
done

echo "ERROR: MySQL did not become ready in time"
exit 1
