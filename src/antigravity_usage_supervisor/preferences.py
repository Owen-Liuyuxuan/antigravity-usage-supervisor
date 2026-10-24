"""Libadwaita preferences and detail view for Antigravity Usage Supervisor."""

from __future__ import annotations

import json
import math
from datetime import datetime
from typing import Any

import gi

gi.require_version("Adw", "1")
gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

from .config import Settings
from .metrics import _timestamp
from .service import BUS_NAME, INTERFACE, OBJECT_PATH, collect_summary


def _format_percent(value: Any) -> str:
    try:
        num = float(value or 0.0)
    except (TypeError, ValueError):
        return "0%"
    if not math.isfinite(num):
        return "0%"
    return f"{num:.2f}".rstrip("0").rstrip(".") + "%"


def _reset_text(value: Any) -> str:
    parsed = _timestamp(value)
    if parsed is None:
        return "Reset time unavailable"
    now = datetime.now().astimezone()
    minutes = max(0, math.ceil((parsed - now).total_seconds() / 60.0))
    if minutes < 60:
        return f"Resets in {minutes} min"
    if minutes < 1440:
        return f"Resets in {minutes // 60}h {minutes % 60}m"
    return f"Resets in {minutes // 1440}d {(minutes % 1440) // 60}h"


class _QuotaLimitRow:
    def __init__(self, default_title: str) -> None:
        self.default_title = default_title
        self.row = Adw.ActionRow(title=GLib.markup_escape_text(default_title), subtitle="Waiting for usage data")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, valign=Gtk.Align.CENTER)
        self.value_label = Gtk.Label(label="—", xalign=1.0)
        self.value_label.add_css_class("heading")
        self.progress = Gtk.ProgressBar(valign=Gtk.Align.CENTER)
        self.progress.set_size_request(160, -1)
        box.append(self.value_label)
        box.append(self.progress)
        self.row.add_suffix(box)

    def update(self, window: dict[str, Any] | None, is_active: bool = False) -> None:
        if not isinstance(window, dict):
            self.row.set_title(GLib.markup_escape_text(self.default_title))
            self.row.set_subtitle("Not reported")
            self.value_label.set_label("Not reported")
            self.progress.set_fraction(0.0)
            return
        used = float(window.get("used_percent") or 0.0)
        rem_raw = window.get("remaining_percent")
        remaining = float(rem_raw) if rem_raw is not None else max(0.0, 100.0 - used)
        self.row.set_title(GLib.markup_escape_text(str(window.get("label") or self.default_title)))
        reset_str = _reset_text(window.get("resets_at"))
        self.row.set_subtitle(f"Indicator quota  ·  {reset_str}" if is_active else reset_str)
        self.value_label.set_label(f"{_format_percent(used)} used ({_format_percent(remaining)} left)")
        self.progress.set_fraction(min(1.0, max(0.0, used / 100.0)))


