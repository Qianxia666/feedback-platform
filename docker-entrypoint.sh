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

# 未显式配置时，在持久化数据卷中生成稳定的会话密钥。
if [ -z "$SECRET_KEY" ] || [ "$SECRET_KEY" = "your-secure-secret-key" ]; then
  SECRET_FILE=/app/data/.secret_key
  if [ ! -s "$SECRET_FILE" ]; then
    python -c "import secrets; print(secrets.token_hex(32))" > "$SECRET_FILE"
    chmod 600 "$SECRET_FILE"
  fi
  SECRET_KEY=$(cat "$SECRET_FILE")
  export SECRET_KEY
fi

echo "Starting feedback platform with $WORKERS workers and $THREADS threads"

# 初始化数据库（如果需要）
python -c "from models import init_db; init_db()"

# 启动应用（开发模式）
if [ "$FLASK_ENV" = "development" ]; then
  echo "Running in development mode"
  FLASK_DEBUG=${FLASK_DEBUG:-1}
  export FLASK_DEBUG
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
