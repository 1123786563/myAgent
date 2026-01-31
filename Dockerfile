FROM python:3.10-slim

WORKDIR /app

# 设置时区
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 安装基础依赖
RUN apt-get update && apt-get install -y \
    gcc \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖并安装
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目代码
COPY . .

# 创建必要的目录
RUN mkdir -init -p logs workspace/input

# 声明挂载点
VOLUME ["/app/workspace", "/app/logs", "/app/config"]

# 暴露 API 端口
EXPOSE 8000

# 启动命令
CMD ["python", "src/main.py"]
