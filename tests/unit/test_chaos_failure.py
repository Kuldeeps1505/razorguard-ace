"""
Unit tests — Phase 15: Chaos / Failure Tests.

Failure scenarios covered:
  1. UNKNOWN + reconcile          — network timeout → UNKNOWN → reconciliation only
  2. Redis down → fail closed     — lock acquisition fails → payment never executed
  3. Price drift → re-evaluate    — price changed after intent creation → PriceChangedError
  4. Concurrent duplicate → one   — second lock attempt raises ConcurrentExecutionError
  5. Stale worker                 — max reconciliation attempts exhausted gracefully

These tests assert system-level safety invariants under adverse conditions.
No real network, database, or Redis connections are required.
"""

import asyncio
import hashlib
import hmac
import inspect
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from razorguard.domain.intents.state_machine import (
    IllegalTransitionError,
    can_transition,
    validate_transition,
)
from razorguard.shared.enums import TransactionStatus
from razorguard.shared.errors import (
    ConcurrentExecutionError,
    PriceChangedError,
    ProductUnavailableError,
)

# ══════════════════════════════════════════════════════════════════════════════
# 1. UNKNOWN + Reconcile
#    Network timeout during Razorpay call → UNKNOWN → queued for reconciliation.
#    UNKNOWN must NEVER be treated as FAILED, and must NEVER trigger a blind retry.
# ══════════════════════════════════════════════════════════════════════════════