class PreferencesApplication(Adw.Application):
    def __init__(self) -> None:
        super().__init__(application_id="io.github.owen.AntigravityUsageSupervisor.Preferences")
        self.settings = Settings.load()
        self._quota_group: Adw.PreferencesGroup | None = None
        self._gemini_argon_7d_row: _QuotaLimitRow | None = None
        self._gemini_5h_row: _QuotaLimitRow | None = None
        self._gemini_7d_row: _QuotaLimitRow | None = None
        self._claude_5h_row: _QuotaLimitRow | None = None
        self._claude_7d_row: _QuotaLimitRow | None = None
        self._activity_rows: dict[str, Adw.ActionRow] = {}
        self._recent_group: Adw.PreferencesGroup | None = None
        self._recent_rows: list[Adw.ActionRow] = []
        self._bus: Gio.DBusConnection | None = None
        self._signal_id: int = 0

    def do_activate(self) -> None:
        existing = self.get_active_window()
        if existing:
            existing.present()
            return

        window = Adw.PreferencesWindow(application=self)
        window.set_title("Antigravity Usage Supervisor")
        window.set_default_size(620, 740)

        page = Adw.PreferencesPage(title="Details", icon_name="view-list-symbolic")
        window.add(page)

        self._quota_group = Adw.PreferencesGroup(
            title="Google AI Pro quota allowances",
            description="Gemini 4 Argon has a dedicated 7-day limit; Gemini Models and Claude &amp; GPT each have 5-hour and 7-day limits.",
        )
        refresh_btn = Gtk.Button(
            icon_name="view-refresh-symbolic",
            tooltip_text="Refresh quota allowances",
            valign=Gtk.Align.CENTER,
        )
        refresh_btn.add_css_class("flat")
        refresh_btn.connect("clicked", self._on_refresh_clicked)
        self._quota_group.set_header_suffix(refresh_btn)

        self._gemini_argon_7d_row = _QuotaLimitRow("7-day allowance (Gemini 4 Argon)")
        self._gemini_5h_row = _QuotaLimitRow("5-hour allowance (Gemini)")
        self._gemini_7d_row = _QuotaLimitRow("7-day allowance (Gemini)")
        self._claude_5h_row = _QuotaLimitRow("5-hour allowance (Claude & GPT)")
        self._claude_7d_row = _QuotaLimitRow("7-day allowance (Claude & GPT)")
        self._quota_group.add(self._gemini_argon_7d_row.row)
        self._quota_group.add(self._gemini_5h_row.row)
        self._quota_group.add(self._gemini_7d_row.row)
        self._quota_group.add(self._claude_5h_row.row)
        self._quota_group.add(self._claude_7d_row.row)
        page.add(self._quota_group)

        activity = Adw.PreferencesGroup(title="Local activity")
        page.add(activity)
        for key, title in (
            ("sessions", "Today's tasks"),
            ("focus_minutes", "Today's estimated focus time"),
            ("tokens", "Today's tokens"),
            ("week_tokens", "Tokens over the last 7 days"),
            ("source", "Quota data source"),
        ):
            row = Adw.ActionRow(title=title, subtitle="Waiting for data")
            activity.add(row)
            self._activity_rows[key] = row
        self._recent_group = Adw.PreferencesGroup(title="Recent tasks")
        page.add(self._recent_group)

        page = Adw.PreferencesPage(title="Settings", icon_name="emblem-system-symbolic")
        window.add(page)

        goals = Adw.PreferencesGroup(
            title="Personal goals",
            description="Optional reminders independent of Google AI Pro allowance windows.",
        )
        page.add(goals)
        goals.add(
            self._spin_row(
                "Daily token goal",
                "tokens",
                self.settings.daily_token_budget,
                10_000,
                500_000_000,
                50_000,
                "daily_token_budget",
            )
        )
        goals.add(
            self._spin_row(
                "Daily focus-time goal",
                "minutes",
                self.settings.daily_focus_minutes,
                15,
                1_440,
                15,
                "daily_focus_minutes",
            )
        )

        behavior = Adw.PreferencesGroup(title="Behavior")
        page.add(behavior)
        behavior.add(
            self._spin_row(
                "Notify at",
                "%",
                self.settings.notify_at_percent,
                1,
                100,
                1,
                "notify_at_percent",
            )
        )
        behavior.add(
            self._spin_row(
                "Refresh interval",
                "seconds",
                self.settings.refresh_seconds,
                5,
                3_600,
                5,
                "refresh_seconds",
            )
        )

        source = Adw.PreferencesGroup(
            title="Data source",
            description="Conversation content stays on this computer. Only metadata, numeric counters, and Google AI Pro quota fractions are read.",
        )
        page.add(source)
        source.add(self._text_row("Antigravity data folder", self.settings.antigravity_home))

        about = Adw.PreferencesGroup(title="About")
        page.add(about)
        privacy = Adw.ActionRow(
            title="Privacy-first local &amp; Google AI Pro quota monitoring",
            subtitle="Reads local ~/.gemini/antigravity-cli transcripts and Cloud Code Assist quota buckets",
        )
        privacy.add_prefix(Gtk.Image.new_from_icon_name("security-high-symbolic"))
        about.add(privacy)

        window.present()
        self._connect_service_and_load()

    def _connect_service_and_load(self) -> None:
        try:
            self._bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            self._signal_id = self._bus.signal_subscribe(
                BUS_NAME,
                INTERFACE,
                "UsageChanged",
                OBJECT_PATH,
                None,
                Gio.DBusSignalFlags.NONE,
                self._on_usage_signal,
            )
            self._call_dbus_method("GetSummary")
        except Exception:
            self._load_direct_fallback()

    def _call_dbus_method(self, method_name: str) -> None:
        if self._bus is None:
            self._load_direct_fallback()
            return
        self._bus.call(
            BUS_NAME,
            OBJECT_PATH,
            INTERFACE,
            method_name,
            None,
            GLib.VariantType("(s)"),
            Gio.DBusCallFlags.NONE,
            8000,
            None,
            self._on_dbus_reply,
        )

    def _on_dbus_reply(self, bus: Gio.DBusConnection, res: Gio.AsyncResult) -> None:
        try:
            variant = bus.call_finish(res)
            serialized = variant.unpack()[0]
            self._apply_summary(json.loads(serialized))
        except Exception:
            self._load_direct_fallback()

    def _on_usage_signal(
        self,
        _connection: Gio.DBusConnection,
        _sender_name: str,
        _object_path: str,
        _interface_name: str,
        _signal_name: str,
        parameters: GLib.Variant,
    ) -> None:
        try:
            serialized = parameters.unpack()[0]
            self._apply_summary(json.loads(serialized))
        except Exception:
            pass

    def _load_direct_fallback(self) -> None:
        try:
            summary = collect_summary(self.settings)
            self._apply_summary(summary)
        except Exception:
            pass

    def _on_refresh_clicked(self, _button: Gtk.Button) -> None:
        self._call_dbus_method("Refresh")

    def _apply_summary(self, summary: dict[str, Any]) -> None:
        limits = summary.get("rate_limits") or {}
        groups = limits.get("groups") or []
        argon_group = next((g for g in groups if isinstance(g, dict) and g.get("group_id") == "gemini_argon"), {})
        gemini_group = next((g for g in groups if isinstance(g, dict) and g.get("group_id") == "gemini"), {})
        claude_group = next((g for g in groups if isinstance(g, dict) and g.get("group_id") == "claude_gpt"), {})

        primary = limits.get("primary") or {}
        primary_bucket = str(primary.get("bucket_id") or "")

        argon_7d = limits.get("gemini_argon_weekly") or argon_group.get("weekly")
        gemini_5h = limits.get("gemini_5h") or gemini_group.get("five_hour")
        if gemini_5h is None and primary_bucket in ("", "gemini-5h") and argon_7d is None:
            gemini_5h = limits.get("primary")
        gemini_7d = limits.get("gemini_weekly") or gemini_group.get("weekly")
        claude_5h = limits.get("claude_gpt_5h") or claude_group.get("five_hour")
        if claude_5h is None and (limits.get("secondary") or {}).get("bucket_id") in ("", "3p-5h"):
            claude_5h = limits.get("secondary")
        claude_7d = limits.get("claude_gpt_weekly") or claude_group.get("weekly")

        if self._gemini_argon_7d_row:
            self._gemini_argon_7d_row.update(argon_7d, is_active=True)
        if self._gemini_5h_row:
            self._gemini_5h_row.update(gemini_5h)
        if self._gemini_7d_row:
            self._gemini_7d_row.update(gemini_7d)
        if self._claude_5h_row:
            self._claude_5h_row.update(claude_5h)
        if self._claude_7d_row:
            self._claude_7d_row.update(claude_7d)

        if self._quota_group:
            active_model = str(summary.get("active_model") or limits.get("active_model") or "")
            email = str(summary.get("account_email") or limits.get("account_email") or "")
            parts = [p for p in (active_model, email) if p]
            if parts:
                self._quota_group.set_description("  ·  ".join(parts))

        today = summary.get("today") or {}
        values = {
            "sessions": str(today.get("sessions", 0)),
            "focus_minutes": f"{today.get('focus_minutes', 0)} min",
            "tokens": f"{int(today.get('tokens', 0)):,}",
            "week_tokens": f"{int((summary.get('week') or {}).get('tokens', 0)):,}",
            "source": str(summary.get("rate_limits_source") or "Unavailable"),
        }
        if summary.get("rate_limits_refresh_error"):
            values["source"] += " (refresh failed; showing available data)"
        for key, value in values.items():
            if key in self._activity_rows:
                self._activity_rows[key].set_subtitle(GLib.markup_escape_text(value))
        if self._recent_group:
            for row in self._recent_rows:
                self._recent_group.remove(row)
            self._recent_rows.clear()
            for item in (summary.get("recent") or [])[:5]:
                subtitle = " · ".join(str(v) for v in (
                    item.get("project"), item.get("model"),
                    f"{int(item.get('tokens', 0)):,} tokens", item.get("status"),
                ) if v)
                row = Adw.ActionRow(
                    title=GLib.markup_escape_text(str(item.get("name") or "Untitled task")),
                    subtitle=GLib.markup_escape_text(subtitle),
                )
                self._recent_group.add(row)
                self._recent_rows.append(row)
            if not self._recent_rows:
                row = Adw.ActionRow(title="No recent tasks")
                self._recent_group.add(row)
                self._recent_rows.append(row)

    def _spin_row(
        self,
        title: str,
        unit: str,
        value: int,
        minimum: int,
        maximum: int,
        step: int,
        attribute: str,
    ) -> Adw.ActionRow:
        row = Adw.ActionRow(title=title)
        control = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(
                value=value,
                lower=minimum,
                upper=maximum,
                step_increment=step,
                page_increment=step * 10,
            ),
            numeric=True,
            valign=Gtk.Align.CENTER,
        )
        control.set_tooltip_text(unit)
        control.connect("value-changed", self._save_number, attribute)
        row.add_suffix(control)
        row.set_activatable_widget(control)
        return row

    def _text_row(self, title: str, value: str) -> Adw.ActionRow:
        row = Adw.ActionRow(title=title)
        entry = Gtk.Entry(text=value, valign=Gtk.Align.CENTER, width_chars=28)
        entry.connect("activate", self._save_path)
        entry.connect("notify::has-focus", self._save_path_on_blur)
        row.add_suffix(entry)
        row.set_activatable_widget(entry)
        return row

    def _save_number(self, control: Gtk.SpinButton, attribute: str) -> None:
        setattr(self.settings, attribute, control.get_value_as_int())
        self.settings.validated().save()

    def _save_path(self, entry: Gtk.Entry) -> None:
        self.settings.antigravity_home = entry.get_text()
        self.settings.validated().save()

    def _save_path_on_blur(self, entry: Gtk.Entry, _parameter: object) -> None:
        if not entry.get_property("has-focus"):
            self._save_path(entry)


def main() -> None:
    PreferencesApplication().run(None)


if __name__ == "__main__":
    main()
