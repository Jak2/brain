# brain — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a mentor system that drives whatever AI coding assistant the user already has, teaches from real work plus role gaps, and keeps all learning data local to the machine.

**Architecture:** Markdown protocol (`AGENTS.md` + `personas/`) tells the assistant how to behave; a stdlib-only `brain.py` owns every deterministic fact (dates, scheduling, graph metrics); learning data lives in `data/`, a nested git repo with no remote so it cannot be pushed. Per-assistant adapters are additive one-line pointers to `AGENTS.md`.

**Tech Stack:** Python 3.9+ standard library only. Git. Markdown. No pip packages, no network, ever.

Spec: [design.md](design.md). Rationale: [../DECISIONS.md](../DECISIONS.md).

## Global Constraints

- **Python 3.9+, standard library only.** No third-party import may appear in any file. This is a hard constraint (C2) — a dependency makes the tool unusable on the target machine.
- **Cross-platform.** Use `pathlib`, never string path concatenation. No shell pipelines, no POSIX-only calls.
- **`brain.py` decides facts; the assistant decides language.** Dates, counts, scheduling, graph metrics → Python. Explanations, questions, note wording → assistant. Never mix.
- **Nothing in `brain.py` may raise an unhandled exception on the `due` path.** Malformed input warns to stderr and is skipped.
- **`data/` must never have a git remote.** Any code that touches git in `data/` verifies this.
- **No personal data in the system repo.** The repo is public (ADR-008).
- Repo root for all paths below: `my_learning_projects/ideas/brain/`.
- **Every file read goes through `read_text_safe(path)`** (added in Task 4). Never call `path.read_text()` directly in a code path reachable from a command. `UnicodeDecodeError` is a `ValueError`, not an `OSError` — `except OSError` does not catch a file with a bad byte in it, and that crashes the briefing. One guard, all callers.
- **Anything parsed from disk is shape-checked before use.** Valid JSON is not necessarily the expected type: `json.loads` on `42` succeeds and then `.get()` raises. Validate `isinstance(..., dict)` before treating a parsed value as a mapping.
- **`selftest` output stays pristine.** Every `cmd_*` prints to stdout. A test that calls one directly must wrap the call in `selftest._silent(...)` (added in Task 2) so briefing text never interleaves with pass/fail lines. Applies to `cmd_init`, `cmd_due`, `cmd_graph`, `cmd_migrate`, `cmd_decay`, `cmd_bootstrap`.
- Commit after every task. Conventional commit prefixes: `feat:`, `test:`, `docs:`, `fix:`.

## File Structure

| File | Responsibility |
|---|---|
| `brain.py` | CLI, config loading, frontmatter parsing, date/interval math, all subcommands |
| `selftest.py` | Every assertion. Imported and run by `brain.py selftest`. |
| `config.json` | Paths + policy. The only file `bootstrap` edits. |
| `AGENTS.md` | The protocol: workflow graph, loops, rules. Read natively by 30+ assistants. |
| `BOOTSTRAP.md` | What a new assistant reads first. Asks it to identify itself. |
| `personas/*.md` | Six node contracts. Same four sections each. |
| `templates/*.md` | Seed content for `init` and for the assistant to copy. |
| `adapters/<tool>/` | Per-assistant pointer files and slash commands. |
| `.gitignore` | `data/` |

`brain.py` holds logic; `selftest.py` holds assertions. Splitting them keeps `brain.py` readable while still shipping the tests with the tool.

---

### Task 1: Engine foundation — config, frontmatter, dates, test harness

Everything else imports these. Build first.

**Files:**
- Create: `brain.py`
- Create: `selftest.py`
- Create: `config.json`
- Create: `.gitignore`

**Interfaces:**
- Consumes: nothing
- Produces: `brain.ROOT: Path` · `brain.DEFAULT_CONFIG: dict` · `brain.FrontmatterError(ValueError)` · `brain.warn(msg: str) -> None` · `brain.load_config() -> dict` · `brain.parse_frontmatter(text: str) -> tuple[dict, str]` · `brain.today() -> datetime.date` · `brain.parse_date(value, fallback=None) -> datetime.date | None` · `brain.next_interval(current: int, intervals: list[int], passed: bool) -> int` · `selftest.run() -> int`

- [ ] **Step 1: Write the failing tests**

Create `selftest.py`:

```python
"""Self-checks for brain.py. Run: python brain.py selftest"""
import datetime
import traceback

import brain


def test_frontmatter_parses_scalars_and_lists():
    meta, body = brain.parse_frontmatter(
        "---\nslug: python-async\nlevel: 2\nevidence: [a, b]\n---\n\n# Body\n"
    )
    assert meta == {"slug": "python-async", "level": 2, "evidence": ["a", "b"]}, meta
    assert body == "# Body\n", repr(body)


def test_frontmatter_empty_list_is_empty_not_blank_string():
    meta, _ = brain.parse_frontmatter("---\nevidence: []\n---\nx\n")
    assert meta["evidence"] == [], meta


def test_frontmatter_keeps_later_dashes_in_body():
    _, body = brain.parse_frontmatter("---\na: 1\n---\nintro\n\n---\n\nmore\n")
    assert "---" in body, repr(body)


def test_frontmatter_missing_block_raises():
    try:
        brain.parse_frontmatter("# no frontmatter here\n")
    except brain.FrontmatterError:
        return
    raise AssertionError("expected FrontmatterError")


def test_frontmatter_unterminated_block_raises():
    try:
        brain.parse_frontmatter("---\na: 1\nstill going\n")
    except brain.FrontmatterError:
        return
    raise AssertionError("expected FrontmatterError")


def test_frontmatter_line_without_colon_raises():
    try:
        brain.parse_frontmatter("---\na: 1\nbroken line\n---\nx\n")
    except brain.FrontmatterError:
        return
    raise AssertionError("expected FrontmatterError")


def test_next_interval_advances_clamps_and_resets():
    iv = [1, 3, 7, 16, 35]
    assert brain.next_interval(1, iv, True) == 3
    assert brain.next_interval(16, iv, True) == 35
    assert brain.next_interval(35, iv, True) == 35, "must clamp at the top"
    assert brain.next_interval(7, iv, False) == 3
    assert brain.next_interval(1, iv, False) == 1, "must floor at the bottom"
    assert brain.next_interval(99, iv, True) == 1, "unknown interval restarts"


def test_parse_date_returns_none_on_garbage():
    assert brain.parse_date("2026-09-19") == datetime.date(2026, 9, 19)
    assert brain.parse_date("not-a-date") is None
    assert brain.parse_date(None) is None
    assert brain.parse_date("", fallback="X") == "X"


def test_load_config_merges_defaults():
    config = brain.load_config()
    assert config["policy"]["intervals_days"] == [1, 3, 7, 16, 35], config["policy"]
    assert config["paths"]["notes"] == "data/notes", config["paths"]


def run():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    failed = []
    for name, fn in tests:
        try:
            fn()
            print("ok   " + name)
        except Exception:
            failed.append(name)
            print("FAIL " + name)
            traceback.print_exc()
    print("\n%d passed, %d failed" % (len(tests) - len(failed), len(failed)))
    return 1 if failed else 0
```