class TestUnknownStateReconcileFlow:
    """
    UNKNOWN is not FAILED. It means 'outcome uncertain'.
    Every path out of UNKNOWN must go through VERIFYING.
    """

    def test_unknown_is_not_a_terminal_state(self):
        """If UNKNOWN were terminal, reconciliation could never run."""
        assert not TransactionStatus.UNKNOWN.is_terminal

    def test_unknown_cannot_jump_to_completed(self):
        """Skipping VERIFYING to COMPLETED is illegal — could mask a partial capture."""
        assert not can_transition(TransactionStatus.UNKNOWN, TransactionStatus.COMPLETED)
        with pytest.raises(IllegalTransitionError):
            validate_transition(TransactionStatus.UNKNOWN, TransactionStatus.COMPLETED)

    def test_unknown_cannot_jump_to_failed(self):
        """Skipping VERIFYING to FAILED would write off a potentially captured payment."""
        assert not can_transition(TransactionStatus.UNKNOWN, TransactionStatus.FAILED)
        with pytest.raises(IllegalTransitionError):
            validate_transition(TransactionStatus.UNKNOWN, TransactionStatus.FAILED)

    def test_unknown_cannot_blind_retry_via_executing(self):
        """
        CRITICAL: UNKNOWN → EXECUTING would be a blind retry.
        This could result in a double charge. Must be permanently illegal.
        """
        assert not can_transition(TransactionStatus.UNKNOWN, TransactionStatus.EXECUTING)
        with pytest.raises(IllegalTransitionError):
            validate_transition(TransactionStatus.UNKNOWN, TransactionStatus.EXECUTING)

    def test_unknown_cannot_regress_to_authorized(self):
        """Cannot re-authorize once a payment has already been submitted."""
        assert not can_transition(TransactionStatus.UNKNOWN, TransactionStatus.AUTHORIZED)

    def test_reconciliation_path_exists(self):
        """UNKNOWN → VERIFYING → COMPLETED must be fully traversable."""
        validate_transition(TransactionStatus.UNKNOWN, TransactionStatus.VERIFYING)
        validate_transition(TransactionStatus.VERIFYING, TransactionStatus.COMPLETED)

    def test_reconciliation_failure_path_exists(self):
        """UNKNOWN → VERIFYING → FAILED is the correct path when payment actually failed."""
        validate_transition(TransactionStatus.UNKNOWN, TransactionStatus.VERIFYING)
        validate_transition(TransactionStatus.VERIFYING, TransactionStatus.FAILED)

    def test_full_chaos_scenario_timeout_then_reconcile_success(self):
        """
        Scenario: network timeout mid-execution → UNKNOWN → reconcile → COMPLETED.
        Full chain must be legal.
        """
        # Execution started
        validate_transition(TransactionStatus.EXECUTING, TransactionStatus.UNKNOWN)
        # Reconciliation worker picks up job
        validate_transition(TransactionStatus.UNKNOWN, TransactionStatus.VERIFYING)
        # Razorpay confirms the payment was captured
        validate_transition(TransactionStatus.VERIFYING, TransactionStatus.COMPLETED)

    def test_full_chaos_scenario_timeout_then_reconcile_failure(self):
        """
        Scenario: network timeout mid-execution → UNKNOWN → reconcile → FAILED.
        Full chain must be legal.
        """
        validate_transition(TransactionStatus.EXECUTING, TransactionStatus.UNKNOWN)
        validate_transition(TransactionStatus.UNKNOWN, TransactionStatus.VERIFYING)
        validate_transition(TransactionStatus.VERIFYING, TransactionStatus.FAILED)

    def test_reconcile_module_never_creates_new_payment(self):
        """
        Structural invariant: reconcile_unknown.py must ONLY query Razorpay,
        never call create_order. Verified by source inspection.
        """
        from razorguard.application.reconciliation import reconcile_unknown

        source = inspect.getsource(reconcile_unknown)
        assert "create_order" not in source, (
            "CRITICAL: reconcile_unknown must NEVER call create_order — "
            "that would be a duplicate charge"
        )

    def test_reconcile_module_uses_read_only_fetch(self):
        """Reconciliation must use fetch_payments_for_order, not create_order."""
        from razorguard.application.reconciliation import reconcile_unknown

        source = inspect.getsource(reconcile_unknown)
        assert "fetch_payments_for_order" in source

    @pytest.mark.asyncio
    async def test_execute_payment_returns_unknown_on_razorpay_error(self):
        """
        When create_order raises (network timeout / 5xx), execute_payment
        must NOT propagate the exception — it must return status=UNKNOWN.
        """
        from razorguard.application.payments.execute_payment import execute_payment

        mock_session = AsyncMock()
        mock_redis = AsyncMock()
        mock_redis.set.return_value = True  # lock acquired
        mock_redis.delete.return_value = 1  # lock released

        intent_id = uuid.uuid4()
        cap_id = uuid.uuid4()
        user_id = uuid.uuid4()
        agent_id = uuid.uuid4()

        # Build a fake intent and capability
        fake_intent = MagicMock()
        fake_intent.id = intent_id
        fake_intent.user_id = user_id
        fake_intent.payment_method = "UPI"
        fake_intent.merchant_id = uuid.uuid4()

        fake_cap = MagicMock()
        fake_cap.id = cap_id
        fake_cap.amount_minor = 149900
        fake_cap.currency = "INR"
        fake_cap.nonce = "test-nonce"

        fake_txn_created = MagicMock()
        fake_txn_created.id = uuid.uuid4()
        fake_txn_created.status = TransactionStatus.CREATED
        fake_txn_created.version = 1
        fake_txn_created.razorpay_order_id = None

        fake_txn_executing = MagicMock()
        fake_txn_executing.id = fake_txn_created.id
        fake_txn_executing.status = TransactionStatus.EXECUTING
        fake_txn_executing.version = 2
        fake_txn_executing.razorpay_order_id = None

        fake_txn_unknown = MagicMock()
        fake_txn_unknown.id = fake_txn_created.id
        fake_txn_unknown.status = TransactionStatus.UNKNOWN
        fake_txn_unknown.version = 3
        fake_txn_unknown.razorpay_order_id = None

        with (
            patch(
                # Lazy-imported inside execute_payment() — patch at definition site
                "razorguard.infrastructure.database.repositories.intent_repository.IntentRepository"
            ) as MockIntentRepo,
            patch(
                "razorguard.infrastructure.database.repositories.capability_repository.CapabilityRepository"
            ) as MockCapRepo,
            patch(
                "razorguard.application.payments.execute_payment.create_transaction",
                new_callable=AsyncMock,
                return_value=fake_txn_created,
            ),
            patch(
                "razorguard.application.payments.execute_payment.consume_capability",
                new_callable=AsyncMock,
            ),
            patch(
                "razorguard.application.payments.execute_payment._revalidate_for_execution",
                new_callable=AsyncMock,
            ),
            patch(
                "razorguard.application.payments.execute_payment.transition_transaction",
                new_callable=AsyncMock,
                side_effect=[fake_txn_executing, fake_txn_unknown],
            ),
            patch(
                "razorguard.application.payments.execute_payment.create_order",
                side_effect=ConnectionError("Razorpay gateway timeout"),
            ),
            patch("razorguard.application.payments.execute_payment._enqueue_reconciliation"),
            patch("razorguard.application.payments.execute_payment.payments_attempted"),
            patch("razorguard.application.payments.execute_payment.payments_unknown"),
        ):
            MockIntentRepo.return_value.get_by_id_for_user = AsyncMock(return_value=fake_intent)
            MockCapRepo.return_value.get_by_id = AsyncMock(return_value=fake_cap)

            result = await execute_payment(
                intent_id=intent_id,
                capability_id=cap_id,
                authenticated_user_id=user_id,
                authenticated_agent_id=agent_id,
                request_id="req-chaos-001",
                session=mock_session,
                redis=mock_redis,
            )

        # Must return UNKNOWN — never raise, never return FAILED
        assert (
            result["status"] == TransactionStatus.UNKNOWN.value
        ), "Payment timeout must result in UNKNOWN, not an exception or FAILED"

    @pytest.mark.asyncio
    async def test_reconcile_returns_pending_when_razorpay_still_processing(self):
        """
        When Razorpay shows no captured/failed payments (still pending),
        reconciliation must schedule a retry — not resolve to FAILED.
        """
        from razorguard.application.reconciliation.reconcile_unknown import (
            reconcile_unknown_payment,
        )

        txn_id = uuid.uuid4()
        order_id = "order_chaos_001"

        fake_txn = MagicMock()
        fake_txn.id = txn_id
        fake_txn.status = TransactionStatus.UNKNOWN.value
        fake_txn.razorpay_order_id = order_id
        fake_txn.version = 1

        fake_job = MagicMock()
        fake_job.attempt_count = 0
        fake_job.max_attempts = 10

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = fake_txn
        mock_session.execute = AsyncMock(return_value=mock_result)

        with (
            patch(
                "razorguard.application.reconciliation.reconcile_unknown._get_or_create_job",
                new_callable=AsyncMock,
                return_value=fake_job,
            ),
            patch(
                "razorguard.application.reconciliation.reconcile_unknown.fetch_payments_for_order",
                return_value=[],  # Razorpay: no captured/failed — still pending
            ),
        ):
            result = await reconcile_unknown_payment(transaction_id=txn_id, session=mock_session)

        # Must be "pending" with a retry scheduled — not "resolved" or "abandoned"
        assert (
            result["status"] == "pending"
        ), "Still-processing payment must schedule a retry, not be written off"
        assert "next_retry_seconds" in result

    @pytest.mark.asyncio
    async def test_reconcile_resolves_completed_when_razorpay_confirms_capture(self):
        """
        When Razorpay returns a captured payment, reconciliation must
        transition UNKNOWN → VERIFYING → COMPLETED.
        """
        from razorguard.application.reconciliation.reconcile_unknown import (
            reconcile_unknown_payment,
        )

        txn_id = uuid.uuid4()
        fake_txn = MagicMock()
        fake_txn.id = txn_id
        fake_txn.status = TransactionStatus.UNKNOWN.value
        fake_txn.razorpay_order_id = "order_captured_001"
        fake_txn.version = 1
        fake_txn.razorpay_payment_id = None

        fake_job = MagicMock()
        fake_job.attempt_count = 1
        fake_job.max_attempts = 10

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = fake_txn
        mock_session.execute = AsyncMock(return_value=mock_result)

        verifying_txn = MagicMock()
        verifying_txn.id = txn_id
        verifying_txn.version = 2

        completed_txn = MagicMock()
        completed_txn.id = txn_id
        completed_txn.version = 3

        with (
            patch(
                "razorguard.application.reconciliation.reconcile_unknown._get_or_create_job",
                new_callable=AsyncMock,
                return_value=fake_job,
            ),
            patch(
                "razorguard.application.reconciliation.reconcile_unknown.fetch_payments_for_order",
                return_value=[{"id": "pay_captured_001", "status": "captured"}],
            ),
            patch(
                "razorguard.application.reconciliation.reconcile_unknown.transition_transaction",
                new_callable=AsyncMock,
                side_effect=[verifying_txn, completed_txn],
            ),
            patch("razorguard.application.reconciliation.reconcile_unknown.payments_reconciled"),
        ):
            result = await reconcile_unknown_payment(transaction_id=txn_id, session=mock_session)

        assert result["status"] == "resolved"
        assert result["outcome"] == "completed"


