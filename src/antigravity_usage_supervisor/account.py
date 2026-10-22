"""Fetch fresh Google AI Pro / Antigravity quota limits via Cloud Code Assist API or local Language Server."""

from __future__ import annotations

import base64
import json
import os
import re
import ssl
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .metrics import ModelGroupQuota, RateLimits, RateWindow, _timestamp

_DAILY_HOST = "https://daily-cloudcode-pa.googleapis.com"
_PROD_HOST = "https://cloudcode-pa.googleapis.com"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_CACHED_CLIENT_CREDS: tuple[str, str] | None = None


def _discover_local_oauth_client() -> tuple[str, str]:
    """Read public OAuth client_id and client_secret from installed Antigravity IDE or agy binary."""
    global _CACHED_CLIENT_CREDS
    if _CACHED_CLIENT_CREDS is not None:
        return _CACHED_CLIENT_CREDS

    env_id = os.environ.get("ANTIGRAVITY_OAUTH_CLIENT_ID", "").strip()
    env_secret = os.environ.get("ANTIGRAVITY_OAUTH_CLIENT_SECRET", "").strip()
    if env_id and env_secret:
        _CACHED_CLIENT_CREDS = (env_id, env_secret)
        return _CACHED_CLIENT_CREDS

    id_pattern = re.compile(rb"(1071006060591-[a-z0-9]+\.apps\.googleusercontent\.com)")
    secret_pattern = re.compile(rb"(GOCSPX-[A-Za-z0-9_-]{20,40})")

    candidates = [
        Path("/usr/share/antigravity/resources/app/out/main.js"),
        Path.home() / ".local" / "bin" / "agy",
        Path("/usr/local/bin/agy"),
        Path("/usr/bin/agy"),
    ]
    found_id = env_id
    found_secret = env_secret
    for candidate in candidates:
        if not candidate.is_file():
            continue
        try:
            raw = candidate.read_bytes()
        except OSError:
            continue
        if not found_id:
            m_id = id_pattern.search(raw)
            if m_id:
                found_id = m_id.group(1).decode("ascii", errors="ignore")
        if not found_secret:
            m_sec = secret_pattern.search(raw)
            if m_sec:
                found_secret = m_sec.group(1).decode("ascii", errors="ignore")
        if found_id and found_secret:
            break

    _CACHED_CLIENT_CREDS = (found_id, found_secret)
    return _CACHED_CLIENT_CREDS


class AccountLimitsError(RuntimeError):
    """Raised when a fresh account snapshot cannot be obtained."""


def _decode_jwt_claims(token: str) -> dict[str, Any]:
    if not isinstance(token, str) or token.count(".") < 2:
        return {}
    try:
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        raw = base64.urlsafe_b64decode(payload_b64.encode("ascii"))
        claims = json.loads(raw.decode("utf-8"))
        return claims if isinstance(claims, dict) else {}
    except (ValueError, KeyError, UnicodeDecodeError):
        return {}


def _read_keyring_secret_dbus() -> dict[str, Any] | None:
    try:
        import gi

        gi.require_version("Gio", "2.0")
        from gi.repository import Gio, GLib

        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        _, session_path = bus.call_sync(
            "org.freedesktop.secrets",
            "/org/freedesktop/secrets",
            "org.freedesktop.Secret.Service",
            "OpenSession",
            GLib.Variant("(sv)", ("plain", GLib.Variant("s", ""))),
            GLib.VariantType("(vo)"),
            Gio.DBusCallFlags.NONE,
            2000,
            None,
        ).unpack()

        unlocked, _ = bus.call_sync(
            "org.freedesktop.secrets",
            "/org/freedesktop/secrets",
            "org.freedesktop.Secret.Service",
            "SearchItems",
            GLib.Variant("(a{ss})", ({"service": "gemini", "username": "antigravity"},)),
            GLib.VariantType("(aoao)"),
            Gio.DBusCallFlags.NONE,
            2000,
            None,
        ).unpack()
        if not unlocked:
            return None

        secrets = bus.call_sync(
            "org.freedesktop.secrets",
            "/org/freedesktop/secrets",
            "org.freedesktop.Secret.Service",
            "GetSecrets",
            GLib.Variant("(aoo)", (unlocked, session_path)),
            GLib.VariantType("(a{o(oayays)})"),
            Gio.DBusCallFlags.NONE,
            2000,
            None,
        ).unpack()[0]
        if not secrets:
            return None

        raw_bytes = bytes(next(iter(secrets.values()))[2])
        parsed = json.loads(raw_bytes.decode("utf-8"))
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def _read_keyring_secret_cli() -> dict[str, Any] | None:
    try:
        output = subprocess.check_output(
            ["secret-tool", "lookup", "service", "gemini", "username", "antigravity"],
            stderr=subprocess.DEVNULL,
            timeout=2.0,
            text=True,
        )
        parsed = json.loads(output)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def _read_plugin_secrets_file() -> dict[str, Any] | None:
    config_root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    candidates = [
        config_root / "antigravity" / "plugin-secrets.json",
        Path.home() / ".config" / "antigravity" / "plugin-secrets.json",
    ]
    for path in candidates:
        if not path.is_file():
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                if "token" in raw and isinstance(raw["token"], dict):
                    return raw
                for val in raw.values():
                    if isinstance(val, str):
                        try:
                            inner = json.loads(val)
                            if isinstance(inner, dict) and "token" in inner:
                                return inner
                        except json.JSONDecodeError:
                            continue
        except (OSError, json.JSONDecodeError):
            continue
    return None


