FROM python:3.12-slim

RUN apt-get update && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 复制本地代码到镜像
COPY . .

# 自动生成 .env（如不存在则复制 example.env）
RUN [ -f .env ] || cp example.env .env

# 安装依赖
RUN pip install --no-cache-dir -r requirements.txt

# 暴露端口（如需）
EXPOSE 3000

# 支持环境变量覆盖
ENV HOST=0.0.0.0 \
    PORT=3000

CMD ["python", "-m", "src.server"] 