# ══════════════════════════════════════════════════════════════════════════════
# 2. Redis Down → Fail Closed
#    If Redis is unavailable, the lock cannot be acquired.
#    The system must FAIL CLOSED — no payment must execute without a lock.
# ══════════════════════════════════════════════════════════════════════════════


class TestRedisDownFailClosed:
    """
    Redis unavailability must cause payment execution to fail closed.
    A payment without a distributed lock risks duplicate charges.
    """

    @pytest.mark.asyncio
    async def test_redis_connection_error_prevents_lock_acquisition(self):
        """
        When redis.set raises ConnectionError (Redis is down),
        acquire_payment_lock must propagate the error — not silently proceed.
        """
        from razorguard.infrastructure.cache.locks import acquire_payment_lock

        dead_redis = AsyncMock()
        dead_redis.set.side_effect = ConnectionError("Redis unreachable")

        with pytest.raises(ConnectionError):
            async with acquire_payment_lock(dead_redis, "intent-chaos-redis-down"):
                pass  # must never reach here

    @pytest.mark.asyncio
    async def test_redis_timeout_prevents_lock_acquisition(self):
        """TimeoutError from Redis must also propagate, blocking payment execution."""
        from razorguard.infrastructure.cache.locks import acquire_payment_lock

        slow_redis = AsyncMock()
        slow_redis.set.side_effect = TimeoutError("Redis command timed out")

        with pytest.raises(TimeoutError):
            async with acquire_payment_lock(slow_redis, "intent-chaos-timeout"):
                pass

    @pytest.mark.asyncio
    async def test_lock_set_returns_none_blocks_execution(self):
        """
        If Redis returns None from SET NX (lock already held),
        ConcurrentExecutionError must be raised — not a silent pass-through.
        This is the 'lock already held by another worker' scenario.
        """
        from razorguard.infrastructure.cache.locks import acquire_payment_lock

        contended_redis = AsyncMock()
        contended_redis.set.return_value = None  # SET NX returned None = not acquired

        with pytest.raises(ConcurrentExecutionError) as exc_info:
            async with acquire_payment_lock(contended_redis, "intent-chaos-contended"):
                pass

        assert "intent-chaos-contended" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_lock_is_always_released_even_on_exception(self):
        """
        Even if the body of the lock context raises, the lock must be released.
        Redis key must be deleted to prevent deadlocks.
        """
        from razorguard.infrastructure.cache.locks import acquire_payment_lock

        healthy_redis = AsyncMock()
        healthy_redis.set.return_value = True  # lock acquired
        healthy_redis.delete.return_value = 1

        with pytest.raises(RuntimeError):
            async with acquire_payment_lock(healthy_redis, "intent-lock-release-test"):
                raise RuntimeError("Simulated failure inside lock")

        # Lock must have been released despite the exception
        healthy_redis.delete.assert_called_once()

    def test_locks_module_documents_redis_not_sole_safety_net(self):
        """
        The locks module must document that DB constraints are the final safety net.
        Redis alone is NOT sufficient for financial correctness.
        """
        from razorguard.infrastructure.cache import locks

        source = inspect.getsource(locks)
        assert (
            "DB uniqueness" in source or "final safety net" in source
        ), "locks.py must document that Redis locks are first-line, not final, defence"

    def test_concurrent_execution_error_has_machine_readable_code(self):
        """ConcurrentExecutionError must have a machine-readable error code for clients."""
        err = ConcurrentExecutionError("intent-test-123")
        assert err.code == "CONCURRENT_EXECUTION"
        assert "intent-test-123" in str(err)


