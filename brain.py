#!/usr/bin/env python3
"""brain — a mentor that lives in your repo. Standard library only."""
import argparse
import datetime
import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath

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


def _unsafe_relpath(value):
    """True if a paths value is absolute (POSIX or Windows-style) or escapes the
    repo via a '..' segment.

    is_absolute() is checked under both flavors - each catches an absolute form
    the other doesn't ("/etc/passwd" is only absolute under PurePosixPath,
    "C:\\foo" only under PureWindowsPath). The '..' check only needs
    PureWindowsPath: it splits on '\\' and '/', a superset of PurePosixPath's
    '/'-only split, so any '..' component PurePosixPath would find,
    PureWindowsPath finds too - confirmed for mixed separators like "a\\../b".

    Pure-path check only - the target may not exist yet, and Path.resolve()
    would hit the disk and follow symlinks.
    """
    return (
        PurePosixPath(value).is_absolute()
        or PureWindowsPath(value).is_absolute()
        or ".." in PureWindowsPath(value).parts
    )


def _outside_data_root(value, data_value):
    """True if `value` does not sit strictly inside `data_value`.

    Checked under both PurePosixPath and PureWindowsPath - the real join
    later uses the platform-native Path (PurePosixPath on Linux/macOS,
    PureWindowsPath on Windows), and the two flavors split a string like
    "data\\sibling" differently (Windows treats '\\' as a separator, POSIX
    doesn't). Checking one flavor only lets a value that is in-bounds under
    that flavor slip past while landing outside the root under the other -
    exactly the asymmetry that made the backslash bypass possible. A value
    must be contained under both to be accepted.

    Pure PurePath-parts comparison, same approach as _unsafe_relpath - no
    filesystem access, and a whole-component compare so "data2" can't pass as
    inside "data".
    """
    def outside(flavor):
        parts = flavor(value).parts
        data_parts = flavor(data_value).parts
        return parts[: len(data_parts)] != data_parts or len(parts) <= len(data_parts)

    return outside(PurePosixPath) or outside(PureWindowsPath)


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
    # config.json is hand-edited; a wrong-shaped value must not reach any caller.
    for key, default in DEFAULT_CONFIG.items():
        if type(config[key]) is not type(default):
            warn("config.json: %r is %s, expected %s - using default" % (
                key, type(config[key]).__name__, type(default).__name__))
            config[key] = json.loads(json.dumps(default))
    # Same risk one level down: paths/policy values feed arithmetic and
    # comparisons directly, so a wrong-shaped value there must not reach any caller.
    for section in ("paths", "policy"):
        for key, default in DEFAULT_CONFIG[section].items():
            if type(config[section][key]) is not type(default):
                warn("config.json: %s.%r is %s, expected %s - using default" % (
                    section, key, type(config[section][key]).__name__, type(default).__name__))
                config[section][key] = json.loads(json.dumps(default))
    # paths.data and paths.local are pinned to their defaults: the outer
    # .gitignore matches the literal string "data/", and data/.gitignore
    # hardcodes "local/" - renaming either one silently drops an ignore layer
    # and can push private notes into the pushable public repo. Renaming
    # notes/skills/log stays supported and goes through the containment
    # checks below, same as before.
    data_default = DEFAULT_CONFIG["paths"]["data"]
    data_value = config["paths"]["data"]
    if data_value != data_default:
        warn("config.json: paths.'data' is pinned to %r (got %r) - renaming it "
             "would move notes outside the outer .gitignore - using default"
             % (data_default, data_value))
        data_value = data_default
    config["paths"]["data"] = data_value

    for key, default in DEFAULT_CONFIG["paths"].items():
        if key == "data":
            continue
        value = config["paths"][key]
        if key == "local" and value != default:
            warn("config.json: paths.'local' is pinned to %r (got %r) - renaming it "
                 "would drop data/.gitignore's inner ignore layer - using default"
                 % (default, value))
            config["paths"][key] = default
            continue
        if _unsafe_relpath(value):
            warn("config.json: paths.%r is not a safe relative path (%r) - using default"
                 % (key, value))
            config["paths"][key] = default
            continue
        # data/ is the only unpushable repo (no remote, gitignored in the outer
        # repo) - anything outside it is one migrate away from leaking notes
        # into the public repo as tracked files.
        if _outside_data_root(value, data_value):
            warn("config.json: paths.%r (%r) is not inside paths.data (%r) under both "
                 "path flavors - use forward slashes ('/'), not backslashes - using default"
                 % (key, value, data_value))
            config["paths"][key] = default
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


