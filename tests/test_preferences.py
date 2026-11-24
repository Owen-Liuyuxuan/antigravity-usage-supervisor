"""Build the actual GTK window to catch desktop API compatibility failures."""
import os
import unittest

try:
    from antigravity_usage_supervisor.preferences import PreferencesApplication
except ImportError:
    PreferencesApplication = None


@unittest.skipUnless(PreferencesApplication and os.environ.get("DISPLAY"), "GTK display required")
class PreferencesTest(unittest.TestCase):
    def test_window_builds_and_populates_details(self):
        app = PreferencesApplication()
        from gi.repository import Gio
        app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
        app.register(None)
        app._connect_service_and_load = lambda: None
        app.activate()
        try:
            self.assertFalse(hasattr(app, "_gemini_argon_7d_row"))
            self.assertIsNotNone(app._gemini_5h_row)
            self.assertIsNotNone(app._gemini_7d_row)
            self.assertIsNotNone(app._claude_5h_row)
            self.assertIsNotNone(app._claude_7d_row)
            self.assertEqual(len(app._activity_rows), 5)
            app._apply_summary({
                "today": {"sessions": 2, "tokens": 12345, "focus_minutes": 20},
                "week": {"tokens": 54321},
                "rate_limits_source": "cloudcode-api",
                "rate_limits": {
                    "primary": {"bucket_id": "gemini-5h", "used_percent": 1.5, "remaining_percent": 98.5},
                    "gemini_5h": {"used_percent": 1.5, "remaining_percent": 98.5},
                    "gemini_weekly": {"used_percent": 99.19, "remaining_percent": 0.81},
                    "claude_gpt_5h": {"used_percent": 0.0, "remaining_percent": 100.0},
                    "claude_gpt_weekly": {"used_percent": 5.0, "remaining_percent": 95.0},
                },
                "recent": [{"name": "Task & quota", "tokens": 42}],
            })
            self.assertIn("98.5% left", app._gemini_5h_row.value_label.get_label())
            self.assertIn("0.81% left", app._gemini_7d_row.value_label.get_label())
            self.assertIn("100% left", app._claude_5h_row.value_label.get_label())
            self.assertIn("95% left", app._claude_7d_row.value_label.get_label())
            self.assertEqual(app._activity_rows["tokens"].get_subtitle(), "12,345")
            self.assertEqual(len(app._recent_rows), 1)
            self.assertIn("Task", app._recent_rows[0].get_title())
        finally:
            if app.get_active_window():
                app.get_active_window().destroy()
