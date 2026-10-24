"""Persist account allowance snapshots independently of Antigravity session logs."""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from .metrics import ModelGroupQuota, RateLimits, RateWindow


def network_cache_path(antigravity_home: str) -> Path:
    """Keep separate caches for each Antigravity home, outside Antigravity's own files."""
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    home = os.path.normcase(str(Path(antigravity_home).expanduser().resolve()))
    profile = hashlib.sha256(home.encode("utf-8")).hexdigest()
    return base / "antigravity-usage-supervisor" / f"network-limits-{profile}.json"


def _window_dict(window: RateWindow | None) -> dict[str, Any] | None:
    if window is None:
        return None
    return {
        "used_percent": window.used_percent,
        "remaining_percent": round(max(0.0, 100.0 - window.used_percent), 2),
        "window_minutes": window.window_minutes,
        "resets_at": window.resets_at.isoformat() if window.resets_at else None,
        "label": window.label,
        "bucket_id": window.bucket_id,
    }


def _group_dict(group: ModelGroupQuota) -> dict[str, Any]:
    return {
        "group_id": group.group_id,
        "display_name": group.display_name,
        "five_hour": _window_dict(group.five_hour),
        "weekly": _window_dict(group.weekly),
    }


def limits_dict(limits: RateLimits | None) -> dict[str, Any] | None:
    """Serialize the cache and desktop contract in the same timestamp format."""
    if limits is None:
        return None
    argon_group = next((g for g in limits.groups if g.group_id == "gemini_argon"), None)
    gemini_group = next((g for g in limits.groups if g.group_id == "gemini"), None)
    claude_group = next((g for g in limits.groups if g.group_id == "claude_gpt"), None)

    gemini_argon_weekly = limits.gemini_argon_weekly or (argon_group.weekly if argon_group else None)
    gemini_5h = (gemini_group.five_hour if gemini_group else None) or next(
        (w for w in (limits.primary, limits.secondary) if w and w.bucket_id == "gemini-5h"), None
    )
    gemini_weekly = limits.gemini_weekly or (gemini_group.weekly if gemini_group else None)
    claude_5h = (claude_group.five_hour if claude_group else None) or next(
        (w for w in (limits.primary, limits.secondary) if w and w.bucket_id == "3p-5h"), None
    )
    claude_weekly = (claude_group.weekly if claude_group else None) or limits.claude_gpt_weekly
    return {
        "plan_type": limits.plan_type,
        "account_email": limits.account_email,
        "active_model": limits.active_model,
        "primary": _window_dict(limits.primary),
        "secondary": _window_dict(limits.secondary),
        "gemini_argon_weekly": _window_dict(gemini_argon_weekly),
        "gemini_5h": _window_dict(gemini_5h),
        "gemini_weekly": _window_dict(gemini_weekly),
        "claude_gpt_5h": _window_dict(claude_5h),
        "claude_gpt_weekly": _window_dict(claude_weekly),
        "groups": [_group_dict(g) for g in limits.groups],
        "observed_at": limits.observed_at.isoformat(),
    }


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("Cache timestamps must include a timezone")
    return parsed


def _window(value: Any) -> RateWindow | None:
    if value is None:
        return None
    used = float(value["used_percent"])
    minutes = int(value["window_minutes"])
    if not math.isfinite(used) or used < 0 or minutes < 0:
        raise ValueError("Invalid cached allowance window")
    reset = value.get("resets_at")
    return RateWindow(
        used_percent=used,
        window_minutes=minutes,
        resets_at=_timestamp(reset) if isinstance(reset, str) and reset else None,
        label=str(value.get("label") or ""),
        bucket_id=str(value.get("bucket_id") or ""),
    )


def _group(value: Any) -> ModelGroupQuota:
    if not isinstance(value, dict):
        raise ValueError("Invalid cached model group")
    return ModelGroupQuota(
        group_id=str(value.get("group_id") or ""),
        display_name=str(value.get("display_name") or ""),
        five_hour=_window(value.get("five_hour")),
        weekly=_window(value.get("weekly")),
    )


def load_network_limits(path: Path) -> RateLimits | None:
    """Ignore missing, unreadable, or malformed caches without breaking refresh."""
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("schema_version") != 1:
            return None
        value = record["rate_limits"]
        groups_raw = value.get("groups") or []
        parsed_groups = [_group(item) for item in groups_raw if isinstance(item, dict)]
        argon_group = next((g for g in parsed_groups if g.group_id == "gemini_argon"), None)
        gemini_group = next((g for g in parsed_groups if g.group_id == "gemini"), None)
        claude_group = next((g for g in parsed_groups if g.group_id == "claude_gpt"), None)
        gemini_argon_weekly = _window(value.get("gemini_argon_weekly")) or (
            argon_group.weekly if argon_group else None
        )
        gemini_weekly = _window(value.get("gemini_weekly")) or (
            gemini_group.weekly if gemini_group else None
        )
        claude_weekly = _window(value.get("claude_gpt_weekly")) or (
            claude_group.weekly if claude_group else None
        )
        limits = RateLimits(
            plan_type=value["plan_type"],
            primary=_window(value.get("primary")),
            secondary=_window(value.get("secondary")),
            observed_at=_timestamp(value["observed_at"]),
            account_email=str(value.get("account_email") or ""),
            active_model=str(value.get("active_model") or ""),
            gemini_argon_weekly=gemini_argon_weekly,
            gemini_weekly=gemini_weekly,
            claude_gpt_weekly=claude_weekly,
            groups=parsed_groups,
        )
        if not isinstance(limits.plan_type, str) or (limits.primary is None and limits.secondary is None):
            return None
        return limits
    except (OSError, ValueError, TypeError, KeyError, OverflowError):
        return None


def save_network_limits(path: Path, limits: RateLimits) -> None:
    """Atomically save only allowance fields and their original observation time."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=path.name, suffix=".tmp", delete=False
        ) as stream:
            temporary = Path(stream.name)
            json.dump({"schema_version": 1, "rate_limits": limits_dict(limits)}, stream, allow_nan=False)
            stream.write("\n")
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