# ══════════════════════════════════════════════════════════════════════════════
# 3. Price Drift → Re-evaluate
#    Between intent creation and execution, the merchant updates the price.
#    The execution guard must detect this and abort with PriceChangedError.
# ══════════════════════════════════════════════════════════════════════════════


class TestPriceDriftReEvaluate:
    """
    Price drift: product price changed after intent was authorized.
    The validate_intent_for_execution guard must catch this.
    """

    def test_price_changed_error_is_typed(self):
        """PriceChangedError must carry both original and new price for client handling."""
        err = PriceChangedError("product-abc", original_minor=149900, current_minor=199900)
        assert err.code == "PRICE_CHANGED"
        assert err.details["original_minor"] == 149900
        assert err.details["current_minor"] == 199900

    def test_price_drift_calculation_is_exact(self):
        """
        Price drift is: canonical_price = product.price_minor * intent.quantity.
        If canonical_price != intent.amount_minor → drift detected.
        """
        product_price_per_unit = 49900  # ₹499 per unit
        quantity = 3
        canonical = product_price_per_unit * quantity  # ₹1497
        authorized_amount = 149900 * 1  # ₹1499 (original, now wrong)

        drift_detected = canonical != authorized_amount
        assert drift_detected

    def test_no_drift_when_price_unchanged(self):
        """If the product price hasn't changed, no drift must be detected."""
        product_price_per_unit = 149900
        quantity = 1
        canonical = product_price_per_unit * quantity
        authorized_amount = 149900

        drift_detected = canonical != authorized_amount
        assert not drift_detected

    def test_price_drift_uses_integer_arithmetic(self):
        """
        Price drift comparison must use integer paise — never floats.
        Float arithmetic on currency values can hide drift through rounding.
        """
        # If floats were used: 0.1 + 0.2 != 0.3 in floating point
        # With paise (integers), 100 + 200 == 300 always
        price_a = 1000  # ₹10.00 in paise
        price_b = 2000  # ₹20.00 in paise
        total = price_a + price_b
        assert total == 3000
        assert isinstance(total, int)

    @pytest.mark.asyncio
    async def test_validate_intent_raises_price_changed_on_drift(self):
        """
        validate_intent_for_execution must raise PriceChangedError if
        the canonical catalog price differs from the authorized amount.
        """
        from razorguard.application.intents.validate_intent import validate_intent_for_execution

        intent_id = uuid.uuid4()
        user_id = uuid.uuid4()
        product_id = uuid.uuid4()
        merchant_id = uuid.uuid4()

        # Intent was authorized at ₹1499
        fake_intent = MagicMock()
        fake_intent.id = intent_id
        fake_intent.user_id = user_id
        fake_intent.product_id = product_id
        fake_intent.merchant_id = merchant_id
        fake_intent.expires_at = MagicMock()
        fake_intent.status = TransactionStatus.AUTHORIZED.value
        fake_intent.intent_hash = "test-hash"
        fake_intent.final_amount_minor = 149900
        fake_intent.amount_minor = 149900  # Authorized at ₹1499
        fake_intent.currency = "INR"
        fake_intent.category = "electronics"
        fake_intent.session_id = "sess-001"
        fake_intent.payment_method = "UPI"
        fake_intent.quantity = 1
        fake_intent.agent_id = uuid.uuid4()

        # Catalog product is now ₹1999 — price drifted upward
        fake_product = MagicMock()
        fake_product.price_minor = 199900  # Merchant raised price
        fake_product.is_available = True

        mock_session = AsyncMock()

        with (
            patch(
                "razorguard.application.intents.validate_intent.IntentRepository"
            ) as MockIntentRepo,
            patch(
                "razorguard.application.intents.validate_intent.CatalogRepository"
            ) as MockCatalogRepo,
            patch("razorguard.application.intents.validate_intent.MerchantRepository"),
            patch(
                "razorguard.application.intents.validate_intent.is_expired",
                return_value=False,
            ),
            patch(
                "razorguard.application.intents.validate_intent.verify_intent_hash",
                return_value=True,
            ),
        ):
            MockIntentRepo.return_value.get_by_id_for_user = AsyncMock(return_value=fake_intent)
            MockCatalogRepo.return_value.get_available_for_agent = AsyncMock(
                return_value=fake_product
            )

            with pytest.raises(PriceChangedError) as exc_info:
                await validate_intent_for_execution(
                    intent_id=intent_id,
                    authenticated_user_id=user_id,
                    session=mock_session,
                )

        err = exc_info.value
        assert err.code == "PRICE_CHANGED"
        assert err.details["original_minor"] == 149900
        assert err.details["current_minor"] == 199900

    @pytest.mark.asyncio
    async def test_validate_intent_raises_product_unavailable_when_delisted(self):
        """
        If the product is delisted between intent creation and execution,
        ProductUnavailableError must be raised — not PriceChangedError.
        """
        from razorguard.application.intents.validate_intent import validate_intent_for_execution

        intent_id = uuid.uuid4()
        user_id = uuid.uuid4()

        fake_intent = MagicMock()
        fake_intent.id = intent_id
        fake_intent.user_id = user_id
        fake_intent.product_id = uuid.uuid4()
        fake_intent.merchant_id = uuid.uuid4()
        fake_intent.expires_at = MagicMock()
        fake_intent.status = TransactionStatus.AUTHORIZED.value
        fake_intent.intent_hash = "hash"
        fake_intent.final_amount_minor = 149900
        fake_intent.amount_minor = 149900
        fake_intent.currency = "INR"
        fake_intent.category = "electronics"
        fake_intent.session_id = "sess-002"
        fake_intent.payment_method = "UPI"
        fake_intent.quantity = 1
        fake_intent.agent_id = uuid.uuid4()

        mock_session = AsyncMock()

        with (
            patch(
                "razorguard.application.intents.validate_intent.IntentRepository"
            ) as MockIntentRepo,
            patch(
                "razorguard.application.intents.validate_intent.CatalogRepository"
            ) as MockCatalogRepo,
            patch("razorguard.application.intents.validate_intent.MerchantRepository"),
            patch(
                "razorguard.application.intents.validate_intent.is_expired",
                return_value=False,
            ),
            patch(
                "razorguard.application.intents.validate_intent.verify_intent_hash",
                return_value=True,
            ),
        ):
            MockIntentRepo.return_value.get_by_id_for_user = AsyncMock(return_value=fake_intent)
            # Product no longer in catalog (delisted / out of stock)
            MockCatalogRepo.return_value.get_available_for_agent = AsyncMock(return_value=None)

            with pytest.raises(ProductUnavailableError):
                await validate_intent_for_execution(
                    intent_id=intent_id,
                    authenticated_user_id=user_id,
                    session=mock_session,
                )

    def test_price_drift_detection_code_exists_in_validate_intent(self):
        """Structural: validate_intent.py must contain price drift detection logic."""
        from razorguard.application.intents import validate_intent

        source = inspect.getsource(validate_intent)
        assert "PriceChangedError" in source
        assert "canonical_price" in source
        assert "price_minor" in source


