# syntax=docker/dockerfile:1
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl tzdata \
    && rm -rf /var/lib/apt/lists/*

# Copy only dependency manifest first — this layer is cached until pyproject.toml changes
COPY pyproject.toml README.md ./

# --mount=type=cache keeps the pip download cache across builds on the same machine
# so packages are never re-downloaded unless their version changes
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --timeout=120 -e ".[dev]"

# Copy source after deps — changes here don't bust the pip cache layer
COPY src/ src/
COPY apps/ apps/
COPY migrations/ migrations/
COPY scripts/ scripts/
COPY alembic.ini .

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health/live || exit 1

CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
