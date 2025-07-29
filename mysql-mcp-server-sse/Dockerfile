FROM python:3.11-slim

RUN apt-get update && \
    rm -rf /var/lib/apt/lists/*


# 设置工作目录
WORKDIR /app/mysql-mcp-server-sse


COPY mysql-mcp-server-sse/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制本地代码到镜像
COPY mysql-mcp-server-sse/ .

# 自动生成 .env（如不存在则复制 example.env）
# RUN [ -f .env ] || cp example.env .env


# 暴露端口（如需）
EXPOSE 3000

# 支持环境变量覆盖
ENV HOST=0.0.0.0 \
    PORT=3000

CMD ["python", "-m", "src.server"] 