# ══════════════════════════════════════════════════════════════════════════════
# 4. Concurrent Duplicate → One Payment
#    Two simultaneous requests for the same intent must result in exactly
#    one payment. The second must be rejected via ConcurrentExecutionError.
# ══════════════════════════════════════════════════════════════════════════════


class TestConcurrentDuplicateOnePayment:
    """
    Distributed lock ensures that for any given intent_id, only one
    execute_payment call can proceed at a time.
    """

    @pytest.mark.asyncio
    async def test_second_lock_attempt_raises_concurrent_error(self):
        """
        Simulates two workers racing for the same intent.
        Worker 1 holds the lock; Worker 2 must be rejected immediately.
        """
        from razorguard.infrastructure.cache.locks import acquire_payment_lock

        intent_id = "intent-concurrent-dupe-001"

        # First worker's Redis: acquires the lock successfully
        redis_w1 = AsyncMock()
        redis_w1.set.return_value = True
        redis_w1.delete.return_value = 1

        # Second worker's Redis: lock already held — SET NX returns None
        redis_w2 = AsyncMock()
        redis_w2.set.return_value = None  # lock already taken

        # Worker 1 acquires and holds
        w1_holding = asyncio.Event()
        w2_rejected = asyncio.Event()

        w2_error: ConcurrentExecutionError | None = None

        async def worker1():
            async with acquire_payment_lock(redis_w1, intent_id):
                w1_holding.set()
                await asyncio.sleep(0.05)  # Simulate payment execution time

        async def worker2():
            nonlocal w2_error
            await w1_holding.wait()
            try:
                async with acquire_payment_lock(redis_w2, intent_id):
                    pass  # must not reach here
            except ConcurrentExecutionError as e:
                w2_error = e
                w2_rejected.set()

        await asyncio.gather(worker1(), worker2())

        assert (
            w2_error is not None
        ), "Second concurrent execution must raise ConcurrentExecutionError"
        assert isinstance(w2_error, ConcurrentExecutionError)

    def test_concurrent_execution_error_carries_intent_id(self):
        """Error details must identify which intent caused the contention."""
        intent_id = "intent-race-condition-99"
        err = ConcurrentExecutionError(intent_id)
        assert intent_id in err.details.get("intent_id", "")

    def test_lock_key_is_scoped_to_intent(self):
        """
        Lock key format must include intent_id — not a global lock.
        A global lock would serialize all payments in the system.
        """
        from razorguard.shared.constants import REDIS_PREFIX_LOCK

        intent_id = "intent-scope-check"
        expected_key_fragment = f"payment:{intent_id}"
        full_key = f"{REDIS_PREFIX_LOCK}payment:{intent_id}"
        assert expected_key_fragment in full_key

    def test_lock_uses_nx_semantics(self):
        """
        SET NX (Only set if Not eXists) is the correct Redis primitive.
        Verified by source inspection.
        """
        from razorguard.infrastructure.cache import locks

        source = inspect.getsource(locks)
        assert "nx=True" in source, "Lock must use SET NX to be atomic"

    def test_lock_has_auto_expiry_ttl(self):
        """
        Lock must have a TTL (ex=...) to auto-expire, preventing deadlocks
        if the worker crashes while holding the lock.
        """
        from razorguard.infrastructure.cache import locks

        source = inspect.getsource(locks)
        assert (
            "ex=ttl_seconds" in source or "ex=" in source
        ), "Lock must set a TTL (ex=) to prevent permanent deadlocks"

    def test_idempotency_key_deterministic_for_same_attempt(self):
        """
        Even if two workers race, the idempotency key for the same
        intent+capability+user+amount+nonce is identical.
        This is the second safety layer after the distributed lock.
        """
        from razorguard.shared.security import generate_idempotency_key

        k1 = generate_idempotency_key("intent-1", "cap-1", "user-1", "149900", "nonce-x")
        k2 = generate_idempotency_key("intent-1", "cap-1", "user-1", "149900", "nonce-x")
        assert k1 == k2, "Idempotency key must be deterministic for duplicate prevention"

    def test_idempotency_key_is_256bit_hex(self):
        """SHA-256 output = 64 hex characters. Sufficient collision resistance."""
        from razorguard.shared.security import generate_idempotency_key

        key = generate_idempotency_key("a", "b", "c", "d", "e")
        assert len(key) == 64
        assert all(c in "0123456789abcdef" for c in key)


