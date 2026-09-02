"""
Unit tests — Phase 13: control plane APIs (security dashboard counters).
"""

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
