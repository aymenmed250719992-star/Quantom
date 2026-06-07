FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    EXCHANGE_MODE=demo \
    EXCHANGE_NAME=mexc \
    MIN_CONFIDENCE_SCORE=55 \
    MAX_RISK_PERCENT=1.5 \
    TARGET_WIN_RATE=65 \
    SCAN_INTERVAL_MINUTES=5 \
    _USE_SSL_RENDER=True \
    PORT=5000

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD curl -f http://localhost:${PORT}/trade/health || exit 1

CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-5000} --workers 1
