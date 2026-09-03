"""
Unit tests — Phase 13: control plane APIs (security dashboard counters).
"""

import pytest

from razorguard.infrastructure.observability.metrics import policy_blocks
from razorguard.interfaces.http.routes.security import _counter_total


class TestSecurityDashboardCounters:
    def test_counter_total_is_non_negative(self):
        assert _counter_total(policy_blocks) >= 0

    def test_dashboard_schema_fields(self):
        from razorguard.interfaces.http.routes.security import SecurityDashboardResponse

        fields = set(SecurityDashboardResponse.model_fields)
        assert "policy_violations_blocked" in fields
        assert "prompt_injections_detected" in fields
        assert "webhook_replays_rejected" in fields

    @pytest.mark.asyncio
    async def test_development_demo_seed_populates_each_dashboard_counter(self):
        from razorguard.interfaces.http.routes import security

        before = await security.security_dashboard()
        after = await security.seed_demo_security_signals()

        assert after.policy_violations_blocked == before.policy_violations_blocked + 2
        assert after.duplicate_payments_prevented == before.duplicate_payments_prevented + 1
        assert after.expired_capabilities_rejected == before.expired_capabilities_rejected + 1
        assert after.prompt_injections_detected == before.prompt_injections_detected + 2
        assert after.unknown_payments_reconciled == before.unknown_payments_reconciled + 1
        assert after.webhook_replays_rejected == before.webhook_replays_rejected + 1
