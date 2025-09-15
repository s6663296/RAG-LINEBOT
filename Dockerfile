# 使用官方 Python 映像檔作為基礎映像檔
FROM python:3.10-slim-buster

# 設定工作目錄
WORKDIR /app

# 將 requirements.txt 複製到工作目錄
COPY requirements.txt .

# 安裝所有依賴項
RUN pip install --no-cache-dir -r requirements.txt

# 將應用程式的其餘部分複製到工作目錄
COPY . .

# 暴露應用程式監聽的端口
# Cloud Run 會自動將流量導向到這個端口
ENV PORT 8080
EXPOSE 8080

# 定義容器啟動時執行的命令
# 使用 Gunicorn 作為生產級 WSGI 伺服器
# --bind 0.0.0.0:$PORT 綁定到所有網路介面和指定的端口
# app:app 表示運行 app.py 中的 Flask 應用程式實例 (app = Flask(__name__))
CMD exec gunicorn --workers 1 --bind 0.0.0.0:$PORT "main:app"