#!/usr/bin/env python3
"""Print the alarms that are currently ringing, as JSON on stdout."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from tminus import scan  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=7,
                        help="how many days of khal events to scan (default: 7)")
    parser.add_argument("--pretty", action="store_true",
                        help="indent the JSON output")
    args = parser.parse_args()

    try:
        alarms = scan(args.days)
    except RuntimeError as exc:
        print(f"tminus-scan: {exc}", file=sys.stderr)
        return 1

    json.dump(alarms, sys.stdout, ensure_ascii=False,
              indent=2 if args.pretty else None)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
