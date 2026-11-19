#!/usr/bin/env python3
"""Keep alarm notifications on screen with a live, second-accurate countdown.

The khal scan runs at a slower interval; the countdown itself is computed
from absolute timestamps every second, so no subprocess is spawned per tick.
"""

import argparse
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from tminus import (DISMISS_REASONS, GioNotifier, alarm_key, backends,  # noqa: E402
                    close_notification, format_countdown, format_start,
                    load_dismissed, local_now, log_event, notification_style,
                    notify, save_dismissed, scan, urgency_for, write_state)

STOP = False


def on_signal(_signum, _frame) -> None:
    global STOP
    STOP = True


def wait_for_tick(seconds: float) -> None:
    """Sleep until the next whole second, but react promptly to SIGTERM."""
    deadline = time.monotonic() + seconds
    while not STOP:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(0.2, remaining))


def make_notifier():
    """Prefer D-Bus (so close events are visible), fall back to notify-send."""
    try:
        return GioNotifier()
    except Exception as exc:  # no session bus, PyGObject missing, ...
        print(f"tminus-watch: D-Bus unavailable ({exc}); using notify-send",
              file=sys.stderr)
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=7,
                        help="how many days of khal events to scan (default: 7)")
    parser.add_argument("--scan-interval", type=int, default=15,
                        help="seconds between khal scans (default: 15)")
    parser.add_argument("--expire", type=int, default=2500,
                        help="notification timeout in ms (default: 2500)")
    args = parser.parse_args()

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)

    notifier = make_notifier()
    if notifier is None and not backends():
        print("tminus-watch: no notification daemon found; "
              "falling back to stderr every 30s", file=sys.stderr)
    have_daemon = notifier is not None or bool(backends())

    ids: dict[str, int] = {}
    shown: dict[str, dict] = {}
    dismissed = load_dismissed()
    alarms: list[dict] = []
    next_scan = 0.0

    while not STOP:
        if notifier is not None:
            notifier.pump()
            changed = False
            for notification_id, reason, key in notifier.drain_closed():
                if reason not in DISMISS_REASONS or not key:
                    continue
                ids.pop(key, None)
                if key in dismissed:
                    continue
                dismissed.add(key)
                changed = True
                log_event("dismiss", shown.get(key, {}),
                          notification_id=notification_id, reason=reason)
                shown.pop(key, None)
            if changed:
                save_dismissed(dismissed)

        now_wall = local_now()
        now_ts = time.time()

        if now_ts >= next_scan:
            try:
                alarms = scan(args.days, now_wall)
                next_scan = now_ts + args.scan_interval
            except RuntimeError as exc:
                print(f"tminus-watch: scan failed: {exc}", file=sys.stderr)
                next_scan = now_ts + 30

        active_keys: set[str] = set()
        for alarm in alarms:
            key = alarm_key(alarm)
            active_keys.add(key)
            remaining = alarm["start_ts"] - time.time()
            if remaining <= 0 or not have_daemon or key in dismissed:
                continue
            start = datetime.fromisoformat(alarm["start"])
            body = (f"Starts {format_start(start)}"
                    f" · in {format_countdown(remaining)}")
            colors = notification_style(alarm, remaining)
            if notifier is not None:
                notification_id = notifier.notify(
                    key, alarm["title"], body,
                    urgency=urgency_for(remaining),
                    expire_ms=args.expire,
                    replace_id=ids.get(key), colors=colors,
                )
            else:
                notification_id = notify(
                    alarm["title"], body,
                    urgency=urgency_for(remaining),
                    expire_ms=args.expire,
                    replace_id=ids.get(key), colors=colors,
                )
            if notification_id is not None:
                ids[key] = notification_id
                if key not in shown:
                    shown[key] = alarm
                    log_event("shown", alarm, notification_id=notification_id)

        for key in list(ids):
            if key not in active_keys:
                notification_id = ids.pop(key)
                if notifier is not None:
                    notifier.close(notification_id)
                else:
                    close_notification(notification_id)
                if dismissed.pop(key, None) is not None:
                    save_dismissed(dismissed)
                if key in shown:
                    log_event("ended", shown.pop(key))

        write_state(ids, alarms)

        # Align to the wall clock so the displayed second actually changes
        # once per second, not once per loop iteration.
        tick = 1.0 - (time.time() % 1.0)
        if not have_daemon:
            tick = 30.0
        wait_for_tick(tick)

    for notification_id in ids.values():
        if notifier is not None:
            notifier.close(notification_id)
        else:
            close_notification(notification_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
