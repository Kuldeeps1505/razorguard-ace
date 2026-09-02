"""
RazorGuard ACE — FastAPI application entry point.

ARCHITECTURAL PRINCIPLE:
  The LLM is untrusted.
  Every payment action is deterministically authorized.
  Fail closed when authorization cannot be established.
"""

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from apps.api.lifespan import lifespan
from razorguard.interfaces.http.middleware.error_handler import register_error_handlers
from razorguard.interfaces.http.middleware.idempotency import IdempotencyMiddleware
from razorguard.interfaces.http.middleware.rate_limit import RateLimiter
from razorguard.interfaces.http.middleware.request_id import RequestIDMiddleware
from razorguard.interfaces.http.routes import (
    audit,
    buyer_agent,
    chaos,
    consent,
    health,
    intents,
    merchants,
    payments,
    policy,
    protocols,
    security,
    webhooks,
)
from razorguard.shared.config import get_settings

settings = get_settings()

app = FastAPI(
    title="RazorGuard ACE",
    description=(
        "Zero-trust agentic commerce & payment control plane. "
        "Every money action is bounded, explainable, and gated."
    ),
    version="0.1.0",
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
    lifespan=lifespan,
)

# ── Middleware (order matters — outermost first) ──────────────
app.add_middleware(RequestIDMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=(
        ["http://localhost:3000", "http://localhost:5173", "http://localhost:8080"]
        if not settings.is_production
        else []
    ),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Redis-backed idempotency for POST/PUT/PATCH endpoints
app.add_middleware(IdempotencyMiddleware)

# ── Error handlers ────────────────────────────────────────────
register_error_handlers(app)

# ── Routes ────────────────────────────────────────────────────
app.include_router(health.router, prefix="/health", tags=["health"])
app.include_router(
    intents.router, prefix="/intents", tags=["intents"], dependencies=[Depends(RateLimiter("api"))]
)
app.include_router(chaos.router, prefix="/chaos", tags=["chaos"])
app.include_router(
    policy.router, prefix="/policy", tags=["policy"], dependencies=[Depends(RateLimiter("api"))]
)
app.include_router(
    consent.router, prefix="", tags=["consent"], dependencies=[Depends(RateLimiter("api"))]
)
app.include_router(
    payments.router,
    prefix="/payments",
    tags=["payments"],
    dependencies=[Depends(RateLimiter("payment"))],
)
app.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])
app.include_router(
    merchants.router,
    prefix="/merchants",
    tags=["merchants"],
    dependencies=[Depends(RateLimiter("api"))],
)
app.include_router(
    buyer_agent.router,
    prefix="/agent",
    tags=["buyer-agent"],
    dependencies=[Depends(RateLimiter("agent"))],
)
app.include_router(
    protocols.router,
    prefix="/protocols",
    tags=["protocols"],
    dependencies=[Depends(RateLimiter("api"))],
)
app.include_router(
    audit.router, prefix="/audit", tags=["audit"], dependencies=[Depends(RateLimiter("api"))]
)
app.include_router(
    security.router,
    prefix="/security",
    tags=["security"],
    dependencies=[Depends(RateLimiter("api"))],
)

# ── Prometheus metrics endpoint ───────────────────────────────
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)