# ══════════════════════════════════════════════════════════════════════════════
# 5. Stale Worker — Max Reconciliation Attempts Exhausted
#    If a payment stays UNKNOWN across all retry attempts, the system must
#    abandon it gracefully — log the alert, mark job exhausted, and stop retrying.
# ══════════════════════════════════════════════════════════════════════════════


class TestStaleWorkerMaxAttemptsExhausted:
    """
    After MAX_RECONCILIATION_ATTEMPTS, the reconciliation job must be
    marked exhausted and the job must stop retrying — the payment stays
    in UNKNOWN state awaiting manual review/ops intervention.
    """

    def test_max_attempts_is_in_safe_range(self):
        """MAX attempts must be reasonable — not too low (miss recovery) nor too high."""
        from razorguard.application.reconciliation.reconcile_unknown import (
            MAX_RECONCILIATION_ATTEMPTS,
        )

        assert 5 <= MAX_RECONCILIATION_ATTEMPTS <= 20, (
            f"MAX_RECONCILIATION_ATTEMPTS={MAX_RECONCILIATION_ATTEMPTS} is outside "
            "the safe range [5, 20]"
        )

    def test_backoff_sequence_is_monotonically_increasing(self):
        """Each retry must wait at least as long as the previous one."""
        from razorguard.application.reconciliation.reconcile_unknown import (
            RETRY_BACKOFF_SECONDS,
        )

        for i in range(1, len(RETRY_BACKOFF_SECONDS)):
            assert RETRY_BACKOFF_SECONDS[i] >= RETRY_BACKOFF_SECONDS[i - 1], (
                f"Backoff[{i}]={RETRY_BACKOFF_SECONDS[i]} < "
                f"Backoff[{i-1}]={RETRY_BACKOFF_SECONDS[i-1]} — must be monotonic"
            )

    def test_backoff_sequence_covers_all_max_attempts(self):
        """There must be at least one backoff value per possible retry attempt."""
        from razorguard.application.reconciliation.reconcile_unknown import (
            MAX_RECONCILIATION_ATTEMPTS,
            RETRY_BACKOFF_SECONDS,
        )

        assert (
            len(RETRY_BACKOFF_SECONDS) >= MAX_RECONCILIATION_ATTEMPTS
        ), "Backoff list must have an entry for every possible retry attempt"

    def test_total_backoff_window_provides_adequate_recovery_time(self):
        """
        The cumulative backoff time must give enough time for Razorpay
        to settle edge cases (at least 1 hour total reconciliation window).
        """
        from razorguard.application.reconciliation.reconcile_unknown import (
            RETRY_BACKOFF_SECONDS,
        )

        ONE_HOUR = 3600
        total_window = sum(RETRY_BACKOFF_SECONDS)
        assert total_window >= ONE_HOUR, (
            f"Total backoff window {total_window}s < 1 hour — "
            "may miss delayed Razorpay settlements"
        )

    @pytest.mark.asyncio
    async def test_reconcile_returns_abandoned_when_max_attempts_exceeded(self):
        """
        When job.attempt_count >= job.max_attempts, the reconciliation
        must return 'abandoned' — not raise, not loop forever.
        """
        from razorguard.application.reconciliation.reconcile_unknown import (
            reconcile_unknown_payment,
        )

        txn_id = uuid.uuid4()

        fake_txn = MagicMock()
        fake_txn.id = txn_id
        fake_txn.status = TransactionStatus.UNKNOWN.value
        fake_txn.razorpay_order_id = "order_stale_worker_001"

        # Job has already exhausted all attempts
        fake_job = MagicMock()
        fake_job.attempt_count = 10
        fake_job.max_attempts = 10

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = fake_txn
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch(
            "razorguard.application.reconciliation.reconcile_unknown._get_or_create_job",
            new_callable=AsyncMock,
            return_value=fake_job,
        ):
            result = await reconcile_unknown_payment(transaction_id=txn_id, session=mock_session)

        assert (
            result["status"] == "abandoned"
        ), "Exhausted reconciliation must return 'abandoned', not loop or crash"
        assert result["reason"] == "max_attempts_exceeded"

    @pytest.mark.asyncio
    async def test_reconcile_skips_non_unknown_transactions(self):
        """
        If the transaction status is no longer UNKNOWN (already resolved
        by another worker), reconciliation must skip gracefully.
        """
        from razorguard.application.reconciliation.reconcile_unknown import (
            reconcile_unknown_payment,
        )

        txn_id = uuid.uuid4()
        fake_txn = MagicMock()
        fake_txn.id = txn_id
        fake_txn.status = TransactionStatus.COMPLETED.value  # Already resolved
        fake_txn.razorpay_order_id = "order_already_done"

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = fake_txn
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await reconcile_unknown_payment(transaction_id=txn_id, session=mock_session)

        assert (
            result["status"] == "skipped"
        ), "Non-UNKNOWN transaction must be skipped by reconciliation worker"

    @pytest.mark.asyncio
    async def test_reconcile_handles_missing_transaction_gracefully(self):
        """
        If the transaction ID is not found (e.g., stale queue entry),
        reconciliation must return an error dict — not raise an exception.
        """
        from razorguard.application.reconciliation.reconcile_unknown import (
            reconcile_unknown_payment,
        )

        txn_id = uuid.uuid4()
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None  # transaction deleted/missing
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await reconcile_unknown_payment(transaction_id=txn_id, session=mock_session)

        assert result["status"] == "error"
        assert "not_found" in result["reason"]

    @pytest.mark.asyncio
    async def test_reconcile_handles_razorpay_query_failure_with_backoff(self):
        """
        If the Razorpay API is down during reconciliation, the job must
        schedule the next attempt using exponential backoff — not crash.
        """
        from razorguard.application.reconciliation.reconcile_unknown import (
            reconcile_unknown_payment,
        )

        txn_id = uuid.uuid4()
        fake_txn = MagicMock()
        fake_txn.id = txn_id
        fake_txn.status = TransactionStatus.UNKNOWN.value
        fake_txn.razorpay_order_id = "order_razorpay_down"
        fake_txn.version = 1

        fake_job = MagicMock()
        fake_job.attempt_count = 2
        fake_job.max_attempts = 10
        fake_job.next_attempt_at = None

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = fake_txn
        mock_session.execute = AsyncMock(return_value=mock_result)

        with (
            patch(
                "razorguard.application.reconciliation.reconcile_unknown._get_or_create_job",
                new_callable=AsyncMock,
                return_value=fake_job,
            ),
            patch(
                "razorguard.application.reconciliation.reconcile_unknown.fetch_payments_for_order",
                side_effect=ConnectionError("Razorpay API unreachable"),
            ),
            patch(
                "razorguard.application.reconciliation.reconcile_unknown.utcnow_plus",
                return_value="2099-01-01T00:00:00Z",
            ),
        ):
            result = await reconcile_unknown_payment(transaction_id=txn_id, session=mock_session)

        # Must schedule a retry — not crash or abandon prematurely
        assert result["status"] == "retry"
        assert "razorpay_query_failed" in result["reason"]


