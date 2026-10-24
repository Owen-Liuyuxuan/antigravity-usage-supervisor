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
                {
                    "displayName": "Gemini 4 Argon",
                    "buckets": [
                        {
                            "bucketId": "gemini-argon-wtu-weekly",
                            "window": "weekly",
                            "remainingFraction": 0.25,
                            "resetTime": "2026-10-29T05:14:17Z",
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
        # When Gemini 4 Argon is the active model, primary is the Gemini 4 Argon weekly limit
        self.assertIsNotNone(limits.primary)
        self.assertEqual(limits.primary.used_percent, 75.0)
        self.assertEqual(limits.primary.window_minutes, 10080)
        self.assertEqual(limits.primary.bucket_id, "gemini-argon-wtu-weekly")
        self.assertIsNotNone(limits.gemini_argon_weekly)
        self.assertEqual(limits.gemini_argon_weekly.used_percent, 75.0)
        self.assertIsNotNone(limits.gemini_weekly)
        self.assertEqual(limits.gemini_weekly.used_percent, 10.0)
        self.assertEqual(limits.gemini_weekly.window_minutes, 10080)
        self.assertEqual(limits.gemini_weekly.bucket_id, "gemini-weekly")
        self.assertIsNotNone(limits.claude_gpt_weekly)
        self.assertEqual(limits.claude_gpt_weekly.used_percent, 5.0)
        self.assertEqual(limits.claude_gpt_weekly.window_minutes, 10080)
        self.assertEqual(limits.claude_gpt_weekly.bucket_id, "3p-weekly")
        self.assertEqual(len(limits.groups), 3)
        argon_group = next(g for g in limits.groups if g.group_id == "gemini_argon")
        self.assertIsNotNone(argon_group.weekly)
        self.assertEqual(argon_group.weekly.used_percent, 75.0)
        gemini_group = next(g for g in limits.groups if g.group_id == "gemini")
        self.assertIsNotNone(gemini_group.five_hour)
        self.assertEqual(gemini_group.five_hour.used_percent, 0.0)
        self.assertIsNotNone(gemini_group.weekly)
        self.assertEqual(gemini_group.weekly.used_percent, 10.0)
        claude_group = next(g for g in limits.groups if g.group_id == "claude_gpt")
        self.assertIsNone(claude_group.five_hour)

        # When active model is standard Gemini Flash/Pro, primary is gemini-5h
        flash_limits = parse_cloudcode_quota(
            load_response=load_resp,
            quota_response=quota_resp,
            summary_response=summary_resp,
            account_email="owen@example.com",
            active_model="Gemini 3.8 Flash",
            observed_at=datetime(2026, 10, 22, 6, 0, tzinfo=timezone.utc),
        )
        self.assertIsNotNone(flash_limits.primary)
        self.assertEqual(flash_limits.primary.bucket_id, "gemini-5h")
        self.assertEqual(flash_limits.primary.used_percent, 0.0)

    def test_argon_low_remaining_and_summary_authority(self) -> None:
        from antigravity_usage_supervisor.network_cache import limits_dict

        def bucket(bucket_id, fraction, window="weekly"):
            return {"bucketId": bucket_id, "remainingFraction": fraction,
                    "window": window, "resetTime": "2026-10-29T05:14:17Z"}

        summary = {"groups": [
            {"displayName": "Gemini 4 Argon", "buckets": [bucket("gemini-argon-wtu-weekly", 0.0080972)]},
            {"displayName": "Gemini Models", "buckets": [
                bucket("gemini-weekly", 0.9874851), bucket("gemini-5h", 1.0, "5h")]},
            {"displayName": "Claude and GPT models", "buckets": [
                bucket("3p-weekly", 1.0), bucket("3p-5h", 1.0, "5h")]},
        ]}
        # A conflicting model snapshot must not overwrite the explicit groups.
        per_model = {"buckets": [
            {"modelId": "gemini-4-argon-medium", "remainingFraction": 0.001},
            {"modelId": "gemini-3.8-flash", "remainingFraction": 0.1},
        ]}
        limits = parse_cloudcode_quota({}, per_model, summary, active_model="Claude Sonnet")
        data = limits_dict(limits)
        self.assertEqual(data["gemini_argon_weekly"]["remaining_percent"], 0.81)
        self.assertEqual(data["gemini_weekly"]["remaining_percent"], 98.75)
        self.assertEqual(data["gemini_5h"]["remaining_percent"], 100.0)
        self.assertEqual(data["claude_gpt_5h"]["remaining_percent"], 100.0)
        self.assertEqual(len(data["groups"]), 3)

    def test_serialization_does_not_relabel_claude_primary_as_gemini(self) -> None:
        from antigravity_usage_supervisor.network_cache import limits_dict

        limits = parse_cloudcode_quota({}, {"buckets": [
            {"modelId": "claude-sonnet", "remainingFraction": 0.5}
        ]}, active_model="Claude Sonnet")
        data = limits_dict(limits)
        self.assertIsNone(data["gemini_5h"])
        self.assertIsNone(data["gemini_argon_weekly"])
        self.assertEqual(data["claude_gpt_5h"]["used_percent"], 50.0)

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
