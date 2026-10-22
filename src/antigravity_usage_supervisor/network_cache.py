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
    return {
        "plan_type": limits.plan_type,
        "account_email": limits.account_email,
        "active_model": limits.active_model,
        "primary": _window_dict(limits.primary),
        "secondary": _window_dict(limits.secondary),
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
        limits = RateLimits(
            plan_type=value["plan_type"],
            primary=_window(value.get("primary")),
            secondary=_window(value.get("secondary")),
            observed_at=_timestamp(value["observed_at"]),
            account_email=str(value.get("account_email") or ""),
            active_model=str(value.get("active_model") or ""),
            groups=[_group(item) for item in groups_raw if isinstance(item, dict)],
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
