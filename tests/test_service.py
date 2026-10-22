from __future__ import annotations

import unittest
from datetime import datetime
from unittest.mock import patch

from antigravity_usage_supervisor.account import AccountLimitsError
from antigravity_usage_supervisor.metrics import (
    DashboardMetrics,
    RateLimits,
    RateWindow,
    SessionMetric,
    TokenUsage,
)
from antigravity_usage_supervisor.service import collect_summary, metrics_summary


class ServiceContractTest(unittest.TestCase):
    def test_summary_contract_contains_only_desktop_fields(self) -> None:
        now = datetime.now().astimezone()
        metric = SessionMetric(
            session_id="id",
            name="Example task",
            cwd="/work/planner",
            model="Gemini 4 Argon (Medium)",
            updated_at=now,
            turns=3,
            usage=TokenUsage(total_tokens=12_345),
            status="CASCADE_RUN_STATUS_RUNNING",
        )
        result = metrics_summary(
            DashboardMetrics(
                sessions=[metric],
                today_tokens=12_345,
                week_tokens=54_321,
                today_minutes=25,
                today_sessions=1,
                generated_at=now,
                active_model="Gemini 4 Argon (Medium)",
                account_email="owen@example.com",
            )
        )
        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(result["recent"][0]["project"], "planner")
        self.assertEqual(result["today"]["focus_minutes"], 25)
        self.assertEqual(result["rate_limits_source"], "local-session")
        self.assertEqual(result["account_email"], "owen@example.com")
        self.assertNotIn("content", str(result).lower())

    def test_account_limits_override_cached_snapshot(self) -> None:
        now = datetime.now().astimezone()
        cached = RateLimits(
            plan_type="Google AI Pro",
            primary=RateWindow(used_percent=5.0, window_minutes=300, resets_at=None),
            secondary=None,
            observed_at=now,
        )
        live = RateLimits(
            plan_type="Google AI Pro",
            primary=RateWindow(used_percent=18.5, window_minutes=300, resets_at=None),
            secondary=None,
            observed_at=now,
        )
        metrics = DashboardMetrics(
            sessions=[],
            today_tokens=0,
            week_tokens=0,
            today_minutes=0,
            today_sessions=0,
            generated_at=now,
        )

        result = metrics_summary(metrics, live, cached)
        self.assertEqual(result["rate_limits"]["primary"]["used_percent"], 18.5)
        self.assertEqual(result["rate_limits_source"], "cloudcode-api")

    @patch("antigravity_usage_supervisor.service.load_network_limits")
    @patch("antigravity_usage_supervisor.service.fetch_account_rate_limits")
    @patch("antigravity_usage_supervisor.service.collect_metrics")
    def test_collect_summary_falls_back_when_account_refresh_fails(
        self,
        collect_metrics_mock,
        fetch_account_rate_limits_mock,
        load_network_limits_mock,
    ) -> None:
        now = datetime.now().astimezone()
        collect_metrics_mock.return_value = DashboardMetrics(
            sessions=[],
            today_tokens=0,
            week_tokens=0,
            today_minutes=0,
            today_sessions=0,
            generated_at=now,
        )
        load_network_limits_mock.return_value = None
        fetch_account_rate_limits_mock.side_effect = AccountLimitsError("offline")

        result = collect_summary()
        self.assertEqual(result["rate_limits_source"], "local-session")
        self.assertEqual(result["rate_limits_refresh_error"], "offline")


if __name__ == "__main__":
    unittest.main()
