from __future__ import annotations

import unittest
from datetime import datetime, timezone

from antigravity_usage_supervisor.account import (
    AccountLimitsError,
    parse_cloudcode_quota,
    parse_user_status_response,
)


class AccountLimitsTest(unittest.TestCase):
    def test_parses_google_ai_pro_cloudcode_quota(self) -> None:
        load_resp = {
            "paidTier": {"id": "g1-pro-tier", "name": "Google AI Pro"},
            "cloudaicompanionProject": "aicode-consumers",
        }
        quota_resp = {
            "buckets": [
                {
                    "modelId": "gemini-3.8-flash-tiered",
                    "remainingFraction": 0.975,
                    "resetTime": "2026-10-22T10:51:06Z",
                },
                {
                    "modelId": "claude-sonnet-5-5-high",
                    "remainingFraction": 0.88,
                    "resetTime": "2026-10-22T11:15:00Z",
                },
            ]
        }
        summary_resp = {
            "groups": [
                {
                    "displayName": "Gemini Models",
                    "buckets": [
                        {
                            "bucketId": "gemini-weekly",
                            "window": "weekly",
                            "remainingFraction": 0.9,
                            "resetTime": "2026-10-29T06:00:00Z",
                        },
                        {
                            "bucketId": "gemini-5h",
                            "window": "5h",
                            "remainingFraction": 1.0,
                            "resetTime": "2026-10-22T10:51:06Z",
                        },
                    ],
                },
                {
                    "displayName": "Claude and GPT models",
                    "buckets": [
                        {
                            "bucketId": "3p-weekly",
                            "window": "weekly",
                            "remainingFraction": 0.95,
                            "resetTime": "2026-10-29T06:00:00Z",
                        }
                    ],
                },
            ]
        }

        limits = parse_cloudcode_quota(
            load_response=load_resp,
            quota_response=quota_resp,
            summary_response=summary_resp,
            account_email="owen@example.com",
            active_model="Gemini 4 Argon (Medium)",
            observed_at=datetime(2026, 10, 22, 6, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(limits.plan_type, "Google AI Pro")
        self.assertEqual(limits.account_email, "owen@example.com")
        self.assertIsNotNone(limits.primary)
        self.assertEqual(limits.primary.used_percent, 2.5)
        self.assertEqual(limits.primary.window_minutes, 300)
        self.assertIsNotNone(limits.secondary)
        self.assertEqual(limits.secondary.used_percent, 10.0)
        self.assertEqual(limits.secondary.window_minutes, 10080)
        self.assertEqual(len(limits.groups), 2)

    def test_parses_language_server_user_status(self) -> None:
        payload = {
            "userStatus": {
                "email": "owen@example.com",
                "planStatus": {"planInfo": {"planName": "Google AI Pro"}},
                "cascadeModelConfigData": {
                    "clientModelConfigs": [
                        {
                            "label": "Gemini 4 Argon (Medium)",
                            "quotaInfo": {
                                "remainingFraction": 0.85,
                                "resetTime": "2026-10-22T10:00:00Z",
                            },
                        },
                        {
                            "label": "Claude Sonnet 5.5 (High)",
                            "quotaInfo": {
                                "remainingFraction": 0.95,
                                "resetTime": "2026-10-22T10:00:00Z",
                            },
                        },
                    ]
                },
            }
        }
        limits = parse_user_status_response(payload, active_model="Gemini 4 Argon (Medium)")
        self.assertEqual(limits.plan_type, "Google AI Pro")
        self.assertEqual(limits.primary.used_percent, 15.0)
        self.assertEqual(limits.secondary.used_percent, 5.0)

    def test_rejects_empty_cloudcode_buckets(self) -> None:
        with self.assertRaisesRegex(AccountLimitsError, "no model quota buckets"):
            parse_cloudcode_quota({}, {"buckets": []}, {})


if __name__ == "__main__":
    unittest.main()
