FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src/ src/
COPY apps/ apps/
COPY scripts/ scripts/

RUN pip install --no-cache-dir -e ".[dev]"

CMD ["celery", "-A", "apps.worker.main", "worker", \
     "--loglevel=info", "--concurrency=2", \
     "--queues=reconciliation,webhooks,celery"]
