#!/usr/bin/env python3
"""Send a desktop notification through whatever daemon is available.

Takes options or a JSON object on stdin, so other scripts can use it as
their notification back-end. Prints the notification id on stdout.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from tminus import (APP_NAME, CATEGORY, close_notification,  # noqa: E402
                    notify)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-s", "--summary")
    parser.add_argument("-b", "--body", default="")
    parser.add_argument("-a", "--app", default=APP_NAME)
    parser.add_argument("-c", "--category", default=CATEGORY)
    parser.add_argument("-u", "--urgency", default="normal",
                        choices=("low", "normal", "critical"))
    parser.add_argument("-t", "--expire", type=int, default=2500,
                        help="timeout in milliseconds (default: 2500)")
    parser.add_argument("-r", "--replace-id", type=int)
    parser.add_argument("-i", "--icon")
    parser.add_argument("--backend", default="auto",
                        choices=("auto", "notify-send", "dunstify"))
    parser.add_argument("--close", type=int, metavar="ID",
                        help="close an existing notification instead")
    args = parser.parse_args()

    if args.close is not None:
        close_notification(args.close, backend=args.backend)
        return 0

    values = vars(args).copy()
    if not args.summary:
        try:
            incoming = json.load(sys.stdin)
        except (json.JSONDecodeError, OSError):
            parser.error("give --summary or a JSON object on stdin")
        if not isinstance(incoming, dict):
            parser.error("stdin JSON must be an object")
        values.update({k: v for k, v in incoming.items() if k in values})
        if not values.get("summary"):
            parser.error("JSON object needs a summary")

    notification_id = notify(
        values["summary"],
        values["body"] or "",
        app=values["app"],
        category=values["category"],
        urgency=values["urgency"],
        expire_ms=values["expire"],
        replace_id=values["replace_id"],
        icon=values["icon"],
        backend=values["backend"],
    )
    if notification_id is not None:
        print(notification_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
