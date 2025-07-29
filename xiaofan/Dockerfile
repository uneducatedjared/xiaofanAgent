# 使用轻量级的 Python 基础镜像
FROM python:3.11-slim

# 设置容器内的工作目录
WORKDIR /app/xiaofan

# 复制 requirements.txt 文件并安装依赖
COPY xiaofan/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用程序的其余代码
COPY xiaofan/ .

# 暴露 Streamlit 运行的端口（默认为 8501）
EXPOSE 8501

# 运行 Streamlit 应用程序的命令
CMD ["streamlit", "run", "streamlit_app.py", "--server.port=8501", "--server.address=0.0.0.0"]
