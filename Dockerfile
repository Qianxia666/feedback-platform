# 使用Python官方镜像作为基础镜像
FROM python:3.10-slim

# 设置工作目录
WORKDIR /app

# 设置Python环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_APP=app.py \
    FLASK_ENV=production \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 创建非root用户
RUN groupadd -r flask && useradd -r -g flask flask

# 先复制依赖文件，利用Docker缓存机制
COPY requirements.txt .

# 安装依赖
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install gunicorn

# 复制启动脚本
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# 复制项目文件到容器
COPY . .

# 创建数据目录并设置权限
RUN mkdir -p /app/data && \
    chown -R flask:flask /app /docker-entrypoint.sh

# 切换到非root用户
USER flask

# 设置容器健康检查
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD curl -f http://localhost:5000/ || exit 1

# 暴露端口
EXPOSE 5000

# 启动命令
ENTRYPOINT ["/docker-entrypoint.sh"] 