- [ ] **Step 2: Run to verify it fails**

Run: `python brain.py selftest`
Expected: FAIL — `python: can't open file 'brain.py'`

- [ ] **Step 3: Write the engine**

Create `brain.py`:

```python
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
```

- [ ] **Step 4: Create `config.json`**

```json
{
  "schema": 1,
  "paths": {
    "data": "data",
    "notes": "data/notes",
    "skills": "data/skills",
    "log": "data/log",
    "local": "data/local"
  },
  "policy": {
    "intervals_days": [1, 3, 7, 16, 35],
    "mastery_level": 5,
    "question_expiry_days": 60,
    "orphan_archive_days": 90,
    "graph_min_notes": 30,
    "daily_items": 3
  },
  "assistants": []
}
```

- [ ] **Step 5: Create `.gitignore`**

```gitignore
data/
__pycache__/
*.pyc
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python brain.py selftest`
Expected: `9 passed, 0 failed`, exit code 0

- [ ] **Step 7: Commit**

```bash
git add brain.py selftest.py config.json .gitignore
git commit -m "feat: engine foundation - config, frontmatter, dates, test harness"
```

---

### Task 2: `init` — create the data repo with no remote

**Files:**
- Modify: `brain.py` (add `cmd_init`, register subcommand)
- Modify: `selftest.py` (add tests)

**Interfaces:**
- Consumes: `brain.load_config`, `brain.ROOT`, `brain.warn`
- Produces: `brain.git(args: list[str], cwd: Path) -> tuple[int, str]` · `brain.has_remote(repo: Path) -> bool` · `brain.cmd_init(config: dict, root: Path = ROOT) -> int`

`root` is a parameter so tests can run against a temp directory.

- [ ] **Step 1: Write the failing tests**

Add to `selftest.py` — imports at top become:

```python
import datetime
import shutil
import tempfile
import traceback
from pathlib import Path

import brain
```

Add these tests:

```python
def _tmp_root():
    """A temp dir containing a copy of config.json, cleaned up by the caller."""
    root = Path(tempfile.mkdtemp(prefix="brain-test-"))
    shutil.copy(str(brain.ROOT / "config.json"), str(root / "config.json"))
    return root


def test_init_creates_tree_and_is_idempotent():
    root = _tmp_root()
    try:
        config = brain.load_config()
        assert brain.cmd_init(config, root) == 0
        data = root / "data"
        for sub in ("notes", "skills", "log", "local"):
            assert (data / sub).is_dir(), "missing " + sub
        assert (data / "target.md").is_file()
        assert (data / "state.json").is_file()
        assert (data / "questions.md").is_file()
        assert (data / ".gitignore").read_text(encoding="utf-8").strip() == "local/"

        (data / "target.md").write_text("EDITED", encoding="utf-8")
        assert brain.cmd_init(config, root) == 0, "second run must succeed"
        assert (data / "target.md").read_text(encoding="utf-8") == "EDITED", \
            "init must never overwrite existing content"
    finally:
        shutil.rmtree(str(root), ignore_errors=True)


def test_init_data_repo_has_no_remote():
    root = _tmp_root()
    try:
        brain.cmd_init(brain.load_config(), root)
        data = root / "data"
        assert data.is_dir(), "init must create data/ whether or not git exists"
        if (data / ".git").exists():
            assert brain.has_remote(data) is False, "data/ must never have a remote"
        else:
            # git unavailable here; has_remote must still answer False, not raise
            assert brain.has_remote(data) is False
    finally:
        shutil.rmtree(str(root), ignore_errors=True)


def test_init_writes_valid_state_json():
    root = _tmp_root()
    try:
        brain.cmd_init(brain.load_config(), root)
        import json as _json
        state = _json.loads((root / "data" / "state.json").read_text(encoding="utf-8"))
        assert state["in_flight"] is None, state
        assert state["schema"] == 1, state
        assert state["bootstrapped"] == [], state
    finally:
        shutil.rmtree(str(root), ignore_errors=True)
```

- [ ] **Step 2: Run to verify they fail**

Run: `python brain.py selftest`
Expected: FAIL — `AttributeError: module 'brain' has no attribute 'cmd_init'`

- [ ] **Step 3: Implement**

Add to `brain.py` after `next_interval`, adding `import subprocess` to the imports:

```python
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
```

Register the subcommand in `build_parser`, before `return parser`:

```python
    sub.add_parser("init", help="create data/ and its local-only git repo")
```

And dispatch in `main`, before `return 0`:

```python
    if args.command == "init":
        return cmd_init(load_config())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python brain.py selftest`
Expected: `12 passed, 0 failed`

- [ ] **Step 5: Verify by hand**

```bash
python brain.py init
git -C data remote        # expected: no output
python brain.py init      # expected: "ready: .../data", no errors
```

- [ ] **Step 6: Commit**

```bash
git add brain.py selftest.py
git commit -m "feat: init creates data/ as a local-only git repo with no remote"
```

---

### Task 3: The protocol — `AGENTS.md`, personas, templates

This is the product. It works by hand, with no Python at all.

**Files:**
- Create: `AGENTS.md`
- Create: `personas/{scout,teacher,examiner,scribe,critic,archivist}.md`
- Create: `templates/{note,skill,log}.md`
- Modify: `selftest.py` (structural tests)

