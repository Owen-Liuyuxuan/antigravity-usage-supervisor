"""Read privacy-conscious usage metrics from local Antigravity session logs.

Only timestamps, identifiers, workspace paths, model names, step counts, and
numeric token counters are retained. Prompt and response content is ignored.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote, urlparse

_MODEL_CHANGE_RE = re.compile(r"Model Selection from [^\n]*? to ([^\n.<]+?)\.?\s*(?:</USER_SETTINGS_CHANGE>|$)")
_PBTXT_TITLE_RE = re.compile(r'title\s*:\s*"((?:[^"\\]|\\.)*)"')
_LOG_EMAIL_RE = re.compile(r"OAuth: authenticated successfully as ([^\s]+)")
_LOG_MODEL_RE = re.compile(r'Propagating selected model override to backend: label="([^"]+)"')
_LOG_WORKSPACE_RE = re.compile(r'Using workspace "([^"]+)" from conversation ([0-9a-fA-F-]+)')


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value or value.startswith("0001-01-01"):
        return None
    try:
        normalized = value.strip().replace("Z", "+00:00")
        # Handle Go/SQLite timestamps with 9 fractional digits or space separator
        if " " in normalized and "T" not in normalized:
            normalized = normalized.replace(" ", "T", 1)
        frac_match = re.match(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})\.(\d+)(.*)$", normalized)
        if frac_match:
            prefix, frac, suffix = frac_match.groups()
            normalized = f"{prefix}.{frac[:6].ljust(6, '0')}{suffix}"
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone()
    except ValueError:
        return None


@dataclass(slots=True)
class TokenUsage:
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_output_tokens: int = 0
    total_tokens: int = 0

    def add(self, other: "TokenUsage") -> None:
        self.input_tokens += other.input_tokens
        self.cached_input_tokens += other.cached_input_tokens
        self.output_tokens += other.output_tokens
        self.reasoning_output_tokens += other.reasoning_output_tokens
        self.total_tokens += other.total_tokens


@dataclass(slots=True)
class RateWindow:
    used_percent: float
    window_minutes: int
    resets_at: datetime | None
    label: str = ""
    bucket_id: str = ""


@dataclass(slots=True)
class ModelGroupQuota:
    group_id: str
    display_name: str
    five_hour: RateWindow | None = None
    weekly: RateWindow | None = None


@dataclass(slots=True)
class RateLimits:
    plan_type: str
    primary: RateWindow | None
    secondary: RateWindow | None
    observed_at: datetime
    account_email: str = ""
    active_model: str = ""
    groups: list[ModelGroupQuota] = field(default_factory=list)


@dataclass(slots=True)
class SessionMetric:
    session_id: str
    name: str = "Untitled task"
    cwd: str = ""
    model: str = "Unknown"
    started_at: datetime | None = None
    updated_at: datetime | None = None
    turns: int = 0
    usage: TokenUsage = field(default_factory=TokenUsage)
    today_tokens: int = 0
    week_tokens: int = 0
    today_minutes: int = 0
    status: str = ""
    parent_id: str = ""
    rate_limits: RateLimits | None = None
    event_times: list[datetime] = field(default_factory=list, repr=False)


@dataclass(slots=True)
class DashboardMetrics:
    sessions: list[SessionMetric]
    today_tokens: int
    week_tokens: int
    today_minutes: int
    today_sessions: int
    generated_at: datetime
    active_model: str = ""
    account_email: str = ""
    rate_limits: RateLimits | None = None


def _uri_to_path(uri: str) -> str:
    if not uri:
        return ""
    if uri.startswith("file://"):
        parsed = urlparse(uri)
        return unquote(parsed.path)
    return uri


def _load_annotations(antigravity_home: Path) -> dict[str, str]:
    titles: dict[str, str] = {}
    annotations_dir = antigravity_home / "annotations"
    if not annotations_dir.is_dir():
        return titles
    for pbtxt in annotations_dir.glob("*.pbtxt"):
        try:
            text = pbtxt.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        match = _PBTXT_TITLE_RE.search(text)
        if match and match.group(1).strip():
            titles[pbtxt.stem] = match.group(1).strip()
    return titles


@dataclass(slots=True)
class _SummaryRecord:
    title: str = ""
    cwd: str = ""
    status: str = ""
    agent_name: str = ""
    parent_id: str = ""
    updated_at: datetime | None = None


def _load_db_summaries(antigravity_home: Path) -> dict[str, _SummaryRecord]:
    records: dict[str, _SummaryRecord] = {}
    db_path = antigravity_home / "conversation_summaries.db"
    if not db_path.is_file():
        return records
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=1.0)
        conn.row_factory = sqlite3.Row
        with conn:
            cursor = conn.execute(
                "SELECT conversation_id, title, last_modified_time, workspace_uris, "
                "status, agent_name, parent_conversation_id FROM conversation_summaries"
            )
            for row in cursor:
                cid = str(row["conversation_id"] or "").strip()
                if not cid:
                    continue
                cwd = ""
                raw_uris = row["workspace_uris"]
                if isinstance(raw_uris, str) and raw_uris.strip():
                    try:
                        uris = json.loads(raw_uris)
                        if isinstance(uris, list) and uris:
                            cwd = _uri_to_path(str(uris[0]))
                    except json.JSONDecodeError:
                        pass
                records[cid] = _SummaryRecord(
                    title=str(row["title"] or "").strip(),
                    cwd=cwd,
                    status=str(row["status"] or "").strip(),
                    agent_name=str(row["agent_name"] or "").strip(),
                    parent_id=str(row["parent_conversation_id"] or "").strip(),
                    updated_at=_timestamp(row["last_modified_time"]),
                )
        conn.close()
    except (sqlite3.Error, OSError):
        pass
    return records


def _load_subagent_metadata(antigravity_home: Path) -> dict[str, tuple[str, str, str]]:
    """Return mapping of child_id -> (parent_id, role_title, cwd)."""
    mapping: dict[str, tuple[str, str, str]] = {}
    brain_dir = antigravity_home / "brain"
    if not brain_dir.is_dir():
        return mapping
    for sub_file in brain_dir.glob("*/.system_generated/subagents/*.json"):
        parent_id = sub_file.parents[2].name
        try:
            payload = json.loads(sub_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        child_id = str(payload.get("conversationId") or sub_file.stem).strip()
        descriptor = payload.get("subagentDescriptor")
        role = ""
        if isinstance(descriptor, dict):
            role = str(descriptor.get("role") or descriptor.get("typeName") or "").strip()
        uris = payload.get("workspaceUris")
        cwd = _uri_to_path(str(uris[0])) if isinstance(uris, list) and uris else ""
        if child_id:
            mapping[child_id] = (parent_id, role, cwd)
    return mapping


def _parse_cli_logs(antigravity_home: Path) -> tuple[str, str, dict[str, str]]:
    """Extract (account_email, active_model, workspace_by_conversation) from CLI logs."""
    email = ""
    active_model = ""
    workspaces: dict[str, str] = {}

    candidates: list[Path] = []
    cli_log = antigravity_home / "cli.log"
    if cli_log.is_file():
        candidates.append(cli_log)
    log_dir = antigravity_home / "log"
    if log_dir.is_dir():
        recent_logs = sorted(log_dir.glob("cli-*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
        for path in recent_logs[:3]:
            if path not in candidates:
                candidates.append(path)

    for path in reversed(candidates):
        try:
            with path.open(encoding="utf-8", errors="ignore") as stream:
                for line in stream:
                    if "OAuth: authenticated successfully as " in line:
                        match = _LOG_EMAIL_RE.search(line)
                        if match:
                            email = match.group(1).strip()
                    elif "Propagating selected model override to backend:" in line:
                        match = _LOG_MODEL_RE.search(line)
                        if match:
                            active_model = match.group(1).strip()
                    elif "Using workspace " in line:
                        match = _LOG_WORKSPACE_RE.search(line)
                        if match:
                            workspaces[match.group(2).strip()] = match.group(1).strip()
        except OSError:
            continue
    return email, active_model, workspaces


def transcript_paths(antigravity_home: Path) -> Iterable[Path]:
    brain_dir = antigravity_home / "brain"
    if brain_dir.is_dir():
        yield from brain_dir.glob("*/.system_generated/logs/transcript.jsonl")


def _activity_minutes(times: list[datetime], target: date) -> int:
    same_day = sorted({stamp for stamp in times if stamp.date() == target})
    if not same_day:
        return 0
    seconds = 60.0
    for earlier, later in zip(same_day, same_day[1:]):
        seconds += min((later - earlier).total_seconds(), 15 * 60)
    return max(1, round(seconds / 60))


def parse_transcript(
    path: Path,
    titles: dict[str, str],
    db_summaries: dict[str, _SummaryRecord],
    subagents: dict[str, tuple[str, str, str]],
    log_workspaces: dict[str, str],
    default_model: str,
    today: date,
    week_start: date,
) -> SessionMetric | None:
    session_id = path.parents[2].name
    db_rec = db_summaries.get(session_id)
    sub_meta = subagents.get(session_id)

    parent_id = (db_rec.parent_id if db_rec and db_rec.parent_id else "") or (
        sub_meta[0] if sub_meta else ""
    )
    name = (
        titles.get(session_id)
        or (db_rec.title if db_rec and db_rec.title else "")
        or (sub_meta[1] if sub_meta and sub_meta[1] else "")
        or (f"Subagent ({db_rec.agent_name})" if db_rec and db_rec.agent_name else "")
        or "Untitled task"
    )
    cwd = (
        log_workspaces.get(session_id)
        or (db_rec.cwd if db_rec and db_rec.cwd else "")
        or (sub_meta[2] if sub_meta and sub_meta[2] else "")
    )
    model = default_model or "Gemini"
    times: list[datetime] = []
    turns = 0
    usage = TokenUsage()
    today_tokens = 0
    week_tokens = 0

    try:
        stream = path.open(encoding="utf-8", errors="ignore")
    except OSError:
        return None

    with stream:
        for line in stream:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            stamp = _timestamp(record.get("created_at") or record.get("timestamp"))
            if stamp:
                times.append(stamp)

            step_type = record.get("type")
            if step_type == "USER_INPUT":
                turns += 1
                content = record.get("content")
                if isinstance(content, str) and "<USER_SETTINGS_CHANGE>" in content:
                    match = _MODEL_CHANGE_RE.search(content)
                    if match and match.group(1).strip():
                        model = match.group(1).strip()
            elif step_type == "PLANNER_RESPONSE":
                inp = int(record.get("input_tokens", 0) or 0)
                cached = int(record.get("cache_read_tokens", 0) or 0)
                out = int(record.get("output_tokens", 0) or 0)
                step_total = inp + cached + out
                if step_total > 0:
                    step_usage = TokenUsage(
                        input_tokens=inp,
                        cached_input_tokens=cached,
                        output_tokens=out,
                        total_tokens=step_total,
                    )
                    usage.add(step_usage)
                    if stamp:
                        step_date = stamp.date()
                        if step_date == today:
                            today_tokens += step_total
                        if week_start <= step_date <= today:
                            week_tokens += step_total

    if not times:
        if db_rec and db_rec.updated_at:
            times = [db_rec.updated_at]
        else:
            try:
                times = [datetime.fromtimestamp(path.stat().st_mtime).astimezone()]
            except OSError:
                return None

    return SessionMetric(
        session_id=session_id,
        name=name,
        cwd=cwd,
        model=model,
        started_at=min(times),
        updated_at=max(times),
        turns=turns,
        usage=usage,
        today_tokens=today_tokens,
        week_tokens=week_tokens,
        today_minutes=_activity_minutes(times, today),
        status=db_rec.status if db_rec else "",
        parent_id=parent_id,
        event_times=times,
    )


def collect_metrics(antigravity_home: Path, now: datetime | None = None) -> DashboardMetrics:
    now = (now or datetime.now().astimezone()).astimezone()
    today = now.date()
    week_start = today - timedelta(days=6)

    titles = _load_annotations(antigravity_home)
    db_summaries = _load_db_summaries(antigravity_home)
    subagents = _load_subagent_metadata(antigravity_home)
    account_email, active_model, log_workspaces = _parse_cli_logs(antigravity_home)

    raw_sessions: dict[str, SessionMetric] = {}
    for path in transcript_paths(antigravity_home):
        parsed = parse_transcript(
            path=path,
            titles=titles,
            db_summaries=db_summaries,
            subagents=subagents,
            log_workspaces=log_workspaces,
            default_model=active_model,
            today=today,
            week_start=week_start,
        )
        if parsed is not None:
            raw_sessions[parsed.session_id] = parsed

    all_event_times = [stamp for item in raw_sessions.values() for stamp in item.event_times]
    total_today_tokens = sum(item.today_tokens for item in raw_sessions.values())
    total_week_tokens = sum(item.week_tokens for item in raw_sessions.values())

    # Roll up subagent sessions into their parent session when the parent exists,
    # so recent tasks show top-level user conversations with full token totals.
    top_sessions: list[SessionMetric] = []
    for session in raw_sessions.values():
        if session.parent_id and session.parent_id in raw_sessions:
            parent = raw_sessions[session.parent_id]
            parent.usage.add(session.usage)
            parent.today_tokens += session.today_tokens
            parent.week_tokens += session.week_tokens
            parent.event_times.extend(session.event_times)
            if session.updated_at and (parent.updated_at is None or session.updated_at > parent.updated_at):
                parent.updated_at = session.updated_at
            parent.today_minutes = _activity_minutes(parent.event_times, today)
        else:
            top_sessions.append(session)

    top_sessions.sort(key=lambda item: item.updated_at or datetime.min.astimezone(), reverse=True)

    if not active_model and top_sessions:
        active_model = top_sessions[0].model

    return DashboardMetrics(
        sessions=top_sessions,
        today_tokens=total_today_tokens,
        week_tokens=total_week_tokens,
        today_minutes=_activity_minutes(all_event_times, today),
        today_sessions=sum(1 for item in top_sessions if item.today_minutes > 0),
        generated_at=now,
        active_model=active_model or "Gemini 4 Argon (Medium)",
        account_email=account_email,
        rate_limits=None,
    )
