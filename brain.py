#!/usr/bin/env python3
"""brain — a mentor that lives in your repo. Standard library only."""
import argparse
import datetime
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

DEFAULT_CONFIG = {
    "schema": 1,
    "paths": {
        "data": "data",
        "notes": "data/notes",
        "skills": "data/skills",
        "log": "data/log",
        "local": "data/local",
    },
    "policy": {
        "intervals_days": [1, 3, 7, 16, 35],
        "mastery_level": 5,
        "question_expiry_days": 60,
        "orphan_archive_days": 90,
        "graph_min_notes": 30,
        "daily_items": 3,
    },
    "assistants": [],
}


class FrontmatterError(ValueError):
    """A frontmatter block could not be parsed."""


def warn(msg):
    print("warn: " + msg, file=sys.stderr)


def load_config():
    """Config merged over defaults. Unreadable config falls back, never raises."""
    path = ROOT / "config.json"
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return json.loads(json.dumps(DEFAULT_CONFIG))
    except (OSError, ValueError) as exc:
        warn("config.json unreadable (%s) - using built-in defaults" % exc)
        return json.loads(json.dumps(DEFAULT_CONFIG))
    config = json.loads(json.dumps(DEFAULT_CONFIG))
    for key, value in loaded.items():
        if key in ("paths", "policy") and isinstance(value, dict):
            config[key].update(value)
        else:
            config[key] = value
    return config


def _coerce(value):
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        return [v.strip() for v in inner.split(",") if v.strip()] if inner else []
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    return value


def parse_frontmatter(text):
    """Return (meta, body). Raise FrontmatterError if the block is malformed."""
    if not text.startswith("---"):
        raise FrontmatterError("no frontmatter block")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise FrontmatterError("unterminated frontmatter block")
    meta = {}
    for lineno, raw in enumerate(parts[1].strip().splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            raise FrontmatterError("line %d: missing ':' in %r" % (lineno, line))
        key, _, value = line.partition(":")
        meta[key.strip()] = _coerce(value.strip())
    return meta, parts[2].lstrip("\n")


def today():
    return datetime.date.today()


def parse_date(value, fallback=None):
    """Parse an ISO date. Never raises - bad input yields the fallback."""
    try:
        return datetime.date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return fallback


def next_interval(current, intervals, passed):
    """Advance one step on pass, back one on fail. Clamped at both ends."""
    if current not in intervals:
        return intervals[0]
    i = intervals.index(current)
    return intervals[min(i + 1, len(intervals) - 1)] if passed else intervals[max(i - 1, 0)]


def build_parser():
    parser = argparse.ArgumentParser(prog="brain.py", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("selftest", help="verify the engine")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.command == "selftest":
        import selftest
        return selftest.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
