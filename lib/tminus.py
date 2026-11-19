"""Shared helpers for the tminus calendar alarm tools.

No side effects at import time: every executable in bin/ stays a thin
front-end over these functions.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

APP_NAME = "tminus"
CATEGORY = "calendar"
ICON = "appointment-new"

KHAL_FIELDS = (
    "title",
    "uid",
    "calendar",
    "start-date-full",
    "start-time-full",
    "alarms-list",
)

RUN_DIR = Path(os.environ.get("XDG_RUNTIME_DIR") or "/tmp") / APP_NAME
STATE_FILE = RUN_DIR / "notifications.json"


# --------------------------------------------------------------------------- #
# Time helpers
# --------------------------------------------------------------------------- #
def local_now() -> datetime:
    """Current time with the local UTC offset attached."""
    return datetime.now().astimezone()


def parse_start(date_str: str | None, time_str: str | None) -> datetime | None:
    """Build an aware datetime from khal's start-date-full/start-time-full."""
    if not date_str:
        return None
    clock = (time_str or "00:00").strip()
    if clock in {"24:00", "24:00:00"}:
        clock = "00:00"
    try:
        naive = datetime.fromisoformat(f"{date_str}T{clock[:5]}")
    except ValueError:
        return None
    return naive.replace(tzinfo=local_now().tzinfo)


def format_countdown(seconds: float) -> str:
    """T-00:59:59 style countdown, second precision, days when needed."""
    total = max(0, int(seconds))
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    clock = f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{days}d {clock}" if days else clock


def format_start(start: datetime) -> str:
    """Show HH:MM, or MM-DD HH:MM for events beyond tomorrow."""
    now = local_now()
    if start.date() == now.date():
        return start.strftime("%H:%M")
    if start.date() == (now + timedelta(days=1)).date():
        return f"tomorrow {start:%H:%M}"
    return start.strftime("%m-%d %H:%M")


def urgency_for(seconds: float) -> str:
    if seconds <= 600:
        return "critical"
    if seconds <= 3600:
        return "normal"
    return "low"


# --------------------------------------------------------------------------- #
# Scanning
# --------------------------------------------------------------------------- #
def run_khal(days: int = 7) -> list[dict]:
    """Return khal's events as a flat, de-duplicated list of dicts."""
    if not shutil.which("khal"):
        raise RuntimeError("khal is not installed")

    cmd = ["khal", "list"]
    for field in KHAL_FIELDS:
        cmd.extend(("--json", field))
    cmd.extend(("--day-format", "", "now", f"{days}d"))

    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout).strip() or "khal failed")

    events: list[dict] = []
    seen: set[tuple] = set()
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line or line == "[]":
            continue
        try:
            chunk = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(chunk, list):
            continue
        for event in chunk:
            if not isinstance(event, dict):
                continue
            key = (
                event.get("uid", ""),
                event.get("start-date-full", ""),
                event.get("start-time-full", ""),
            )
            if key in seen:
                continue
            seen.add(key)
            events.append(event)
    return events


def active_alarms(events: list[dict], now: datetime | None = None) -> list[dict]:
    """Select events whose DISPLAY alarm has fired but which have not started.

    An event may carry several alarms; the most recently fired one wins.
    """
    now = now or local_now()
    result: list[dict] = []

    for event in events:
        alarms = event.get("alarms-list") or []
        if not isinstance(alarms, list) or not alarms:
            continue
        start = parse_start(
            event.get("start-date-full"), event.get("start-time-full")
        )
        if start is None or start <= now:
            continue

        fired: list[datetime] = []
        for alarm in alarms:
            if not isinstance(alarm, dict):
                continue
            delta = alarm.get("delta")
            if not isinstance(delta, (int, float)) or delta > 0:
                continue  # only alarms before the start produce a countdown
            alarm_at = start + timedelta(seconds=delta)
            if alarm_at <= now:
                fired.append(alarm_at)
        if not fired:
            continue

        alarm_at = max(fired)
        result.append(
            {
                "uid": str(event.get("uid") or ""),
                "title": str(event.get("title") or "(untitled)"),
                "calendar": str(event.get("calendar") or ""),
                "start": start.isoformat(timespec="seconds"),
                "alarm_at": alarm_at.isoformat(timespec="seconds"),
                "start_ts": start.timestamp(),
                "alarm_ts": alarm_at.timestamp(),
            }
        )

    result.sort(key=lambda item: (item["start_ts"], item["title"]))
    return result


def scan(days: int = 7, now: datetime | None = None) -> list[dict]:
    return active_alarms(run_khal(days), now)


# --------------------------------------------------------------------------- #
# Notification backends
# --------------------------------------------------------------------------- #
def backends() -> list[str]:
    """Available notification daemons, most generic first."""
    return [name for name in ("notify-send", "dunstify") if shutil.which(name)]


def notify(
    summary: str,
    body: str = "",
    *,
    app: str = APP_NAME,
    category: str = CATEGORY,
    urgency: str = "normal",
    expire_ms: int = 2500,
    replace_id: int | None = None,
    icon: str | None = ICON,
    backend: str = "auto",
) -> int | None:
    """Send (or replace) a notification and return its id, if available.

    Falls back to stderr when no notification daemon is present, so the
    tools remain useful over SSH and in plain ttys.
    """
    choices = backends()
    if backend != "auto":
        choices = [name for name in choices if name == backend]
    if not choices:
        print(f"[{app}] {summary}: {body}", file=sys.stderr)
        return None

    last_error = ""
    for name in choices:
        cmd = [
            name,
            "--app-name", app,
            "--category", category,
            "--urgency", urgency,
            "--expire-time", str(expire_ms),
            "--print-id",
        ]
        if replace_id is not None:
            cmd.extend(("--replace-id", str(replace_id)))
        if icon:
            cmd.extend(("--icon", icon))
        cmd.extend((summary, body))
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode == 0:
            for line in reversed(proc.stdout.splitlines()):
                if line.strip().isdigit():
                    return int(line.strip())
            return None
        last_error = (proc.stderr or proc.stdout).strip()

    print(f"[{app}] notification failed ({last_error}): {summary}: {body}",
          file=sys.stderr)
    return None


def close_notification(
    notification_id: int, *, backend: str = "auto"
) -> None:
    """Close a notification when the daemon supports it."""
    choices = backends()
    if backend != "auto":
        choices = [name for name in choices if name == backend]

    for name in choices:
        if name == "dunstify":
            proc = subprocess.run(
                [name, "--close", str(notification_id)],
                capture_output=True, check=False,
            )
            if proc.returncode == 0:
                return
        else:
            # notify-send has no close operation; an empty, instant
            # replacement removes the popup from the screen.
            subprocess.run(
                [name, "--replace-id", str(notification_id),
                 "--expire-time", "1", "", ""],
                capture_output=True, check=False,
            )
            return


# --------------------------------------------------------------------------- #
# Shared state (lets the timer-based sweep see what the watcher is showing)
# --------------------------------------------------------------------------- #
def write_state(ids: dict[str, int], alarms: list[dict]) -> None:
    try:
        RUN_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "updated": time.time(),
            "ids": {str(k): int(v) for k, v in ids.items()},
            "alarms": alarms,
        }
        tmp = STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(STATE_FILE)
    except OSError:
        pass


def read_state() -> dict:
    try:
        payload = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}