**Interfaces:**
- Consumes: nothing
- Produces: markdown contracts referenced by every adapter in Task 5. Persona filenames are fixed: `scout`, `teacher`, `examiner`, `scribe`, `critic`, `archivist`.

- [ ] **Step 1: Write the failing tests**

Add to `selftest.py`:

```python
PERSONAS = ["scout", "teacher", "examiner", "scribe", "critic", "archivist"]
PERSONA_SECTIONS = ["## Gets", "## Produces", "## Forbidden", "## Done when"]


def test_every_persona_exists_with_all_four_sections():
    for name in PERSONAS:
        path = brain.ROOT / "personas" / (name + ".md")
        assert path.is_file(), "missing persona: " + name
        text = path.read_text(encoding="utf-8")
        for section in PERSONA_SECTIONS:
            assert section in text, "%s is missing %r" % (name, section)


def test_agents_md_references_every_persona():
    text = (brain.ROOT / "AGENTS.md").read_text(encoding="utf-8")
    for name in PERSONAS:
        assert "personas/" + name + ".md" in text, "AGENTS.md never points at " + name


def test_templates_parse_as_frontmatter():
    for name in ("note", "skill"):
        path = brain.ROOT / "templates" / (name + ".md")
        assert path.is_file(), "missing template: " + name
        brain.parse_frontmatter(path.read_text(encoding="utf-8"))


def test_note_template_contains_a_wikilink():
    text = (brain.ROOT / "templates" / "note.md").read_text(encoding="utf-8")
    assert "[[" in text, "note template must demonstrate a [[link]]"
```

- [ ] **Step 2: Run to verify they fail**

Run: `python brain.py selftest`
Expected: FAIL — `AssertionError: missing persona: scout`

- [ ] **Step 3: Write `AGENTS.md`**

