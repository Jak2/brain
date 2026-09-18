#!/usr/bin/env python3
"""brain — a mentor that lives in your repo. Standard library only."""
import argparse
import datetime
import json
import re
import subprocess
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


def git(args, cwd):
    """Run git. Returns (returncode, output). Never raises - git may be absent."""
    try:
        done = subprocess.run(
            ["git"] + args, cwd=str(cwd),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        return done.returncode, done.stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, str(exc)


def has_remote(repo):
    code, out = git(["remote"], repo)
    return code == 0 and bool(out.strip())


STARTER = {
    "target.md": (
        "# Target\n\n"
        "_Written by the cold-start interview. Run `/start` and answer honestly._\n\n"
        "## Role\n\n## Ranked gaps\n"
    ),
    "questions.md": (
        "# Open questions\n\n"
        "_One line each: `- YYYY-MM-DD the question`. "
        "Closed automatically after the expiry window._\n"
    ),
    "HANDOVER.md": (
        "# Handover\n\n"
        "_In-flight session state only. Your knowledge is in notes/ and skills/._\n\n"
        "Nothing in flight.\n"
    ),
}


def cmd_init(config, root=ROOT):
    """Create data/ and its own git repo. Idempotent. Never overwrites content."""
    data = root / config["paths"]["data"]
    for key in ("notes", "skills", "log", "local"):
        (root / config["paths"][key]).mkdir(parents=True, exist_ok=True)

    for name, body in STARTER.items():
        path = data / name
        if not path.exists():
            path.write_text(body, encoding="utf-8")

    gitignore = data / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("local/\n", encoding="utf-8")

    state = data / "state.json"
    if not state.exists():
        state.write_text(json.dumps({
            "schema": 1, "last_start": None, "last_end": None,
            "in_flight": None, "bootstrapped": [],
        }, indent=2) + "\n", encoding="utf-8")

    if not (data / ".git").exists():
        code, out = git(["init"], data)
        if code != 0:
            warn("could not create a git repo in data/ (%s) - history disabled, "
                 "everything else works" % out)

    if (data / ".git").exists() and has_remote(data):
        warn("data/ HAS A GIT REMOTE. The no-push guarantee is void. "
             "Remove it with: git -C %s remote remove <name>" % data)

    print("ready: " + str(data))
    return 0


def build_parser():
    parser = argparse.ArgumentParser(prog="brain.py", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("selftest", help="verify the engine")
    sub.add_parser("init", help="create data/ and its local-only git repo")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.command == "selftest":
        import selftest
        return selftest.run()
    if args.command == "init":
        return cmd_init(load_config())
    return 0


if __name__ == "__main__":
    sys.exit(main())
