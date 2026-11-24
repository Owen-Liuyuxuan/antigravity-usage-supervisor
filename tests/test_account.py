from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from antigravity_usage_supervisor.account import (
    AccountLimitsError,
    parse_cloudcode_quota,
    parse_user_status_response,
)
from antigravity_usage_supervisor.network_cache import limits_dict, load_network_limits


class AccountLimitsTest(unittest.TestCase):
    def test_all_gemini_models_including_argon_and_carbon_share_gemini_group(self) -> None:
        summary = {"groups": [
            {"displayName": "Gemini Models", "buckets": [
                {"bucketId": "gemini-5h", "window": "5h", "remainingFraction": 0.9},
                {"bucketId": "gemini-weekly", "window": "weekly", "remainingFraction": 0.8},
            ]},
            {"displayName": "Claude and GPT models", "buckets": [
                {"bucketId": "3p-5h", "window": "5h", "remainingFraction": 1.0},
                {"bucketId": "3p-weekly", "window": "weekly", "remainingFraction": 0.95},
            ]},
        ]}
        for model in (
            "Gemini 4 Neon (Medium)",
            "Orchestrator (Neon)",
            "gemini-pro-orchestrator-neon",
            "Gemini 4 Carbon (High)",
            "Orchestrator (Carbon)",
            "gemini-pro-orchestrator-carbon",
            "Gemini 4 Argon (Medium)",
            "Orchestrator (Argon)",
            "gemini-pro-orchestrator-argon",
            "gemini-pro-orchestrator-g1-pro",
            "Gemini 4 Hydrogen (XHigh)",
            "antigravity/gemini-4-hydrogen-low",
            "Gemini 3.8 Flash",
        ):
            with self.subTest(model=model):
                limits = parse_cloudcode_quota({}, {}, summary, active_model=model)
                self.assertEqual(limits.primary.bucket_id, "gemini-5h")
                self.assertEqual(limits.secondary.bucket_id, "gemini-weekly")
                self.assertEqual([g.group_id for g in limits.groups], ["gemini", "claude_gpt"])

    def test_per_model_fallback_maps_carbon_and_argon_to_shared_gemini(self) -> None:
        for model in (
            "gemini-4-carbon-high",
            "gemini-4-argon-medium",
            "gemini-4-hydrogen-low",
            "gemini-4-neon-medium",
            "gemini-pro-orchestrator-argon",
        ):
            with self.subTest(model=model):
                limits = parse_cloudcode_quota({}, {"buckets": [
                    {"modelId": model, "remainingFraction": 0.9},
                ]}, active_model=model)
                self.assertIsNone(limits.gemini_weekly)
                self.assertEqual(limits.primary.bucket_id, "gemini-5h")
                self.assertEqual(limits.primary.used_percent, 10.0)

    def test_language_server_fallback_shares_gemini_across_carbon_and_argon(self) -> None:
        for active in (
            "Gemini 4 Carbon (High)",
            "Orchestrator (Carbon)",
            "Gemini 4 Argon (Medium)",
            "Orchestrator (Argon)",
            "Gemini 4 Hydrogen (High)",
        ):
            with self.subTest(active=active):
                limits = parse_user_status_response({"userStatus": {"cascadeModelConfigData": {
                    "clientModelConfigs": [
                        {"label": "Gemini 4 Carbon (High)", "quotaInfo": {"remainingFraction": 0.8}},
                        {"label": "Gemini 4 Argon (Medium)", "quotaInfo": {"remainingFraction": 0.8}},
                        {"label": "Gemini 4 Hydrogen (High)", "quotaInfo": {"remainingFraction": 0.8}},
                        {"label": "Claude Sonnet 5.5 (High)", "quotaInfo": {"remainingFraction": 1.0}},
                    ]}}}, active_model=active)
                self.assertEqual(limits.primary.bucket_id, "gemini-5h")
                self.assertEqual(limits.primary.used_percent, 20.0)
                self.assertEqual([g.group_id for g in limits.groups], ["gemini", "claude_gpt"])

    def test_parses_google_ai_pro_cloudcode_quota(self) -> None:
        load_resp = {
            "paidTier": {"id": "g1-pro-tier", "name": "Google AI Pro"},
            "cloudaicompanionProject": "aicode-consumers",
        }
        quota_resp = {
            "buckets": [
                {
                    "modelId": "gemini-4-carbon-high",
                    "remainingFraction": 0.995,
                    "resetTime": "2026-11-24T10:51:06Z",
                },
                {
                    "modelId": "gemini-4-argon-medium",
                    "remainingFraction": 0.995,
                    "resetTime": "2026-11-24T10:51:06Z",
                },
                {
                    "modelId": "claude-sonnet-5-5-high",
                    "remainingFraction": 0.88,
                    "resetTime": "2026-11-24T11:15:00Z",
                },
            ]
        }
        summary_resp = {
            "groups": [
                {
                    "displayName": "Gemini Models",
                    "description": "Models within this group: Gemini 4 Neon, Gemini 4 Carbon, Gemini 4 Argon, Gemini 4 Hydrogen, Orchestrator (Neon), Orchestrator (Carbon), Orchestrator (Argon), Gemini 3.8 Flash",
                    "buckets": [
                        {
                            "bucketId": "gemini-weekly",
                            "window": "weekly",
                            "remainingFraction": 0.9,
                            "resetTime": "2026-12-01T06:00:00Z",
                        },
                        {
                            "bucketId": "gemini-5h",
                            "window": "5h",
                            "remainingFraction": 0.99,
                            "resetTime": "2026-11-24T10:51:06Z",
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
                            "resetTime": "2026-12-01T06:00:00Z",
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
            active_model="Gemini 4 Carbon (High)",
            observed_at=datetime(2026, 11, 24, 6, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(limits.plan_type, "Google AI Pro")
        self.assertEqual(limits.account_email, "owen@example.com")
        self.assertIsNotNone(limits.primary)
        self.assertEqual(limits.primary.used_percent, 1.0)
        self.assertEqual(limits.primary.window_minutes, 300)
        self.assertEqual(limits.primary.bucket_id, "gemini-5h")
        self.assertIsNotNone(limits.secondary)
        self.assertEqual(limits.secondary.bucket_id, "gemini-weekly")
        self.assertIsNotNone(limits.gemini_weekly)
        self.assertEqual(limits.gemini_weekly.used_percent, 10.0)
        self.assertEqual(limits.gemini_weekly.window_minutes, 10080)
        self.assertIsNotNone(limits.claude_gpt_weekly)
        self.assertEqual(limits.claude_gpt_weekly.used_percent, 5.0)
        self.assertEqual(limits.claude_gpt_weekly.window_minutes, 10080)
        self.assertEqual(limits.claude_gpt_weekly.bucket_id, "3p-weekly")
        self.assertEqual(len(limits.groups), 2)
        gemini_group = next(g for g in limits.groups if g.group_id == "gemini")
        self.assertIsNotNone(gemini_group.five_hour)
        self.assertEqual(gemini_group.five_hour.used_percent, 1.0)
        self.assertIsNotNone(gemini_group.weekly)
        self.assertEqual(gemini_group.weekly.used_percent, 10.0)
        claude_group = next(g for g in limits.groups if g.group_id == "claude_gpt")
        self.assertIsNone(claude_group.five_hour)

    def test_summary_authority_and_low_remaining_precision(self) -> None:
        def bucket(bucket_id, fraction, window="weekly"):
            return {"bucketId": bucket_id, "remainingFraction": fraction,
                    "window": window, "resetTime": "2026-12-01T05:14:17Z"}

        summary = {"groups": [
            {"displayName": "Gemini Models", "buckets": [
                bucket("gemini-weekly", 0.9874851), bucket("gemini-5h", 0.0080972, "5h")]},
            {"displayName": "Claude and GPT models", "buckets": [
                bucket("3p-weekly", 1.0), bucket("3p-5h", 1.0, "5h")]},
        ]}
        # Conflicting per-model snapshots must not overwrite explicit groups.
        per_model = {"buckets": [
            {"modelId": "gemini-4-argon-medium", "remainingFraction": 0.5},
            {"modelId": "gemini-4-carbon-high", "remainingFraction": 0.5},
            {"modelId": "gemini-3.8-flash", "remainingFraction": 0.1},
        ]}
        limits = parse_cloudcode_quota({}, per_model, summary, active_model="Claude Sonnet")
        self.assertEqual(limits.primary.bucket_id, "3p-5h")
        self.assertEqual(limits.secondary.bucket_id, "gemini-5h")
        data = limits_dict(limits)
        self.assertEqual(data["gemini_weekly"]["remaining_percent"], 98.75)
        self.assertEqual(data["gemini_5h"]["remaining_percent"], 0.81)
        self.assertEqual(data["claude_gpt_5h"]["remaining_percent"], 100.0)
        self.assertEqual(len(data["groups"]), 2)
        self.assertNotIn("gemini_argon_weekly", data)

    def test_serialization_does_not_relabel_claude_primary_as_gemini(self) -> None:
        limits = parse_cloudcode_quota({}, {"buckets": [
            {"modelId": "claude-sonnet", "remainingFraction": 0.5}
        ]}, active_model="Claude Sonnet")
        data = limits_dict(limits)
        self.assertIsNone(data["gemini_5h"])
        self.assertIsNone(data["gemini_weekly"])
        self.assertEqual(data["claude_gpt_5h"]["used_percent"], 50.0)

    def test_legacy_cache_with_argon_fields_loads_cleanly(self) -> None:
        legacy = {
            "schema_version": 1,
            "rate_limits": {
                "plan_type": "Google AI Pro",
                "primary": {"used_percent": 1.0, "window_minutes": 300, "bucket_id": "gemini-5h"},
                "secondary": {"used_percent": 2.0, "window_minutes": 10080, "bucket_id": "gemini-weekly"},
                "gemini_argon_weekly": {"used_percent": 50.0, "window_minutes": 10080, "bucket_id": "gemini-argon-wtu-weekly"},
                "gemini_weekly": {"used_percent": 2.0, "window_minutes": 10080, "bucket_id": "gemini-weekly"},
                "groups": [],
                "observed_at": "2026-11-24T06:00:00+00:00",
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cache.json"
            path.write_text(json.dumps(legacy), encoding="utf-8")
            loaded = load_network_limits(path)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.primary.bucket_id, "gemini-5h")
            self.assertEqual(loaded.gemini_weekly.used_percent, 2.0)

    def test_parses_language_server_user_status(self) -> None:
        payload = {
            "userStatus": {
                "email": "owen@example.com",
                "planStatus": {"planInfo": {"planName": "Google AI Pro"}},
                "cascadeModelConfigData": {
                    "clientModelConfigs": [
                        {
                            "label": "Gemini 4 Carbon (Medium)",
                            "quotaInfo": {
                                "remainingFraction": 0.85,
                                "resetTime": "2026-11-24T10:00:00Z",
                            },
                        },
                        {
                            "label": "Claude Sonnet 5.5 (High)",
                            "quotaInfo": {
                                "remainingFraction": 0.95,
                                "resetTime": "2026-11-24T10:00:00Z",
                            },
                        },
                    ]
                },
            }
        }
        limits = parse_user_status_response(payload, active_model="Gemini 4 Carbon (Medium)")
        self.assertEqual(limits.plan_type, "Google AI Pro")
        self.assertEqual(limits.primary.used_percent, 15.0)
        self.assertEqual(limits.secondary, None)
        claude_group = next(g for g in limits.groups if g.group_id == "claude_gpt")
        self.assertEqual(claude_group.five_hour.used_percent, 5.0)

    def test_rejects_empty_cloudcode_buckets(self) -> None:
        with self.assertRaisesRegex(AccountLimitsError, "no model quota buckets"):
            parse_cloudcode_quota({}, {"buckets": []}, {})


if __name__ == "__main__":
    unittest.main()