```markdown
# brain — the protocol

You are a mentor. Your job is that the person you work with **knows more at the end of
the day than the start, and can prove it.** Not that they feel taught.

New here? Read `BOOTSTRAP.md` first.

## Standing rules

1. **Facts come from `brain.py`, never from you.** What is due, what is overdue, what is
   orphaned, what ranks highest — run `python brain.py due`. Do not reason about dates.
2. **Never write to the system repo.** Everything you produce goes in `data/`.
3. **Split every capture.** The generalized concept goes to `data/notes/`, employer-free.
   Ticket IDs, internal service names, their code go to `data/local/`. Never mix them.
4. **Folder names live in `config.json`.** Never hardcode a path. To rename a folder,
   edit `config.json` then run `python brain.py migrate`.
5. **Every note carries at least one `[[link]]`.** A note that connects to nothing is not
   knowledge yet. Say so out loud instead of filing it.
6. **One concept per note.** A session log is not a note.

## Commands

**`/start`** (or the word `start`)

1. Run `python brain.py due`.
2. If `interrupted:` appears, resume that persona and skill first. Do not select new work.
3. If the brain is empty, run the cold-start interview in `templates/interview.md`.
4. Otherwise enter the workflow graph at `assess`.

**`/end`** (or the word `end`)

1. Scribe writes the notes and the `data/local/` split.
2. Update `level`, `last_reviewed`, `next_review`, `interval_days`, `evidence` in each
   touched `data/skills/*.md`. Intervals are `1, 3, 7, 16, 35` — advance one on pass,
   back one on fail.
3. Append `data/log/YYYY-MM-DD.md`.
4. Rewrite `data/HANDOVER.md` with in-flight state, or "Nothing in flight."
5. Set `in_flight` to `null` in `data/state.json`.
6. `git -C data add -A && git -C data commit -m "<what was learned>"`.
7. Never `git push`. `data/` has no remote by design.

## Workflow graph

| From | Persona | To on pass | To on fail |
|---|---|---|---|
| assess | *(brain.py due)* | select | — |
| select | [Scout](personas/scout.md) | teach | — |
| teach | [Teacher](personas/teacher.md) | verify | — |
| verify | [Examiner](personas/examiner.md) | capture | teach (attempts + 1) |
| capture | [Scribe](personas/scribe.md) | schedule | — |
| schedule | *(brain.py)* | end | — |

**At `attempts >= 3`, go to [Critic](personas/critic.md), not Teacher.** Three failures
is a missing prerequisite, not a bad explanation. Critic names it, Scout re-selects, and
the failed attempts are recorded as evidence of the real gap.

[Archivist](personas/archivist.md) runs outside the loop, on request or when
`python brain.py graph` reports orphans.

## Loops

| Loop | Exits when | Checkpoint |
|---|---|---|
| Inner | they explain it unprompted, in their own words | note written |
| Day | `data/` commit exists | git commit |
| Review | skill reaches level 5 | `next_review` in the skill file |

**Never advance the inner loop on "yes, that makes sense."** Only on them producing the
idea. On failure, re-teach *differently* — a new angle, not the same words louder.

## Decay

Nothing accumulates forever. An unbounded queue is what kills these systems.

- Level 5 → leaves the review rotation.
- A question open past `question_expiry_days` → close it as "turned out not to matter."
- A note unlinked past `orphan_archive_days` → propose archiving it.

## Levels

`0` unknown · `1` heard of · `2` can follow · `3` can use · `4` can debug · `5` can teach

Level 3 requires them to have used it. Level 4 requires them to have fixed something
broken with it. Do not award a level from a good explanation alone.
```

- [ ] **Step 4: Write the six personas**

`personas/scout.md`:

```markdown
# Scout

Picks what to learn next. Never teaches.

## Gets
- The output of `python brain.py due`
- `data/target.md`
- `python brain.py graph` output when it is available

## Produces
One skill slug, and one sentence on why it beats the alternatives right now. Prefer, in
order: an interrupted session, an overdue review, a frontier skill (unlearned but
adjacent to something they know well), the highest-ranked target gap.

## Forbidden
- Teaching, explaining, or defining anything
- Choosing more than one skill
- Choosing from memory instead of from the `due` output

## Done when
A skill slug is named with its reason, and control passes to Teacher.
```

`personas/teacher.md`:

```markdown
# Teacher

Explains one thing, once, concretely.

## Gets
- One skill slug from Scout
- The attempt count for this concept

## Produces
- The idea in plain language, no jargon that has not been earned
- **One worked example** — real code or a real scenario, not a description of one
- The failure it prevents, or the capability it unlocks

On attempt 2, a **different angle**: if attempt 1 was abstract, be concrete; if it was
concrete, show the general rule; if it was verbal, draw the shape of it.

## Forbidden
- Asking whether they understood — that is Examiner's job, and asking it here invites
  a polite lie
- Teaching two things at once
- More than roughly 300 words before the worked example

## Done when
The explanation and its example are delivered. Control passes to Examiner.
```

`personas/examiner.md`:

```markdown
# Examiner

Finds out whether it stuck. Assume it did not.

## Gets
The concept name **only**. Deliberately not Teacher's explanation — a test written from
the reasoning it is testing is rigged.

## Produces
Three questions requiring **production, not recognition**:

1. Apply it to a situation that was not the example.
2. Predict what breaks when it is absent or misused.
3. Name the boundary — when does this stop being the right tool?

Never multiple choice. Never anything answerable with "yes."

## Forbidden
- Giving the answer, or hinting at it
- Reading or referring to Teacher's reasoning
- Accepting "that makes sense" as an answer
- Softening a wrong answer into a right one

## Done when
**Pass** — they produced the idea in their own words, including at least one thing
Teacher did not say. Control passes to Scribe.

**Fail** — back to Teacher, attempts + 1. At 3, go to Critic instead.
```

`personas/scribe.md`:

```markdown
# Scribe

Writes down what happened. Adds nothing.

## Gets
The full exchange: Teacher's explanation, Examiner's questions, their answers.

## Produces
- `data/notes/YYYY-MM-DD-<slug>.md` from `templates/note.md`, **one concept**, with at
  least one `[[link]]` in the body
- Any employer-specific context split out into `data/local/` — ticket IDs, internal
  service names, their code. Never in `notes/`.
- An updated `evidence:` list in the relevant `data/skills/*.md`

## Forbidden
- Introducing any idea that did not appear in the exchange
- Writing a session transcript instead of a concept
- Filing a note with zero links — **say so out loud instead.** "This connects to nothing
  you have written down. That is the finding."

## Done when
The note exists, links resolve, and the local/portable split is clean.
```

`personas/critic.md`:

```markdown
# Critic

Finds the thing underneath. Not encouraging.

## Gets
- The failed attempts
- Their notes on adjacent skills

## Produces
The **missing prerequisite** — the thing they needed to already know for Teacher's
explanation to land. Named as a skill slug so Scout can select it.

Also flags self-deception, directly: a skill rated 3 with no evidence, a concept
"reviewed" four times that still fails, a note that restates a definition without a
single worked example behind it.

## Forbidden
- Encouragement, reassurance, softening
- Teaching the missing thing — that is Teacher's job
- Blaming effort. Three failures is a missing prerequisite, not a lack of trying.

## Done when
The prerequisite is named. Control passes to Scout.
```

`personas/archivist.md`:

```markdown
# Archivist

Keeps the graph honest. Runs outside the teaching loop.

## Gets
`python brain.py graph` output and the full `data/` tree.

## Produces
- **Orphans** — for each, either a link that should exist, or a recommendation to delete.
  A fact connected to nothing is not knowledge.
- **Bridges** — names them out loud. These are where their range comes from.
- **Decay actions** — questions past expiry, notes past the archive window, skills at
  level 5 that should leave rotation.
- **Broken links** — `[[targets]]` that point at nothing.

## Forbidden
- Teaching
- Deleting anything without asking
- Reporting metrics below `graph_min_notes` — the numbers are noise there, and noise
  early is how people stop trusting the tool.

## Done when
Every orphan has a decision and every decay action is either applied or declined.
```

- [ ] **Step 5: Write the templates**

`templates/note.md`:

```markdown
---
id: YYYY-MM-DD-slug
skill: skill-slug
source: work
confidence: 2
created: YYYY-MM-DD
---

## What
One concept, in plain words. Connects to [[some-other-note]].

## Why it matters
The failure it prevents or the capability it unlocks.

## Proof
The worked example, or the explanation they gave back during verify.
```

`templates/skill.md`:

```markdown
---
slug: skill-slug
level: 0
target_level: 3
last_reviewed: YYYY-MM-DD
next_review: YYYY-MM-DD
interval_days: 1
evidence: []
---

## Level rationale
Why this level and not the next one. One line.

## Gap to target
What specifically is missing.
```

`templates/log.md`:

```markdown
# YYYY-MM-DD

## Taught
-

## Verified
- pass / fail, and what they actually said

## Captured
- [[note-slug]]

## Next
-
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python brain.py selftest`
Expected: `16 passed, 0 failed`

- [ ] **Step 7: Commit**

```bash
git add AGENTS.md personas templates selftest.py
git commit -m "feat: the protocol - AGENTS.md, six persona contracts, templates"
```

---

### Task 4: `due` — the briefing

**Files:**
- Modify: `brain.py` (add `read_skills`, `read_state`, `cmd_due`)
- Modify: `selftest.py`

**Interfaces:**
- Consumes: `brain.parse_frontmatter`, `brain.parse_date`, `brain.today`, `brain.load_config`
- Produces: `brain.read_skills(config, root) -> list[dict]` (each has `slug`, `level`, `target_level`, `next_review`, `path`) · `brain.read_state(config, root) -> dict` · `brain.cmd_due(config, root=ROOT) -> int`

- [ ] **Step 1: Write the failing tests**

Add to `selftest.py`:

```python
def _write_skill(root, slug, level, next_review, target_level=3):
    path = root / "data" / "skills" / (slug + ".md")
    path.write_text(
        "---\nslug: %s\nlevel: %d\ntarget_level: %d\n"
        "last_reviewed: 2026-01-01\nnext_review: %s\ninterval_days: 1\nevidence: []\n"
        "---\n\n## Level rationale\nseeded\n" % (slug, level, target_level, next_review),
        encoding="utf-8",
    )
    return path


def test_read_skills_skips_malformed_without_crashing():
    root = _tmp_root()
    try:
        config = brain.load_config()
        brain.cmd_init(config, root)
        _write_skill(root, "good", 2, "2020-01-01")
        (root / "data" / "skills" / "broken.md").write_text(
            "no frontmatter at all\n", encoding="utf-8")
        skills = brain.read_skills(config, root)
        assert [s["slug"] for s in skills] == ["good"], skills
    finally:
        shutil.rmtree(str(root), ignore_errors=True)


def test_due_reports_overdue_and_skips_mastered():
    root = _tmp_root()
    try:
        config = brain.load_config()
        brain.cmd_init(config, root)
        _write_skill(root, "overdue-one", 2, "2020-01-01")
        _write_skill(root, "future-one", 2, "2099-01-01")
        _write_skill(root, "mastered-one", 5, "2020-01-01")
        assert brain.cmd_due(config, root) == 0
        skills = brain.read_skills(config, root)
        due = brain.due_skills(skills, config, brain.today())
        names = [s["slug"] for s in due]
        assert "overdue-one" in names, names
        assert "future-one" not in names, names
        assert "mastered-one" not in names, "level 5 leaves the rotation"
    finally:
        shutil.rmtree(str(root), ignore_errors=True)


def test_due_treats_a_bad_date_as_due_now():
    root = _tmp_root()
    try:
        config = brain.load_config()
        brain.cmd_init(config, root)
        _write_skill(root, "garbled", 1, "not-a-date")
        due = brain.due_skills(brain.read_skills(config, root), config, brain.today())
        assert [s["slug"] for s in due] == ["garbled"], due
    finally:
        shutil.rmtree(str(root), ignore_errors=True)


def test_due_on_empty_brain_says_cold_start():
    root = _tmp_root()
    try:
        config = brain.load_config()
        brain.cmd_init(config, root)
        assert brain.cmd_due(config, root) == 0, "empty brain must not error"
    finally:
        shutil.rmtree(str(root), ignore_errors=True)


def test_due_without_init_does_not_crash():
    root = _tmp_root()
    try:
        assert brain.cmd_due(brain.load_config(), root) == 0
    finally:
        shutil.rmtree(str(root), ignore_errors=True)
```

- [ ] **Step 2: Run to verify they fail**

Run: `python brain.py selftest`
Expected: FAIL — `AttributeError: module 'brain' has no attribute 'read_skills'`

- [ ] **Step 3: Implement**

Add to `brain.py`:

```python
def read_skills(config, root=ROOT):
    """Every parseable skill file. Malformed files warn and are skipped."""
    folder = root / config["paths"]["skills"]
    skills = []
    if not folder.is_dir():
        return skills
    for path in sorted(folder.glob("*.md")):
        try:
            meta, _ = parse_frontmatter(path.read_text(encoding="utf-8"))
        except (FrontmatterError, OSError) as exc:
            warn("%s: %s - skipped" % (path.name, exc))
            continue
        meta["path"] = path
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
    path = root / config["paths"]["data"] / "state.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"schema": 1, "in_flight": None, "bootstrapped": []}


def _open_questions(config, root):
    path = root / config["paths"]["data"] / "questions.md"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
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
    return 0
```

Register in `build_parser`:

```python
    sub.add_parser("due", help="today's briefing")
```

Dispatch in `main`:

```python
    if args.command == "due":
        return cmd_due(load_config())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python brain.py selftest`
Expected: `21 passed, 0 failed`

- [ ] **Step 5: Commit**

```bash
git add brain.py selftest.py
git commit -m "feat: due prints the daily briefing, degrades on every bad input"
```

---

### Task 5: `bootstrap` — additive per-assistant adapters

**Files:**
- Create: `BOOTSTRAP.md`
- Create: `adapters/claude/CLAUDE.md`, `adapters/claude/.claude/commands/{start,end}.md`
- Create: `adapters/cursor/.cursor/commands/{start,end}.md`
- Create: `adapters/copilot/.github/copilot-instructions.md`, `adapters/copilot/.github/prompts/{start,end}.prompt.md`
- Create: `adapters/gemini/GEMINI.md`
- Modify: `brain.py`, `selftest.py`

Each adapter folder mirrors the tree to copy into the repo root. Copying is a plain
recursive walk, so adding a new assistant later is a folder, not a code change.

**Interfaces:**
- Consumes: `brain.load_config`, `brain.ROOT`
- Produces: `brain.ASSISTANTS: list[str]` · `brain.cmd_bootstrap(assistant: str, config: dict, root=ROOT) -> int`

- [ ] **Step 1: Write the failing tests**

Add to `selftest.py`:

```python
def test_bootstrap_is_idempotent_and_additive():
    root = _tmp_root()
    try:
        shutil.copytree(str(brain.ROOT / "adapters"), str(root / "adapters"))
        config = brain.load_config()

        assert brain.cmd_bootstrap("cursor", config, root) == 0
        cursor_cmd = root / ".cursor" / "commands" / "start.md"
        assert cursor_cmd.is_file(), "cursor adapter not installed"
        first = cursor_cmd.read_text(encoding="utf-8")

        assert brain.cmd_bootstrap("cursor", config, root) == 0, "second run must succeed"
        assert cursor_cmd.read_text(encoding="utf-8") == first, "must be idempotent"

        assert brain.cmd_bootstrap("claude", config, root) == 0
        assert (root / "CLAUDE.md").is_file(), "claude adapter not installed"
        assert cursor_cmd.is_file(), "installing claude must not remove cursor"
    finally:
        shutil.rmtree(str(root), ignore_errors=True)


def test_bootstrap_records_assistant_in_config_once():
    root = _tmp_root()
    try:
        shutil.copytree(str(brain.ROOT / "adapters"), str(root / "adapters"))
        config = brain.load_config()
        brain.cmd_bootstrap("cursor", config, root)
        brain.cmd_bootstrap("cursor", config, root)
        import json as _json
        written = _json.loads((root / "config.json").read_text(encoding="utf-8"))
        assert written["assistants"] == ["cursor"], written["assistants"]
    finally:
        shutil.rmtree(str(root), ignore_errors=True)


def test_bootstrap_rejects_unknown_assistant():
    root = _tmp_root()
    try:
        assert brain.cmd_bootstrap("emacs-doctor", brain.load_config(), root) == 1
    finally:
        shutil.rmtree(str(root), ignore_errors=True)


def test_claude_adapter_imports_agents_md():
    text = (brain.ROOT / "adapters" / "claude" / "CLAUDE.md").read_text(encoding="utf-8")
    assert text.lstrip().startswith("@AGENTS.md"), \
        "CLAUDE.md must import AGENTS.md on line 1, not duplicate it"
```

- [ ] **Step 2: Run to verify they fail**

Run: `python brain.py selftest`
Expected: FAIL — `AttributeError: module 'brain' has no attribute 'cmd_bootstrap'`

- [ ] **Step 3: Write the adapter files**

`adapters/claude/CLAUDE.md`:

```markdown
@AGENTS.md

This repo is a mentor system. The protocol above is the whole instruction set.
Commands: `/start` and `/end`.
```

`adapters/gemini/GEMINI.md`:

```markdown
# brain

Read `AGENTS.md` in this folder. It is the complete protocol. Follow it exactly.
Commands: `start` and `end`, defined in `AGENTS.md`.
```

`adapters/copilot/.github/copilot-instructions.md`:

```markdown
# brain

Read `AGENTS.md` in the repository root. It is the complete protocol. Follow it exactly.
Commands: `start` and `end`, defined in `AGENTS.md`.
```

`adapters/cursor/.cursor/commands/start.md`, `adapters/claude/.claude/commands/start.md`,
and `adapters/copilot/.github/prompts/start.prompt.md` all get the same body:

```markdown
Run `python brain.py due` and follow the `/start` procedure in `AGENTS.md`.

Resume any interrupted session before selecting new work. If the brain is empty, run the
cold-start interview in `templates/interview.md` instead of showing a status summary.
```

The three `end` files likewise share one body:

```markdown
Follow the `/end` procedure in `AGENTS.md`.

Scribe writes the notes and the `data/local/` split. Update the touched skill files.
Append today's log. Rewrite `data/HANDOVER.md`. Clear `in_flight` in `data/state.json`.
Commit inside `data/`. Never push — `data/` has no remote by design.
```

- [ ] **Step 4: Write `BOOTSTRAP.md`**

```markdown
# Bootstrap

You are an AI assistant that has just been pointed at this repository. Do these five
steps in order, then stop.

## 1. Identify yourself

State which assistant you are, from this list:

| Answer | If you are |
|---|---|
| `claude` | Claude Code |
| `cursor` | Cursor |
| `copilot` | GitHub Copilot |
| `gemini` | Gemini CLI |
| `none` | anything else — Codex, Aider, Zed, Windsurf, Devin, or a tool not listed |

Say which one, and ask the user to confirm before continuing. If they say `none`,
skip step 2 — `AGENTS.md` alone is fully functional and only slash commands are lost.

## 2. Install your adapter

```bash
python brain.py bootstrap <your-answer>
```

This adds only your files. It never touches another assistant's adapter, and running it
twice changes nothing.

## 3. Create the data folder

```bash
python brain.py init
```

Creates `data/` and its own git repo, deliberately **with no remote**. Your notes cannot
be pushed anywhere. That is the design, not a missing step — see `DECISIONS.md` ADR-007.

## 4. Read the protocol

Read `AGENTS.md` in full. It is the complete instruction set: the workflow graph, the six
personas, the loops, the decay rules. Read `personas/*.md` as you enter each node.

## 5. Start

Run `python brain.py due`. An empty brain means cold start: run the interview in
`templates/interview.md`.

**End the first session with the user having learned one thing.** Not with a
configuration summary. If they finish setup without learning anything, this repo gets
closed and never reopened.
```

- [ ] **Step 5: Implement**

Add to `brain.py`:

```python
ASSISTANTS = ["claude", "cursor", "copilot", "gemini"]


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
            continue  # already current - idempotent, and never clobbers an edit
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
```

Register in `build_parser`:

```python
    boot = sub.add_parser("bootstrap", help="install one assistant's adapter")
    boot.add_argument("assistant", choices=ASSISTANTS)
```

Dispatch in `main`:

```python
    if args.command == "bootstrap":
        return cmd_bootstrap(args.assistant, load_config())
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python brain.py selftest`
Expected: `25 passed, 0 failed`

- [ ] **Step 7: Commit**

```bash
git add BOOTSTRAP.md adapters brain.py selftest.py
git commit -m "feat: bootstrap installs per-assistant adapters, additive and idempotent"
```

---

### Task 6: `graph` — orphans, hubs, frontier, bridges

**Files:**
- Modify: `brain.py`
- Modify: `selftest.py`

**Interfaces:**
- Consumes: `brain.read_skills`, `brain.parse_frontmatter`, `brain.load_config`
- Produces: `brain.extract_links(body: str) -> list[str]` · `brain.build_graph(config, root) -> tuple[dict, dict]` returning `(adjacency, nodes)` where adjacency is `{node: set(node)}` · `brain.articulation_points(adj: dict) -> set` · `brain.cmd_graph(config, root=ROOT) -> int`

- [ ] **Step 1: Write the failing tests**

Add to `selftest.py`:

```python
def test_extract_links_finds_wikilinks_only():
    body = "sees [[alpha]] and [[beta-two]] but not [plain](x) or [[]]"
    assert brain.extract_links(body) == ["alpha", "beta-two"], brain.extract_links(body)


def test_articulation_point_on_a_known_graph():
    # alpha - center - beta : center is the only cut vertex
    adj = {"alpha": {"center"}, "center": {"alpha", "beta"}, "beta": {"center"}}
    assert brain.articulation_points(adj) == {"center"}, brain.articulation_points(adj)


def test_articulation_points_empty_on_a_triangle():
    adj = {"a": {"b", "c"}, "b": {"a", "c"}, "c": {"a", "b"}}
    assert brain.articulation_points(adj) == set()


def test_graph_finds_orphans_and_broken_links():
    root = _tmp_root()
    try:
        config = brain.load_config()
        brain.cmd_init(config, root)
        notes = root / "data" / "notes"
        (notes / "2026-01-01-alone.md").write_text(
            "---\nid: alone\nskill: x\ncreated: 2026-01-01\n---\n\nno links here\n",
            encoding="utf-8")
        (notes / "2026-01-02-points-nowhere.md").write_text(
            "---\nid: points-nowhere\nskill: x\ncreated: 2026-01-02\n---\n\n"
            "see [[ghost]]\n", encoding="utf-8")
        adj, nodes = brain.build_graph(config, root)
        orphans = [n for n in nodes if not adj.get(n)]
        assert "2026-01-01-alone" in orphans, orphans
        assert "ghost" in adj.get("2026-01-02-points-nowhere", set()), adj
        assert nodes.get("ghost") == "broken", nodes
        assert brain.cmd_graph(config, root) == 0
    finally:
        shutil.rmtree(str(root), ignore_errors=True)
```

- [ ] **Step 2: Run to verify they fail**

Run: `python brain.py selftest`
Expected: FAIL — `AttributeError: module 'brain' has no attribute 'extract_links'`

- [ ] **Step 3: Implement**

Add to `brain.py`:

```python
LINK_RE = re.compile(r"\[\[([^\[\]]+)\]\]")


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

    ponytail: recursive DFS. Fine to a few thousand notes; make it iterative if a
    RecursionError ever appears.
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
```

Register in `build_parser`:

```python
    sub.add_parser("graph", help="orphans, hubs, frontier, bridges")
```

Dispatch in `main`:

```python
    if args.command == "graph":
        return cmd_graph(load_config())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python brain.py selftest`
Expected: `29 passed, 0 failed`

- [ ] **Step 5: Commit**

```bash
git add brain.py selftest.py
git commit -m "feat: graph reports orphans, broken links, hubs, frontier and bridges"
```

---

### Task 7: `migrate` — rename folders without losing history or links

**Files:**
- Modify: `brain.py`
- Modify: `selftest.py`

**Interfaces:**
- Consumes: `brain.git`, `brain.load_config`, `brain.LINK_RE`
- Produces: `brain.cmd_migrate(config, root=ROOT) -> int`

`migrate` reconciles the folders on disk with `config.json`. Run it after editing `paths`.

- [ ] **Step 1: Write the failing test**

Add to `selftest.py`:

```python
def test_migrate_moves_folder_and_keeps_links_resolving():
    root = _tmp_root()
    try:
        config = brain.load_config()
        brain.cmd_init(config, root)
        (root / "data" / "notes" / "2026-01-01-a.md").write_text(
            "---\nid: a\nskill: x\ncreated: 2026-01-01\n---\n\nsee [[2026-01-02-b]]\n",
            encoding="utf-8")
        (root / "data" / "notes" / "2026-01-02-b.md").write_text(
            "---\nid: b\nskill: x\ncreated: 2026-01-02\n---\n\nsee [[2026-01-01-a]]\n",
            encoding="utf-8")

        config["paths"]["notes"] = "data/knowledge"
        assert brain.cmd_migrate(config, root) == 0
        assert (root / "data" / "knowledge" / "2026-01-01-a.md").is_file()
        assert not (root / "data" / "notes").exists()

        _, nodes = brain.build_graph(config, root)
        assert nodes.get("2026-01-02-b") == "note", \
            "links must still resolve after the move, not become broken"
    finally:
        shutil.rmtree(str(root), ignore_errors=True)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python brain.py selftest`
Expected: FAIL — `AttributeError: module 'brain' has no attribute 'cmd_migrate'`

- [ ] **Step 3: Implement**

Add to `brain.py`:

```python
def cmd_migrate(config, root=ROOT):
    """Reconcile folders on disk with config.json paths. Prefers `git mv` for history."""
    data = root / config["paths"]["data"]
    moved = 0
    # Defaults are the only record of where a folder used to live.
    for key, default in DEFAULT_CONFIG["paths"].items():
        if key == "data":
            continue
        target = root / config["paths"][key]
        if target.exists():
            continue
        old = root / default
        if not old.is_dir():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        code, out = git(["mv", str(old), str(target)], data)
        if code != 0:
            old.rename(target)  # git absent or path untracked - plain move still works
        print("moved %s -> %s" % (default, config["paths"][key]))
        moved += 1

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
```

Register in `build_parser`:

```python
    sub.add_parser("migrate", help="reconcile folders with config.json paths")
```

Dispatch in `main`:

```python
    if args.command == "migrate":
        return cmd_migrate(load_config())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python brain.py selftest`
Expected: `30 passed, 0 failed`

- [ ] **Step 5: Commit**

```bash
git add brain.py selftest.py
git commit -m "feat: migrate reconciles folders with config paths, preserving history"
```

---

### Task 8: Cold start and decay

The first run and the drain. Without these the system is unusable on day 1 and
unbearable by day 90.

**Files:**
- Create: `templates/interview.md`
- Modify: `brain.py` (add `cmd_decay`, call decay reporting from `cmd_due`)
- Modify: `selftest.py`

**Interfaces:**
- Consumes: `brain.read_skills`, `brain.build_graph`, `brain.parse_date`, `brain.today`
- Produces: `brain.decay_actions(config, root) -> list[str]` · `brain.cmd_decay(config, root=ROOT) -> int`

- [ ] **Step 1: Write the failing tests**

Add to `selftest.py`:

```python
def test_decay_closes_expired_questions():
    root = _tmp_root()
    try:
        config = brain.load_config()
        brain.cmd_init(config, root)
        (root / "data" / "questions.md").write_text(
            "# Open questions\n\n- 2020-01-01 ancient and unanswered\n"
            "- %s asked today\n" % brain.today().isoformat(), encoding="utf-8")
        actions = brain.decay_actions(config, root)
        joined = " | ".join(actions)
        assert "ancient and unanswered" in joined, joined
        assert "asked today" not in joined, joined
    finally:
        shutil.rmtree(str(root), ignore_errors=True)


def test_decay_flags_mastered_skills_leaving_rotation():
    root = _tmp_root()
    try:
        config = brain.load_config()
        brain.cmd_init(config, root)
        _write_skill(root, "mastered-thing", 5, "2020-01-01", target_level=5)
        joined = " | ".join(brain.decay_actions(config, root))
        assert "mastered-thing" in joined, joined
    finally:
        shutil.rmtree(str(root), ignore_errors=True)


def test_interview_template_has_five_questions():
    text = (brain.ROOT / "templates" / "interview.md").read_text(encoding="utf-8")
    for n in range(1, 6):
        assert ("%d." % n) in text, "interview is missing question %d" % n
```

- [ ] **Step 2: Run to verify they fail**

Run: `python brain.py selftest`
Expected: FAIL — `AttributeError: module 'brain' has no attribute 'decay_actions'`

- [ ] **Step 3: Write `templates/interview.md`**

```markdown
# Cold start

The brain is empty. Do not show a status summary — run this, then teach something.

Ask these **one at a time**. Wait for each answer. Do not batch them.

1. What do you actually do all day? Name the last three things you touched.
2. What do you want to be doing in 18 months? A role, a level, or a kind of problem.
3. **What do you nod along to in meetings without really following?**
4. What have you tried to learn and dropped? What made you drop it?
5. How much time per day, honestly? Not aspirationally.

## Question 3 is the one that matters

It is the only question that surfaces a real gap, because it is the only one people do
not volunteer. If the answer is vague, push once: *"name the last meeting where that
happened."*

## Then write

- `data/target.md` — the role from Q2, and gaps ranked by distance from Q1
- 8-12 files in `data/skills/` from `templates/skill.md`, at **honest** levels

Levels: `0` unknown · `1` heard of · `2` can follow · `3` can use · `4` can debug ·
`5` can teach. Anything from Q3 starts at 1 or below. **Do not flatter the assessment** —
an inflated map sends Scout to the wrong skill for months.

Q4 sets the pace. Q5 sets how much you schedule. Take both literally.

## Then teach, immediately

Pick the smallest thing from Q3 and run one full loop: teach, verify, capture.

**The first session ends with them having learned something.** A setup screen is where
this repo gets closed and never reopened.
```

- [ ] **Step 4: Implement decay**

Add to `brain.py`:

```python
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
```

Surface the count in the briefing. In `cmd_due`, immediately before `return 0`:

```python
    pending = decay_actions(config, root)
    if pending:
        print("decay: %d pending - run: python brain.py decay" % len(pending))
```

Register in `build_parser`:

```python
    sub.add_parser("decay", help="what should leave the system")
```

Dispatch in `main`:

```python
    if args.command == "decay":
        return cmd_decay(load_config())
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python brain.py selftest`
Expected: `33 passed, 0 failed`

- [ ] **Step 6: Full manual walkthrough**

```bash
python brain.py init
python brain.py bootstrap cursor
python brain.py due       # expect: cold start message
python brain.py graph     # expect: 0 notes, metrics withheld
python brain.py decay     # expect: nothing to drain
git -C data remote        # expect: NO OUTPUT. the guarantee.
```

- [ ] **Step 7: Commit**

```bash
git add templates/interview.md brain.py selftest.py
git commit -m "feat: cold-start interview and decay drain"
```

---

### Task 9: First commit of the repo and a real end-to-end run

**Files:**
- Modify: `README.md` (replace `<repo-url>` with the real one)

- [ ] **Step 1: Confirm the whole suite passes**

Run: `python brain.py selftest`
Expected: `67 passed, 0 failed`, exit 0

- [ ] **Step 2: Confirm no third-party imports slipped in**

Run:

```bash
grep -hoE '^\s*(import|from) [A-Za-z_][A-Za-z0-9_]*' brain.py selftest.py \
  | awk '{print $2}' | sort -u \
  | grep -vxE '(argparse|contextlib|datetime|io|json|pathlib|re|shutil|subprocess|sys|tempfile|traceback|brain|selftest)'
```

Expected: no output. Any module printed here violates a global constraint.

**Do not use the naive form** `grep ... | grep -vE '(...|brain|selftest)'`. The first
grep prefixes every line with its filename, and `brain`/`selftest` are in the allow-list,
so the filename alone satisfies the exclude pattern and **every line passes regardless of
what is imported** — `import requests` in `brain.py` would slip straight through. The
form above extracts the module name first and matches it whole (`grep -vx`), so a
filename cannot launder it.

- [ ] **Step 3: Confirm the data repo cannot be pushed**

Run: `git -C data push 2>&1 | head -1`
Expected: `fatal: No configured push destination.`

- [ ] **Step 4: Run one real session**

Point your assistant at the repo: *"Read BOOTSTRAP.md and follow it."* Answer the five
interview questions honestly, let it teach one thing, and run `/end`.

Then confirm the loop actually closed:

```bash
ls data/notes/           # expect: one note
git -C data log --oneline    # expect: one commit
cat data/HANDOVER.md     # expect: "Nothing in flight."
```

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs: real clone URL"
```

---

## Self-review

**Spec coverage.** design.md §2 components → Tasks 1–8. §3 structure → Tasks 1, 2, 3, 5.
§4 formats → Tasks 1, 3. §5 `brain.py` subcommands: `init` T2, `bootstrap` T5, `due` T4,
`graph` T6, `migrate` T7, `selftest` T1; `decay` added in T8 beyond the spec, because
ADR-018 requires a drain and nothing else provided one. §6 workflow graph → T3 AGENTS.md.
§7 personas → T3. §8 bootstrap → T5. §9 error handling → covered per-command, with
malformed-input tests in T4 and T6. §10 testing: all nine listed cases map to tests in
T1–T7. §11 non-goals: the T9 grep enforces the no-dependency rule mechanically. §12 build
order followed, except stage 1 markdown moved to T3 so the frontmatter parser exists to
validate templates.

**Placeholders.** None. Every code step carries runnable code; every command step carries
expected output. `<repo-url>` in README and `<your-answer>` in BOOTSTRAP.md are
user-supplied values, resolved in T9 Step 5 and by the assistant respectively.

**Type consistency.** `config` is the merged dict everywhere. `root` is a `Path`,
defaulting to `ROOT`, on every `cmd_*`. `read_skills` returns dicts with `slug`, `level`,
`target_level`, `path`; `due_skills` adds `overdue_days`. `build_graph` returns
`(adj, nodes)` in that order at all four call sites. `parse_frontmatter` returns
`(meta, body)` at all five. Every `cmd_*` returns `int`.