def render_frontmatter(meta, body):
    """Inverse of parse_frontmatter. Scalars stringify as-is; lists render as
    [a, b] to round-trip through _coerce unchanged."""
    lines = []
    for key, value in meta.items():
        if isinstance(value, list):
            rendered = "[%s]" % ", ".join(str(v) for v in value)
        else:
            rendered = str(value)
        lines.append("%s: %s" % (key, rendered))
    return "---\n%s\n---\n\n%s" % ("\n".join(lines), body)


def read_text_safe(path):
    """File contents, or None if unreadable for any reason. Never raises.

    UnicodeDecodeError is a ValueError, not an OSError - a single bad byte in a
    note must not take down the briefing.
    """
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, ValueError) as exc:
        warn("%s: %s - skipped" % (path.name, exc))
        return None


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


LINK_RE = re.compile(r"\[\[([^\[\]\n]+)\]\]")


def extract_links(body):
    """Every [[wikilink]] target in order, blanks discarded."""
    return [m.strip() for m in LINK_RE.findall(body) if m.strip()]


def build_graph(config, root=ROOT):
    """Return (adjacency, nodes). nodes maps id -> 'note' | 'skill' | 'broken'."""
    adj, nodes = {}, {}
    notes_dir = root / config["paths"]["notes"]

    for skill in read_skills(config, root):
        nodes[skill["slug"]] = "skill"
        adj.setdefault(skill["slug"], set())

    if notes_dir.is_dir():
        for path in sorted(notes_dir.glob("*.md")):
            text = read_text_safe(path)
            if text is None:
                continue
            try:
                _, body = parse_frontmatter(text)
            except FrontmatterError as exc:
                warn("%s: %s - skipped" % (path.name, exc))
                continue
            node = path.stem
            if nodes.get(node) == "skill":
                warn("%s: id %r collides with a skill of the same name - "
                     "keeping skill classification" % (path.name, node))
            else:
                nodes[node] = "note"
            adj.setdefault(node, set())
            for target in extract_links(body):
                if target == node:
                    continue  # ponytail: self-links are noise, not structure
                adj.setdefault(target, set())
                adj[node].add(target)
                adj[target].add(node)
                nodes.setdefault(target, "broken")
    return adj, nodes


def articulation_points(adj):
    """Hopcroft-Tarjan cut vertices.

    ponytail: recursive DFS. Verified fine at 900 chained notes, RecursionError
    at 1200; make it iterative if a RecursionError ever appears.
    """
    disc, low, parent, out = {}, {}, {}, set()
    counter = [0]

    def dfs(u):
        disc[u] = low[u] = counter[0]
        counter[0] += 1
        children = 0
        for v in sorted(adj.get(u, ())):
            if v not in disc:
                parent[v] = u
                children += 1
                dfs(v)
                low[u] = min(low[u], low[v])
                if u in parent and low[v] >= disc[u]:
                    out.add(u)
            elif v != parent.get(u):
                low[u] = min(low[u], disc[v])
        if u not in parent and children > 1:
            out.add(u)

    for node in sorted(adj):
        if node not in disc:
            dfs(node)
    return out