def load_oauth_credentials() -> dict[str, Any]:
    """Load Antigravity OAuth credentials from GNOME Keyring or fallback secret store."""
    secret = (
        _read_keyring_secret_dbus()
        or _read_keyring_secret_cli()
        or _read_plugin_secrets_file()
    )
    if not secret or not isinstance(secret.get("token"), dict):
        raise AccountLimitsError("Antigravity OAuth credentials were not found in keyring or config")
    return secret


def _refresh_access_token(refresh_token: str, client_id: str, timeout: float = 6.0) -> str:
    discovered_id, discovered_secret = _discover_local_oauth_client()
    resolved_id = client_id or discovered_id
    if not resolved_id or not discovered_secret:
        raise AccountLimitsError("Could not discover local Antigravity OAuth client configuration for token refresh")
    form = urllib.parse.urlencode(
        {
            "client_id": resolved_id,
            "client_secret": discovered_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        _TOKEN_URL,
        data=form,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            access_token = payload.get("access_token")
            if isinstance(access_token, str) and access_token:
                return access_token
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as error:
        raise AccountLimitsError(f"OAuth token refresh failed: {error}") from error
    raise AccountLimitsError("OAuth token refresh returned no access_token")


def _ensure_valid_token(secret: dict[str, Any], timeout: float = 6.0) -> tuple[str, str]:
    """Return (access_token, account_email), refreshing expired tokens if needed."""
    token_obj = secret.get("token") or {}
    access_token = str(token_obj.get("access_token") or "").strip()
    refresh_token = str(token_obj.get("refresh_token") or "").strip()
    expiry_dt = _timestamp(token_obj.get("expiry"))
    claims = _decode_jwt_claims(str(secret.get("id_token") or ""))
    email = str(claims.get("email") or "").strip()
    client_id = str(claims.get("aud") or "").strip()

    now = datetime.now(timezone.utc)
    is_expired = expiry_dt is not None and expiry_dt <= (now + timedelta(seconds=60))
    if (not access_token or is_expired) and refresh_token:
        access_token = _refresh_access_token(refresh_token, client_id, timeout=timeout)
    if not access_token:
        raise AccountLimitsError("No valid Antigravity OAuth access token available")
    return access_token, email


def _post_json(url: str, access_token: str, payload: dict[str, Any], timeout: float = 6.0) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "User-Agent": "antigravity",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return body if isinstance(body, dict) else {}
    except urllib.error.HTTPError as error:
        raise AccountLimitsError(f"Cloud Code API HTTP {error.code} on {url.rsplit('/', 1)[-1]}") from error
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as error:
        raise AccountLimitsError(f"Cloud Code API request failed: {error}") from error


def _used_percent_from_remaining(remaining: Any) -> float | None:
    if not isinstance(remaining, (int, float)):
        return None
    clamped = min(1.0, max(0.0, float(remaining)))
    return round((1.0 - clamped) * 100.0, 1)


def _merge_windows(first: RateWindow | None, second: RateWindow | None) -> RateWindow | None:
    if first is None:
        return second
    if second is None:
        return first
    if second.used_percent > first.used_percent:
        return RateWindow(
            used_percent=second.used_percent,
            window_minutes=second.window_minutes or first.window_minutes,
            resets_at=second.resets_at or first.resets_at,
            label=first.label or second.label,
            bucket_id=first.bucket_id or second.bucket_id,
        )
    return RateWindow(
        used_percent=first.used_percent,
        window_minutes=first.window_minutes or second.window_minutes,
        resets_at=first.resets_at or second.resets_at,
        label=first.label or second.label,
        bucket_id=first.bucket_id or second.bucket_id,
    )


def parse_cloudcode_quota(
    load_response: dict[str, Any],
    quota_response: dict[str, Any],
    summary_response: dict[str, Any] | None = None,
    account_email: str = "",
    active_model: str = "",
    observed_at: datetime | None = None,
) -> RateLimits:
    """Combine loadCodeAssist, retrieveUserQuota, and retrieveUserQuotaSummary into RateLimits."""
    observed_at = (observed_at or datetime.now().astimezone()).astimezone()

    paid_tier = load_response.get("paidTier") if isinstance(load_response, dict) else None
    current_tier = load_response.get("currentTier") if isinstance(load_response, dict) else None
    plan_type = "Google AI Pro"
    if isinstance(paid_tier, dict) and paid_tier.get("name"):
        plan_type = str(paid_tier["name"])
    elif isinstance(current_tier, dict) and current_tier.get("name"):
        plan_type = str(current_tier["name"])

    gemini_5h: RateWindow | None = None
    gemini_weekly: RateWindow | None = None
    claude_5h: RateWindow | None = None
    claude_weekly: RateWindow | None = None

    # 1. Parse group-level summary (5h and weekly windows)
    if isinstance(summary_response, dict):
        for group in summary_response.get("groups") or []:
            if not isinstance(group, dict):
                continue
            gname = str(group.get("displayName") or "").lower()
            is_gemini_group = "gemini" in gname
            for bucket in group.get("buckets") or []:
                if not isinstance(bucket, dict):
                    continue
                used = _used_percent_from_remaining(bucket.get("remainingFraction"))
                if used is None:
                    continue
                bid = str(bucket.get("bucketId") or "")
                win_str = str(bucket.get("window") or "").lower()
                is_weekly = win_str == "weekly" or "weekly" in bid
                win_mins = 10080 if is_weekly else 300
                reset_dt = _timestamp(bucket.get("resetTime"))
                if is_gemini_group or bid.startswith("gemini"):
                    label = "7-day allowance (Gemini)" if is_weekly else "5-hour allowance (Gemini)"
                    candidate = RateWindow(used, win_mins, reset_dt, label=label, bucket_id=bid or "gemini")
                    if is_weekly:
                        gemini_weekly = _merge_windows(gemini_weekly, candidate)
                    else:
                        gemini_5h = _merge_windows(gemini_5h, candidate)
                else:
                    label = "7-day allowance (Claude & GPT)" if is_weekly else "5-hour allowance (Claude & GPT)"
                    candidate = RateWindow(used, win_mins, reset_dt, label=label, bucket_id=bid or "3p")
                    if is_weekly:
                        claude_weekly = _merge_windows(claude_weekly, candidate)
                    else:
                        claude_5h = _merge_windows(claude_5h, candidate)

    # 2. Parse per-model buckets from retrieveUserQuota (reflects real-time sub-percent usage)
    if isinstance(quota_response, dict):
        for bucket in quota_response.get("buckets") or []:
            if not isinstance(bucket, dict):
                continue
            model_id = str(bucket.get("modelId") or "").lower()
            if not model_id or model_id.startswith(("chat_", "tab_")):
                continue
            used = _used_percent_from_remaining(bucket.get("remainingFraction"))
            if used is None:
                continue
            reset_dt = _timestamp(bucket.get("resetTime"))
            # If reset_dt is more than 6 hours in the future, the bucket is governed by the 7-day weekly limit
            is_weekly_bucket = bool(
                reset_dt is not None and (reset_dt - observed_at) > timedelta(hours=6)
            )
            if "gemini" in model_id:
                if is_weekly_bucket:
                    gemini_weekly = _merge_windows(
                        gemini_weekly,
                        RateWindow(
                            used_percent=used,
                            window_minutes=10080,
                            resets_at=reset_dt,
                            label="7-day allowance (Gemini)",
                            bucket_id="gemini-weekly",
                        ),
                    )
                else:
                    gemini_5h = _merge_windows(
                        gemini_5h,
                        RateWindow(
                            used_percent=used,
                            window_minutes=300,
                            resets_at=reset_dt,
                            label="5-hour allowance (Gemini)",
                            bucket_id="gemini-5h",
                        ),
                    )
            elif any(k in model_id for k in ("claude", "gpt")):
                if is_weekly_bucket:
                    claude_weekly = _merge_windows(
                        claude_weekly,
                        RateWindow(
                            used_percent=used,
                            window_minutes=10080,
                            resets_at=reset_dt,
                            label="7-day allowance (Claude & GPT)",
                            bucket_id="3p-weekly",
                        ),
                    )
                else:
                    claude_5h = _merge_windows(
                        claude_5h,
                        RateWindow(
                            used_percent=used,
                            window_minutes=300,
                            resets_at=reset_dt,
                            label="5-hour allowance (Claude & GPT)",
                            bucket_id="3p-5h",
                        ),
                    )

    if gemini_5h is None and claude_5h is None and gemini_weekly is None and claude_weekly is None:
        raise AccountLimitsError("Cloud Code API returned no model quota buckets")

    groups: list[ModelGroupQuota] = []
    if gemini_5h or gemini_weekly:
        groups.append(
            ModelGroupQuota(
                group_id="gemini",
                display_name="Gemini Models",
                five_hour=gemini_5h,
                weekly=gemini_weekly,
            )
        )
    if claude_5h or claude_weekly:
        groups.append(
            ModelGroupQuota(
                group_id="claude_gpt",
                display_name="Claude & GPT Models",
                five_hour=claude_5h,
                weekly=claude_weekly,
            )
        )

    active_lower = active_model.lower()
    active_is_3p = any(k in active_lower for k in ("claude", "sonnet", "opus", "gpt"))

    # Always pair primary = 5-hour allowance (300m) and secondary = 7-day allowance (10080m)
    if active_is_3p and (claude_5h is not None or claude_weekly is not None):
        primary = claude_5h or gemini_5h
        secondary = claude_weekly or gemini_weekly
    else:
        primary = gemini_5h or claude_5h
        secondary = gemini_weekly or claude_weekly

    return RateLimits(
        plan_type=plan_type,
        primary=primary,
        secondary=secondary,
        observed_at=observed_at,
        account_email=account_email,
        active_model=active_model or "Gemini 4 Argon (Medium)",
        groups=groups,
    )


def fetch_cloudcode_rate_limits(
    active_model: str = "",
    timeout: float = 8.0,
) -> RateLimits:
    """Fetch live Google AI Pro quota limits from Google's Cloud Code Assist API."""
    secret = load_oauth_credentials()
    access_token, email = _ensure_valid_token(secret, timeout=timeout)

    load_payload = {
        "metadata": {
            "ideType": "ANTIGRAVITY",
            "platform": "PLATFORM_UNSPECIFIED",
            "pluginType": "GEMINI",
        }
    }
    try:
        load_resp = _post_json(f"{_DAILY_HOST}/v1internal:loadCodeAssist", access_token, load_payload, timeout=timeout)
    except AccountLimitsError:
        load_resp = _post_json(f"{_PROD_HOST}/v1internal:loadCodeAssist", access_token, load_payload, timeout=timeout)

    project = str(load_resp.get("cloudaicompanionProject") or "aicode-consumers")
    project_payload = {"project": project}

    merged_buckets: list[dict[str, Any]] = []
    for host in (_DAILY_HOST, _PROD_HOST):
        try:
            q_resp = _post_json(
                f"{host}/v1internal:retrieveUserQuota",
                access_token,
                project_payload,
                timeout=timeout,
            )
            if isinstance(q_resp.get("buckets"), list):
                merged_buckets.extend(q_resp["buckets"])
        except AccountLimitsError:
            continue

    merged_groups: list[dict[str, Any]] = []
    for host in (_DAILY_HOST, _PROD_HOST):
        try:
            candidate = _post_json(
                f"{host}/v1internal:retrieveUserQuotaSummary",
                access_token,
                project_payload,
                timeout=timeout,
            )
            if isinstance(candidate.get("groups"), list):
                merged_groups.extend(candidate["groups"])
        except AccountLimitsError:
            continue

    return parse_cloudcode_quota(
        load_response=load_resp,
        quota_response={"buckets": merged_buckets},
        summary_response={"groups": merged_groups},
        account_email=email,
        active_model=active_model,
    )


def _discover_language_server() -> tuple[int, str] | None:
    """Find running language_server_linux_x64 HTTP/HTTPS port and CSRF token."""
    try:
        ps_out = subprocess.check_output(["ps", "-eo", "pid,args"], text=True, timeout=2.0)
    except Exception:
        return None

    csrf_token = ""
    for line in ps_out.splitlines():
        if "language_server_linux" in line and "--csrf_token" in line:
            match = re.search(r"--csrf_token\s+([0-9a-fA-F-]+)", line)
            if match:
                csrf_token = match.group(1)
                break
    if not csrf_token:
        return None

    log_root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "Antigravity" / "logs"
    if not log_root.is_dir():
        return None
    logs = sorted(log_root.glob("**/google.antigravity/Antigravity.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    for log_file in logs[:2]:
        try:
            text = log_file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        http_match = re.search(r"Language server listening on random port at (\d+) for HTTP\b", text)
        if http_match:
            return int(http_match.group(1)), csrf_token
    return None


def parse_user_status_response(
    payload: dict[str, Any],
    active_model: str = "",
    observed_at: datetime | None = None,
) -> RateLimits:
    """Parse Connect-RPC GetUserStatusResponse into RateLimits."""
    observed_at = (observed_at or datetime.now().astimezone()).astimezone()
    user_status = payload.get("userStatus")
    if not isinstance(user_status, dict):
        raise AccountLimitsError("Language server returned no userStatus")

    email = str(user_status.get("email") or "").strip()
    plan_info = (user_status.get("planStatus") or {}).get("planInfo") or {}
    user_tier = user_status.get("userTier") or {}
    plan_type = str(
        user_tier.get("name") or plan_info.get("planName") or "Google AI Pro"
    )

    configs = (user_status.get("cascadeModelConfigData") or {}).get("clientModelConfigs") or []
    gemini_5h: RateWindow | None = None
    claude_5h: RateWindow | None = None

    for cfg in configs:
        if not isinstance(cfg, dict):
            continue
        label = str(cfg.get("label") or "")
        qinfo = cfg.get("quotaInfo")
        if not isinstance(qinfo, dict):
            continue
        used = _used_percent_from_remaining(qinfo.get("remainingFraction", 1.0))
        if used is None:
            continue
        reset_dt = _timestamp(qinfo.get("resetTime"))
        lower_label = label.lower()
        if "gemini" in lower_label:
            gemini_5h = _merge_windows(
                gemini_5h,
                RateWindow(used, 300, reset_dt, label="Gemini 5-hour allowance", bucket_id="gemini-5h"),
            )
        elif any(k in lower_label for k in ("claude", "sonnet", "opus", "gpt")):
            claude_5h = _merge_windows(
                claude_5h,
                RateWindow(used, 300, reset_dt, label="Claude & GPT 5-hour allowance", bucket_id="3p-5h"),
            )

    if gemini_5h is None and claude_5h is None:
        raise AccountLimitsError("Language server returned no model quota configs")

    groups: list[ModelGroupQuota] = []
    if gemini_5h:
        groups.append(ModelGroupQuota("gemini", "Gemini Models", five_hour=gemini_5h))
    if claude_5h:
        groups.append(ModelGroupQuota("claude_gpt", "Claude & GPT Models", five_hour=claude_5h))

    return RateLimits(
        plan_type=plan_type,
        primary=gemini_5h or claude_5h,
        secondary=claude_5h if gemini_5h else None,
        observed_at=observed_at,
        account_email=email,
        active_model=active_model or "Gemini 4 Argon (Medium)",
        groups=groups,
    )


def fetch_language_server_rate_limits(active_model: str = "", timeout: float = 3.0) -> RateLimits:
    discovered = _discover_language_server()
    if discovered is None:
        raise AccountLimitsError("Local Antigravity language server is not running")
    port, csrf_token = discovered
    url = f"http://127.0.0.1:{port}/exa.language_server_pb.LanguageServerService/GetUserStatus"
    req = urllib.request.Request(
        url,
        data=json.dumps(
            {"metadata": {"ideName": "antigravity", "extensionName": "antigravity", "locale": "en"}}
        ).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Connect-Protocol-Version": "1",
            "x-codeium-csrf-token": csrf_token,
        },
        method="POST",
    )
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as error:
        raise AccountLimitsError(f"Local language server request failed: {error}") from error
    return parse_user_status_response(payload, active_model=active_model)


def fetch_account_rate_limits(
    antigravity_home: str | None = None,
    active_model: str = "",
    timeout: float = 8.0,
) -> RateLimits:
    """Fetch fresh Google AI Pro account limits using Cloud Code API with Language Server fallback."""
    errors: list[str] = []
    try:
        return fetch_cloudcode_rate_limits(active_model=active_model, timeout=timeout)
    except AccountLimitsError as error:
        errors.append(str(error))

    try:
        return fetch_language_server_rate_limits(active_model=active_model, timeout=min(timeout, 3.0))
    except AccountLimitsError as error:
        errors.append(str(error))

    raise AccountLimitsError("; ".join(errors))
