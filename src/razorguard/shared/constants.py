"""
Application-wide constants.

Use these instead of magic strings/numbers throughout the codebase.
"""

# ── Currency ──────────────────────────────────────────────────
DEFAULT_CURRENCY = "INR"
SUPPORTED_CURRENCIES = frozenset(["INR"])

# ── Money ─────────────────────────────────────────────────────
# All monetary values are stored as integer minor units (paise).
# 1 INR = 100 paise.  NEVER use float for money.
MINOR_UNITS_PER_INR = 100
MAX_AMOUNT_MINOR = 100_000_000  # ₹10,00,000 — hard ceiling

# ── Payment methods ───────────────────────────────────────────
PAYMENT_METHOD_UPI = "UPI"
PAYMENT_METHOD_CARD = "CARD"
PAYMENT_METHOD_NETBANKING = "NETBANKING"
SUPPORTED_PAYMENT_METHODS = frozenset(
    [
        PAYMENT_METHOD_UPI,
        PAYMENT_METHOD_CARD,
        PAYMENT_METHOD_NETBANKING,
    ]
)

# ── Protocol sources ──────────────────────────────────────────
PROTOCOL_RAZORGUARD = "RAZORGUARD"
PROTOCOL_ACP = "ACP"
PROTOCOL_AP2 = "AP2"
PROTOCOL_UAP = "UAP"
PROTOCOL_UNKNOWN = "UNKNOWN"

# ── Rate limits (fallback defaults) ───────────────────────────
DEFAULT_RATE_LIMIT_API = 100  # requests/minute
DEFAULT_RATE_LIMIT_PAYMENT = 10  # payment attempts/minute
DEFAULT_RATE_LIMIT_AGENT = 60  # agent tool calls/minute

# ── Capability ────────────────────────────────────────────────
CAPABILITY_DEFAULT_TTL_SECONDS = 300  # 5 minutes
MAX_PAYMENT_ATTEMPTS = 3  # per intent

# ── Redis key prefixes ────────────────────────────────────────
REDIS_PREFIX_LOCK = "lock:"
REDIS_PREFIX_IDEMPOTENCY = "idem:"
REDIS_PREFIX_RATE_LIMIT = "rl:"
REDIS_PREFIX_CAPABILITY_USED = "cap_used:"
REDIS_PREFIX_CONSENT_USED = "consent_used:"

# ── Correlation header ────────────────────────────────────────
HEADER_REQUEST_ID = "X-Request-ID"
HEADER_CORRELATION_ID = "X-Correlation-ID"
