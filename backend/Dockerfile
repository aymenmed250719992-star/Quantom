FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV EXCHANGE_MODE=demo
ENV MIN_CONFIDENCE_SCORE=55
ENV MAX_RISK_PERCENT=1.5
ENV _USE_SSL_RENDER=True

EXPOSE 10000

CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-10000}
