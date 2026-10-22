from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from antigravity_usage_supervisor.config import Settings
from antigravity_usage_supervisor.metrics import collect_metrics


class MetricsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

        # Create annotations title
        annotations_dir = self.root / "annotations"
        annotations_dir.mkdir(parents=True)
        (annotations_dir / "main-conv.pbtxt").write_text(
            'title:"Build Antigravity Monitor"\n',
            encoding="utf-8",
        )

        # Create CLI log with email, model, and workspace
        (self.root / "cli.log").write_text(
            'I1022 14:32:31.664421 288 server_oauth.go:229] OAuth: authenticated successfully as owen@example.com\n'
            'I1022 14:32:44.468859 288 model_config_manager.go:340] Propagating selected model override to backend: label="Gemini 4 Argon (Medium)"\n'
            'I1022 14:32:45.000000 288 workspace.go:32] Using workspace "/work/antigravity-monitor" from conversation main-conv\n',
            encoding="utf-8",
        )

        # Main conversation transcript
        main_logs = self.root / "brain" / "main-conv" / ".system_generated" / "logs"
        main_logs.mkdir(parents=True)
        main_steps = [
            {
                "index": 0,
                "source": "USER",
                "type": "USER_INPUT",
                "created_at": "2026-10-22T05:00:00Z",
                "content": "<USER_SETTINGS_CHANGE>\nThe user changed setting Model Selection from None to Gemini 4 Argon (Medium).\n</USER_SETTINGS_CHANGE>\nHello",
            },
            {
                "index": 1,
                "source": "MODEL",
                "type": "PLANNER_RESPONSE",
                "created_at": "2026-10-22T05:05:00Z",
                "input_tokens": 1000,
                "cache_read_tokens": 2000,
                "output_tokens": 300,
            },
            {
                "index": 2,
                "source": "USER",
                "type": "USER_INPUT",
                "created_at": "2026-10-22T05:10:00Z",
                "content": "Next step",
            },
            {
                "index": 3,
                "source": "MODEL",
                "type": "PLANNER_RESPONSE",
                "created_at": "2026-10-22T05:12:00Z",
                "input_tokens": 1500,
                "cache_read_tokens": 3000,
                "output_tokens": 200,
            },
        ]
        (main_logs / "transcript.jsonl").write_text(
            "\n".join(json.dumps(s) for s in main_steps) + "\n",
            encoding="utf-8",
        )

        # Subagent metadata & transcript
        sub_meta_dir = self.root / "brain" / "main-conv" / ".system_generated" / "subagents"
        sub_meta_dir.mkdir(parents=True)
        (sub_meta_dir / "sub-conv.json").write_text(
            json.dumps(
                {
                    "conversationId": "sub-conv",
                    "subagentDescriptor": {"typeName": "research", "role": "Quota Researcher"},
                    "workspaceUris": ["file:///work/antigravity-monitor"],
                }
            ),
            encoding="utf-8",
        )
        sub_logs = self.root / "brain" / "sub-conv" / ".system_generated" / "logs"
        sub_logs.mkdir(parents=True)
        sub_steps = [
            {
                "index": 0,
                "source": "USER",
                "type": "USER_INPUT",
                "created_at": "2026-10-22T05:06:00Z",
                "content": "Research quota",
            },
            {
                "index": 1,
                "source": "MODEL",
                "type": "PLANNER_RESPONSE",
                "created_at": "2026-10-22T05:08:00Z",
                "input_tokens": 500,
                "cache_read_tokens": 1000,
                "output_tokens": 500,
            },
        ]
        (sub_logs / "transcript.jsonl").write_text(
            "\n".join(json.dumps(s) for s in sub_steps) + "\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_collects_incremental_tokens_and_rolls_up_subagents(self) -> None:
        now = datetime.fromisoformat("2026-10-22T06:00:00+00:00")
        result = collect_metrics(self.root, now)
        # Main tokens: (1000+2000+300) + (1500+3000+200) = 3300 + 4700 = 8000
        # Subagent tokens: 500+1000+500 = 2000 -> total 10,000
        self.assertEqual(result.today_tokens, 10_000)
        self.assertEqual(result.week_tokens, 10_000)
        self.assertEqual(result.today_sessions, 1)
        self.assertEqual(len(result.sessions), 1)
        self.assertEqual(result.sessions[0].name, "Build Antigravity Monitor")
        self.assertEqual(result.sessions[0].turns, 2)
        self.assertEqual(result.sessions[0].usage.total_tokens, 10_000)
        self.assertEqual(result.sessions[0].model, "Gemini 4 Argon (Medium)")
        self.assertEqual(result.account_email, "owen@example.com")
        # Focus time from 05:00 to 05:12 (12m + 1m baseline = 13m)
        self.assertEqual(result.today_minutes, 13)

    def test_settings_validation_and_round_trip(self) -> None:
        path = self.root / "settings.json"
        Settings(10, 20, 1, 150, "~/custom-agy").validated().save(path)
        loaded = Settings.load(path)
        self.assertEqual(loaded.refresh_seconds, 5)
        self.assertEqual(loaded.notify_at_percent, 100)
        self.assertTrue(loaded.antigravity_home.endswith("custom-agy"))


if __name__ == "__main__":
    unittest.main()
