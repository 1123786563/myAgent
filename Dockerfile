# Stage 1: Builder
FROM python:3.10-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Stage 2: Runtime
FROM python:3.10-slim AS runtime

WORKDIR /app

# Install runtime dependencies (libpq is needed for psycopg2)
RUN apt-get update && apt-get install -y \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /root/.local /root/.local
COPY --from=builder /app/requirements.txt .

# Update PATH to include user-installed binaries
ENV PATH=/root/.local/bin:$PATH
ENV TZ=Asia/Shanghai
ENV PYTHONUNBUFFERED=1

# Create necessary directories
RUN mkdir -p logs workspace/input config

# Copy project code
COPY . .

# Use a non-root user for security (optional but recommended)
# RUN useradd -m appuser && chown -R appuser:appuser /app
# USER appuser

# Volumes for persistence
VOLUME ["/app/workspace", "/app/logs", "/app/config"]

EXPOSE 8000

CMD ["python", "src/main.py"]
