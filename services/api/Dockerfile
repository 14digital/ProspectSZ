# syntax=docker/dockerfile:1
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN --mount=type=secret,id=proxy_ca,required=false \
    if [ -s /run/secrets/proxy_ca ]; then \
      PIP_CERT=/run/secrets/proxy_ca pip install --no-cache-dir -r requirements.txt; \
    else \
      pip install --no-cache-dir -r requirements.txt; \
    fi
COPY . .
RUN useradd --system --uid 10001 app && mkdir -p /data/uploads && chown -R app:app /data /app
USER app
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && python -m scripts_seed && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
