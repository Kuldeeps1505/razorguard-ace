FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

# Copy everything needed for install first
COPY pyproject.toml README.md ./
COPY src/ src/
COPY apps/ apps/
COPY migrations/ migrations/
COPY scripts/ scripts/
COPY alembic.ini .

RUN pip install --no-cache-dir -e ".[dev]"

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health/live || exit 1

CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