def cmd_graph(config, root=ROOT):
    adj, nodes = build_graph(config, root)
    note_count = sum(1 for kind in nodes.values() if kind == "note")
    minimum = config["policy"]["graph_min_notes"]

    print("GRAPH %d notes, %d nodes, %d edges"
          % (note_count, len(nodes), sum(len(v) for v in adj.values()) // 2))

    broken = sorted(n for n, kind in nodes.items() if kind == "broken")
    if broken:
        print("broken links: " + ", ".join(broken))

    orphans = sorted(n for n, kind in nodes.items()
                     if kind == "note" and not adj.get(n))
    if orphans:
        print("orphans: " + ", ".join(orphans))

    if note_count < minimum:
        print("metrics: need %d notes for hubs/frontier/bridges (have %d)"
              % (minimum, note_count))
        return 0

    ranked = sorted(adj, key=lambda n: (-len(adj[n]), n))
    hubs = ranked[: max(1, len(ranked) // 10)]
    print("hubs: " + ", ".join(hubs))

    hub_set = set(hubs)
    frontier = sorted(
        (s["slug"] for s in read_skills(config, root)
         if isinstance(s["level"], int) and s["level"] <= 1
         and adj.get(s["slug"], set()) & hub_set),
        key=lambda slug: -len(adj.get(slug, set())))
    print("frontier: " + (", ".join(frontier) if frontier else "none"))

    bridges = sorted(n for n in articulation_points(adj) if len(adj.get(n, ())) >= 2)
    print("bridges: " + (", ".join(bridges) if bridges else "none"))
    return 0


def read_skills(config, root=ROOT):
    """Every parseable skill file. Malformed files warn and are skipped."""
    folder = root / config["paths"]["skills"]
    skills = []
    if not folder.is_dir():
        return skills
    for path in sorted(folder.glob("*.md")):
        text = read_text_safe(path)
        if text is None:
            continue
        try:
            meta, _ = parse_frontmatter(text)
        except FrontmatterError as exc:
            warn("%s: %s - skipped" % (path.name, exc))
            continue
        meta["path"] = path
        slug = meta.get("slug")
        if slug is not None and not isinstance(slug, str):
            warn("%s: slug is %s, not a string - using the filename instead"
                 % (path.name, type(slug).__name__))
            meta["slug"] = path.stem
        else:
            meta.setdefault("slug", path.stem)
        meta.setdefault("level", 0)
        meta.setdefault("target_level", 3)
        skills.append(meta)
    return skills


def due_skills(skills, config, when):
    """Overdue first, most overdue at the front. Mastered skills leave the rotation."""
    mastery = config["policy"]["mastery_level"]
    out = []
    for skill in skills:
        if isinstance(skill["level"], int) and skill["level"] >= mastery:
            continue
        # A missing or garbled date means due now - never silently never-due.
        review = parse_date(skill.get("next_review"), when)
        if review <= when:
            skill["overdue_days"] = (when - review).days
            out.append(skill)
    return sorted(out, key=lambda s: -s["overdue_days"])


def read_state(config, root=ROOT):
    default = {"schema": 1, "in_flight": None, "bootstrapped": []}
    path = root / config["paths"]["data"] / "state.json"
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except (OSError, ValueError) as exc:
        warn("%s: %s - resume point lost, using default" % (path.name, exc))
        return default
    return state if isinstance(state, dict) else default


def _open_questions(config, root):
    path = root / config["paths"]["data"] / "questions.md"
    text = read_text_safe(path)
    lines = text.splitlines() if text else []
    return [line[2:].strip() for line in lines if line.startswith("- ")]


def cmd_due(config, root=ROOT):
    """Print the briefing. Must never raise - a failed briefing kills the habit."""
    data = root / config["paths"]["data"]
    if not data.is_dir():
        print("no data yet - run: python brain.py init")
        return 0

    print("BRIEFING " + today().isoformat())

    state = read_state(config, root)
    flight = state.get("in_flight")
    if not isinstance(flight, dict):
        flight = None
    if flight:
        print("interrupted: %s/%s (%s attempts, opened %s)" % (
            flight.get("persona", "?"), flight.get("skill", "?"),
            flight.get("attempts", 0), flight.get("opened", "?")))

    skills = read_skills(config, root)
    if not skills:
        print("cold start: no skills yet - run the interview in templates/interview.md")
        return 0

    due = due_skills(skills, config, today())[: config["policy"]["daily_items"]]
    if due:
        print("due: " + ", ".join(
            "%s(L%s, %s)" % (s["slug"], s["level"],
                             "due today" if s["overdue_days"] == 0
                             else "%dd overdue" % s["overdue_days"])
            for s in due))
    else:
        print("due: nothing")

    gaps = sorted(
        (s for s in skills if isinstance(s["level"], int)
         and isinstance(s["target_level"], int) and s["level"] < s["target_level"]),
        key=lambda s: (s["level"] - s["target_level"], s["slug"]))
    if gaps:
        top = gaps[0]
        print("gap: %s (L%s, target L%s)" % (top["slug"], top["level"], top["target_level"]))

    questions = _open_questions(config, root)
    if questions:
        print("question: " + questions[0])

    pending = decay_actions(config, root)
    if pending:
        print("decay: %d pending - run: python brain.py decay" % len(pending))
    return 0


def decay_actions(config, root=ROOT):
    """Everything that should leave the system. The drain that keeps the queue finite."""
    policy = config["policy"]
    now = today()
    actions = []

    for skill in read_skills(config, root):
        if isinstance(skill["level"], int) and skill["level"] >= policy["mastery_level"]:
            actions.append("mastered: %s leaves the review rotation" % skill["slug"])

    path = root / config["paths"]["data"] / "questions.md"
    text = read_text_safe(path)
    lines = text.splitlines() if text else []
    for line in lines:
        if not line.startswith("- "):
            continue
        head, _, rest = line[2:].strip().partition(" ")
        asked = parse_date(head)
        if asked and (now - asked).days > policy["question_expiry_days"]:
            actions.append("expired question (%dd): %s" % ((now - asked).days, rest))

    adj, nodes = build_graph(config, root)
    notes_dir = root / config["paths"]["notes"]
    for node, kind in sorted(nodes.items()):
        if kind != "note" or adj.get(node):
            continue
        note_path = notes_dir / (node + ".md")
        text = read_text_safe(note_path)
        if text is None:
            continue
        try:
            meta, _ = parse_frontmatter(text)
        except FrontmatterError:
            continue
        created = parse_date(meta.get("created"))
        if created and (now - created).days > policy["orphan_archive_days"]:
            actions.append("archive candidate (orphan %dd): %s"
                           % ((now - created).days, node))
    return actions


def cmd_decay(config, root=ROOT):
    actions = decay_actions(config, root)
    if not actions:
        print("decay: nothing to drain")
        return 0
    print("DECAY %d action(s) - Archivist decides, never delete unasked"
          % len(actions))
    for action in actions:
        print("  " + action)
    return 0


def cmd_schedule(slug, passed, config, root=ROOT):
    """Record a review outcome. The only command that writes to a skill file -
    every other command stays read-only. Date arithmetic lives here, never in
    the assistant."""
    match = next((s for s in read_skills(config, root) if s["slug"] == slug), None)
    if match is None:
        warn("schedule: unknown skill %r" % slug)
        return 1

    path = match["path"]
    text = read_text_safe(path)
    if text is None:
        return 1
    try:
        meta, body = parse_frontmatter(text)
    except FrontmatterError as exc:
        warn("schedule: %s: %s - not writing" % (path.name, exc))
        return 1

    intervals = config["policy"]["intervals_days"]
    current = meta.get("interval_days")
    if not isinstance(current, int):
        current = intervals[0]
    interval = next_interval(current, intervals, passed)
    now = today()
    meta["interval_days"] = interval
    meta["last_reviewed"] = now.isoformat()
    meta["next_review"] = (now + datetime.timedelta(days=interval)).isoformat()

    path.write_text(render_frontmatter(meta, body), encoding="utf-8")

    print("scheduled: %s interval_days=%d last_reviewed=%s next_review=%s"
          % (slug, interval, meta["last_reviewed"], meta["next_review"]))
    level = meta.get("level")
    if passed and isinstance(level, int) and level >= config["policy"]["mastery_level"]:
        print("mastered: %s leaves the review rotation" % slug)
    return 0


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
            "in_flight": None,
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


ASSISTANTS = ["claude", "cursor", "copilot", "gemini"]


def cmd_migrate(config, root=ROOT):
    """Reconcile folders on disk with config.json paths. Prefers `git mv` for history."""
    data = root / config["paths"]["data"]
    moved = 0
    collision = False
    # Defaults are the only record of where a folder used to live.
    for key, default in DEFAULT_CONFIG["paths"].items():
        if key == "data":
            continue
        target = root / config["paths"][key]
        old = root / default
        if target.exists():
            # target == old means config still points at the default - normal,
            # not a collision. Otherwise, if old still holds data, the target
            # existing is not proof a migration ever completed.
            if old != target and old.is_dir() and any(old.iterdir()):
                warn("paths.%s: %s already exists and %s still holds data - "
                     "not a completed migration, leaving data in place" % (key, target, old))
                collision = True
            continue
        if not old.is_dir():
            continue
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            code, out = git(["mv", str(old), str(target)], data)
            if code != 0:
                old.rename(target)  # git absent or path untracked - plain move still works
        except OSError as exc:
            warn("could not move %s -> %s (%s)" % (old, target, exc))
            return 1
        print("moved %s -> %s" % (default, config["paths"][key]))
        moved += 1

    if collision:
        return 1

    if not moved:
        print("nothing to migrate - folders already match config.json")
        return 0

    # Link targets are file stems, so a folder move leaves every [[link]] valid.
    # Verify rather than assume.
    adj, nodes = build_graph(config, root)
    broken = sorted(n for n, kind in nodes.items() if kind == "broken")
    if broken:
        warn("broken links after migrate: " + ", ".join(broken))
    print("migrated %d folder(s), %d broken link(s)" % (moved, len(broken)))
    return 0


def cmd_bootstrap(assistant, config, root=ROOT):
    """Copy one assistant's adapter into place. Additive and idempotent."""
    if assistant not in ASSISTANTS:
        warn("unknown assistant %r - known: %s. AGENTS.md alone works; "
             "you only lose slash commands." % (assistant, ", ".join(ASSISTANTS)))
        return 1

    source = root / "adapters" / assistant
    if not source.is_dir():
        warn("no adapter folder at " + str(source))
        return 1

    installed = 0
    for item in sorted(source.rglob("*")):
        if item.is_dir():
            continue
        target = root / item.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.read_bytes() == item.read_bytes():
            continue  # unchanged, skip - an edited file is overwritten below to match source
        target.write_bytes(item.read_bytes())
        installed += 1

    listed = config.setdefault("assistants", [])
    if assistant not in listed:
        listed.append(assistant)
        (root / "config.json").write_text(
            json.dumps(config, indent=2) + "\n", encoding="utf-8")

    print("%s adapter ready (%d file(s) written). Other adapters untouched."
          % (assistant, installed))
    return 0


def build_parser():
    parser = argparse.ArgumentParser(prog="brain.py", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("selftest", help="verify the engine")
    sub.add_parser("init", help="create data/ and its local-only git repo")
    sub.add_parser("due", help="today's briefing")
    sub.add_parser("graph", help="orphans, hubs, frontier, bridges")
    sub.add_parser("migrate", help="reconcile folders with config.json paths")
    sub.add_parser("decay", help="what should leave the system")
    sched = sub.add_parser("schedule", help="record a review outcome for one skill")
    sched.add_argument("slug")
    sched.add_argument("outcome", choices=["pass", "fail"])
    boot = sub.add_parser("bootstrap", help="install one assistant's adapter")
    boot.add_argument("assistant", choices=ASSISTANTS)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.command == "selftest":
        import selftest
        return selftest.run()
    if args.command == "init":
        return cmd_init(load_config())
    if args.command == "due":
        return cmd_due(load_config())
    if args.command == "graph":
        return cmd_graph(load_config())
    if args.command == "migrate":
        return cmd_migrate(load_config())
    if args.command == "decay":
        return cmd_decay(load_config())
    if args.command == "schedule":
        return cmd_schedule(args.slug, args.outcome == "pass", load_config())
    if args.command == "bootstrap":
        return cmd_bootstrap(args.assistant, load_config())
    return 0


if __name__ == "__main__":
    sys.exit(main())
