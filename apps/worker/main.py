"""
Celery worker entry point.

Workers handle:
  - Payment reconciliation (UNKNOWN → SUCCESS/FAILED)
  - Webhook retry
  - Audit event flushing
  - Background policy evaluation jobs

Run with:
  celery -A apps.worker.main worker --loglevel=info
"""

from celery import Celery

from razorguard.infrastructure.observability.logging import configure_logging
from razorguard.shared.config import get_settings

settings = get_settings()
configure_logging(log_level=settings.log_level, log_format=settings.log_format)

celery_app = Celery(
    "razorguard",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["apps.worker.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,  # ack only after task completes — safe for payments
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,  # process one task at a time per worker
    task_routes={
        "apps.worker.tasks.reconcile_unknown_payment": {"queue": "reconciliation"},
        "apps.worker.tasks.process_webhook_event": {"queue": "webhooks"},
        "apps.worker.tasks.execute_checkout_task": {"queue": "celery"},  # default queue
        "apps.worker.tasks.sweep_unknown_payments": {"queue": "reconciliation"},
        "apps.worker.tasks.release_expired_campaign_reservations": {"queue": "celery"},
    },
    # ── Celery Beat Schedule ──────────────────────────────────
    beat_schedule={
        # Sweep for UNKNOWN transactions every 5 minutes
        "sweep-unknown-payments-every-5-minutes": {
            "task": "apps.worker.tasks.sweep_unknown_payments",
            "schedule": 300.0,  # 5 minutes in seconds
        },
        # Release expired campaign reservations every hour
        "release-expired-campaign-reservations-hourly": {
            "task": "apps.worker.tasks.release_expired_campaign_reservations",
            "schedule": 3600.0,  # 1 hour in seconds
        },
    },
)