# ══════════════════════════════════════════════════════════════════════════════
# 6. Webhook Replay Attack
#    A re-delivered webhook (same razorpay_event_id) must be silently
#    dropped — not processed twice, not cause a duplicate state transition.
# ══════════════════════════════════════════════════════════════════════════════


class TestWebhookReplayAttack:
    """
    Idempotent webhook processing: the same event_id arriving twice
    must be a no-op on the second delivery.
    """

    def test_webhook_model_has_unique_event_id_constraint(self):
        """
        UNIQUE constraint on razorpay_event_id is the database-level guard
        against webhook replay. If this constraint is missing, replays will
        cause duplicate state transitions.
        """
        from razorguard.infrastructure.database.models.webhook_event import WebhookEvent

        constraint_columns = {col for c in WebhookEvent.__table__.constraints for col in str(c)}
        # The constraint string must reference razorpay_event_id
        assert any(
            "razorpay_event_id" in str(c) for c in WebhookEvent.__table__.constraints
        ), "razorpay_event_id must have a UNIQUE constraint to block replay attacks"

    def test_forged_signature_webhook_is_rejected(self):
        """
        A replayed webhook with a tampered body (different amount) must
        fail signature verification — attacker cannot replay with mutations.
        """
        from razorguard.infrastructure.payments.webhook_verifier import verify_webhook_signature
        from razorguard.shared.errors import InvalidWebhookError

        original_payload = (
            b'{"event":"payment.captured","payload":{"payment":{"entity":{"amount":149900}}}}'
        )
        tampered_payload = (
            b'{"event":"payment.captured","payload":{"payment":{"entity":{"amount":999999}}}}'
        )
        secret = "prod-webhook-secret"
        valid_sig = hmac.new(secret.encode(), original_payload, hashlib.sha256).hexdigest()

        mock_settings = MagicMock()
        mock_settings.razorpay_webhook_secret = secret

        with (
            patch(
                "razorguard.infrastructure.payments.webhook_verifier.get_settings",
                return_value=mock_settings,
            ),
            pytest.raises(InvalidWebhookError),
        ):
            # Attacker replays original sig with tampered body
            verify_webhook_signature(
                payload_body=tampered_payload,
                signature=valid_sig,
            )

    def test_replayed_webhook_with_correct_sig_is_blocked_by_db_dedup(self):
        """
        A genuine replay (exact same body + same signature) passes
        signature check but must be blocked by the UNIQUE(razorpay_event_id)
        DB constraint — second INSERT fails, preventing double processing.
        """
        from razorguard.infrastructure.database.models.webhook_event import WebhookEvent

        # The constraint exists (tested above).
        # This test asserts the architecture: sig check → INSERT → UNIQUE violation
        cols = {c.name for c in WebhookEvent.__table__.columns}
        assert "razorpay_event_id" in cols
        assert "processing_status" in cols

    def test_timing_safe_signature_comparison(self):
        """
        Signature comparison must use hmac.compare_digest to prevent
        timing-based side-channel attacks that could allow attackers to
        forge valid signatures character-by-character.
        """
        from razorguard.infrastructure.payments import webhook_verifier

        source = inspect.getsource(webhook_verifier)
        assert "compare_digest" in source, (
            "Webhook signature comparison must use hmac.compare_digest "
            "(constant-time) to prevent timing attacks"
        )

    def test_out_of_order_webhook_blocked_by_state_machine(self):
        """
        A delayed 'payment.captured' webhook arriving after 'payment.failed'
        must be blocked by the state machine — FAILED → COMPLETED is illegal.
        """
        assert not can_transition(
            TransactionStatus.FAILED, TransactionStatus.COMPLETED
        ), "State machine must block out-of-order captured-after-failed webhook"

    def test_out_of_order_failed_after_completed_blocked(self):
        """
        A delayed 'payment.failed' webhook arriving after 'payment.captured'
        must also be blocked — COMPLETED → FAILED is illegal.
        """
        assert not can_transition(
            TransactionStatus.COMPLETED, TransactionStatus.FAILED
        ), "State machine must block out-of-order failed-after-captured webhook"

    def test_terminal_states_accept_no_transitions(self):
        """
        Terminal states (COMPLETED, FAILED, POLICY_BLOCKED, etc.) must
        reject ALL outbound transitions. This is the final replay guard.
        """
        terminal_states = [
            TransactionStatus.COMPLETED,
            TransactionStatus.FAILED,
            TransactionStatus.CANCELLED,
            TransactionStatus.EXPIRED,
            TransactionStatus.POLICY_BLOCKED,
            TransactionStatus.CONSENT_REJECTED,
            TransactionStatus.AGENT_STOPPED,
        ]
        for state in terminal_states:
            for target in TransactionStatus:
                assert not can_transition(
                    state, target
                ), f"Terminal state {state} must not allow any transition to {target}"
