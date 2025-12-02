FROM python:3.11-slim

WORKDIR /app

# 安裝系統依賴
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# 複製依賴檔案
COPY pyproject.toml .

# 安裝 Python 依賴
RUN pip install --no-cache-dir .

# 複製程式碼
COPY src/ src/

# 設定環境變數
ENV PYTHONPATH=/app/src
ENV HOST=0.0.0.0
ENV PORT=8000

# 暴露埠
EXPOSE 8000

# 啟動命令
CMD ["python", "-m", "uvicorn", "line_gateway.main:app", "--host", "0.0.0.0", "--port", "8000"]
