# tminus

Live, second-accurate countdowns for calendar alarms in desktop notifications.
It watches the `VALARM` entries recognised by `khal`: as soon as an alarm fires
but the event has not started yet, the notification appears and the remaining
time is refreshed every second.

It is not tied to dunst: the watcher sends `Notify` directly over the
freedesktop D-Bus interface (works with mako, swaync, dunst and similar), so it
can also observe when the user closes a notification. `notify-send` and
`dunstify` remain as fallbacks; if neither D-Bus nor those tools are available,
the text goes to stderr.

## Tools

| Command | Purpose |
|---|---|
| `bin/tminus-scan` | List currently active alarms as JSON. |
| `bin/tminus-notify` | Generic notification sender: ID replacement, urgency, category, stdin JSON. |
| `bin/tminus-watch` | The watcher process: refreshes notifications every second. |
| `bin/tminus-sweep` | One-shot check: keeps the watcher alive and reports missed alarms. |

Shared logic lives in `lib/tminus.py`; the scripts in `bin/` are thin
front-ends.

## Installation

```sh
./install.sh
```

The script links the units into `~/.config/systemd/user/`, then enables and
starts `tminus.service` and `tminus.timer`. `./uninstall.sh` reverses that:
it stops and disables the units and removes the symlinks. Add `--purge` to
also delete the runtime state and the event log. Calendar data is never
touched.

The dunst styling is in `dunst/tminus.conf` — append it to your
`~/.config/dunst/dunstrc` and reload dunst (`dunstctl reload`). Other
notification daemons need no extra step.

Running manually without systemd:

```sh
bin/tminus-scan --pretty
bin/tminus-watch --scan-interval 15
bin/tminus-notify -s 'Title' -b 'Message' -u critical
echo '{"summary":"Title","body":"Message"}' | bin/tminus-notify
```

## How it works

- `khal list --json` provides the events, their UIDs, start times and the
  `alarms-list` field (`delta`: seconds between the alarm and the start).
  Recurrence and time zones are handled by `khal`.
- Active window: `alarm time <= now < start`. With multiple alarms, the most
  recently fired one wins. If the machine was asleep or the service was not
  running, `tminus-sweep` sends the missed notification on the next timer
  cycle.
- The watcher re-reads the calendar every 15 seconds, but computes the
  countdown from absolute timestamps once per second — so it stays accurate
  without spawning `khal` on every tick.
- Notifications do not pile up: the `replaces_id` field of `Notify` (or
  `notify-send -r` in fallback mode) reuses the same notification every second.
- Displayed IDs are also recorded in `$XDG_RUNTIME_DIR/tminus/notifications.json`
  so the sweep can see what is already on screen.

## Dismissal and event log

Closing a notification (middle-click, `dunstctl close`, or the equivalent in
another daemon) is detected through the `NotificationClosed` D-Bus signal.
The watcher records that alarm as dismissed and does **not** bring it back on
the next tick; the timer-based sweep skips it as well. The dismissal state is
kept in `$XDG_RUNTIME_DIR/tminus/dismissed.json`, so it disappears on reboot —
if the machine was off while an alarm fired, the sweep can still show the
missed notification on the next cycle.

State changes are appended as one JSON line each to
`$XDG_STATE_HOME/tminus/events.log` (`~/.local/state/tminus/events.log` by
default): `shown`, `dismiss`, `ended` and `catchup`. The once-per-second
countdown refreshes are deliberately not logged.

## Colours

Dunst colour hints are used, so other daemons simply ignore them:

- The notification frame uses the calendar's own colour, read from the vdir
  `color` file (`~/.local/share/calendars/<name>/color`, synced by vdirsyncer
  `color` metadata). Set `TMINUS_CALENDAR_DIR` to override the calendar root.
- In the final minute before the event starts, the frame and text switch to a
  red highlight (`#f38ba8` by default, override with `TMINUS_URGENT_COLOR`).
- If a calendar has no colour file, the daemon's category styling applies.

## Tuning

```sh
bin/tminus-watch --days 14 --scan-interval 10 --expire 3000
bin/tminus-sweep --days 14 --expire 15000
```

Edit the `ExecStart` line in `tminus.service` for permanent flag changes.
Urgency is automatic: `normal` within one hour, `critical` within ten minutes.
