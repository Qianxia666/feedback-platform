#!/bin/sh
set -e

# 等待一些基础服务启动（如果有的话）
# sleep 5

# 确保数据目录存在并有正确权限
if [ ! -d "/app/data" ]; then
  mkdir -p /app/data
  echo "Created data directory"
fi

# 设置默认值
WORKERS=${WORKERS:-2}
THREADS=${THREADS:-2}
LOG_LEVEL=${LOG_LEVEL:-info}

echo "Starting feedback platform with $WORKERS workers and $THREADS threads"

# 初始化数据库（如果需要）
python -c "from models import init_db; init_db()" || true

# 启动应用（开发模式）
if [ "$FLASK_ENV" = "development" ]; then
  echo "Running in development mode"
  python app.py
else
  # 启动生产模式（使用gunicorn）
  echo "Running in production mode"
  exec gunicorn --bind 0.0.0.0:5000 \
    --workers $WORKERS \
    --threads $THREADS \
    --log-level $LOG_LEVEL \
    --access-logfile - \
    --error-logfile - \
    "app:create_app()"
fi 