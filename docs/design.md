# brain — design

**Date:** 2026-09-19 · **Status:** approved, pre-implementation

Architecture reference for whoever implements or modifies this. Rationale lives in
[DECISIONS.md](../DECISIONS.md); this document covers *what is built*, not *why*.

---

## 1. Constraints

These are fixed. Every design choice below follows from them.

| # | Constraint | Source |
|---|---|---|
| C1 | No LLM API reachable from user code | corporate network |
| C2 | No package installs | corporate policy |
| C3 | No personal git login on the work machine | corporate policy |
| C4 | Work-derived data must not leave the device | legal |
| C5 | Assistant is unknown at build time | it's a distributable system |
| C6 | Cross-platform: Windows, macOS, Linux | corporate fleets are mixed |

C1 forbids any orchestration framework. C2 forbids all dependencies. C3 forces a public
system repo. C4 forces local-only data. C5 forces the adapter layer. C6 forces
`pathlib` and no shell assumptions.

## 2. Components

```
                      ┌────────────────────────────────────┐
   assistant  ───────▶│ AGENTS.md         the protocol     │
   (any tool)         │ personas/*.md     node contracts   │
                      └───────────────┬────────────────────┘
                                      │ reads
                                      ▼
                      ┌────────────────────────────────────┐
                      │ brain.py        deterministic core │
                      │   reads config.json                │
                      └───────────────┬────────────────────┘
                                      │ reads/writes
                                      ▼
                      ┌────────────────────────────────────┐
                      │ data/    notes skills log state    │
                      │          own git repo, no remote   │
                      └────────────────────────────────────┘
```

Division of labour, and it is strict:

- **`brain.py` decides facts.** What is due. What is orphaned. What ranks highest. Dates,
  counts, graph metrics. Never prose.
- **The assistant decides language.** Explanations, questions, judgment, note wording.
  Never dates or scheduling.

Anything an LLM would get subtly wrong and silently — date arithmetic, "did I already
review this", set operations over 200 files — belongs in Python.

## 3. Repository structure

```
brain/                          public system repo
  README.md  BOOTSTRAP.md  AGENTS.md  DECISIONS.md
  brain.py
  config.json
  personas/{scout,teacher,examiner,scribe,critic,archivist}.md
  checks/{REGISTRY,tests,cost,operations}.md
  templates/{note,skill,log,interview}.md
  adapters/
    claude/{CLAUDE.md,commands/{start,end}.md}
    cursor/commands/{start,end}.md
    copilot/{copilot-instructions.md,prompts/{start,end}.prompt.md}
    gemini/{GEMINI.md,commands/{start,end}.toml}
  docs/design.md  docs/prior-art.md  docs/how-this-was-built.md
  .gitignore                    -> data/

  data/                         created by `brain.py init`; own .git, no remote
    target.md  state.json  HANDOVER.md  questions.md  misses.md
    notes/  skills/  log/  checks/
    local/                      gitignored inside data/ as well
    .gitignore                  -> local/
```

`target.md`, `HANDOVER.md`, `questions.md`, and `misses.md` are not templates —
`cmd_init` writes their starting content from the `STARTER` dict in `brain.py` directly.
Only `note.md`, `skill.md`, `log.md`, and `interview.md` live in `templates/`.

`checks/` in the system repo holds the three shipped checks and is read-only to the
assistant. `data/checks/` holds checks promoted from the user's own miss log and is
written by the assistant (ADR-032). The registry reads both.

## 4. File formats

All markdown with YAML-ish frontmatter, parsed by a ~20-line hand-rolled reader —
flat `key: value` and `key: [a, b]` only. No YAML dependency (C2).

### 4.1 Note — `data/notes/YYYY-MM-DD-slug.md`

```markdown
---
id: 2026-09-19-async-task-starvation
skill: python-async
source: work
confidence: 3
created: 2026-09-19
---

## What
One concept. Not a log of the session. Connects to [[event-loop]] and [[blocking-io]].

## Why it matters
The failure it prevents or the capability it unlocks.

## Proof
Worked example, snippet, or the explanation given back during verify.
```

**Links live in the body as `[[wikilinks]]`, nowhere else.** No `links:` key in
frontmatter — one source, nothing to desync. `source` is one of `work | study |
question`.

**A note with zero `[[links]]` is invalid** (ADR-015). Rejected at write time by Scribe,
flagged at read time by `brain.py graph`.

### 4.2 Skill — `data/skills/<slug>.md`

```markdown
---
slug: python-async
level: 2            # 0 unknown · 1 heard of · 2 can follow · 3 can use
                    # 4 can debug · 5 can teach  → leaves rotation
target_level: 4
last_reviewed: 2026-09-19
next_review: 2026-09-26
interval_days: 7
evidence: [2026-09-19-async-task-starvation]
---

## Level rationale
Why this level and not the next one. One line.

## Gap to target
What specifically is missing.
```

**Interval schedule:** `1, 3, 7, 16, 35 days`. Pass advances one step; fail resets to
the previous step (floor `1`). Fixed table, not a computed algorithm — SM-2 is
unjustifiable complexity at this scale.

### 4.3 `state.json` — the checkpoint

```json
{
  "schema": 1,
  "last_start": "2026-09-19",
  "last_end": "2026-09-19",
  "in_flight": {
    "persona": "teacher",
    "skill": "python-async",
    "attempts": 1,
    "opened": "2026-09-19T14:02:00"
  }
}
```

`in_flight` is `null` when clean. A non-null value on `/start` means the previous
session was interrupted — resume it before selecting anything new (ADR-017). There is no
`bootstrapped` field — which assistants are installed lives in `config.json.assistants`,
written by `cmd_bootstrap`, not in `state.json`.

### 4.4 `config.json` — the only file bootstrap edits

```json
{
  "schema": 1,
  "paths": {
    "data": "data", "notes": "data/notes", "skills": "data/skills",
    "log": "data/log", "local": "data/local"
  },
  "policy": {
    "intervals_days": [1, 3, 7, 16, 35],
    "mastery_level": 5,
    "question_expiry_days": 60,
    "orphan_archive_days": 90,
    "graph_min_notes": 30,
    "daily_items": 3
  },
  "assistants": ["cursor"]
}
```

Renaming a folder = edit `paths`, run `brain.py migrate` (ADR-005) — except `paths.data`
and `paths.local`, which are pinned to `"data"` and `"data/local"`. A different value
there warns and falls back to the default (ADR-026).

## 5. `brain.py`

Standard library only. `pathlib` (`Path`, `PurePosixPath`, `PureWindowsPath`), `json`,
`datetime`, `re`, `argparse`, `subprocess` (git). No third-party imports, ever.
`selftest.py` additionally uses `shutil`, `tempfile`, `contextlib`, `io`, `ast`, and
`traceback` for fixtures — `brain.py` itself does not import any of them.

| Subcommand | Does |
|---|---|
| `init` | Create `data/` tree from templates. `git init` inside it. **Verify no remote is set.** Idempotent. |
| `bootstrap <assistant>` | Copy `adapters/<assistant>/` into place. Append to `config.json.assistants`. **Never deletes.** Idempotent. |
| `due` | Print the briefing: overdue reviews, top gap, oldest open question, interrupted session. |
| `graph` | Orphans, hubs, frontier, bridges. Below `graph_min_notes`, prints note count only. |
| `migrate` | Move folders per changed `paths`, `git mv` to preserve history, then **verify** `[[links]]` still resolve (it does not rewrite them — link targets are file stems, so a folder move never changes them). |
| `decay` | List what should leave the system: mastered skills, expired questions, orphan-archive candidates, expired misses. Never deletes. |
| `misses` | Count `data/misses.md` by check slug as `missed / fired`; name promotion candidates (live miss count ≥ `promotion_threshold`) and expired entries. Read-only. |
| `schedule <slug> pass\|fail` | Compute the next `interval_days` from the fixed table, set `last_reviewed`/`next_review`, write it back. The only command that writes a skill file. |
| `selftest` | Assertions against temp fixtures. Exit non-zero on failure. |

### 5.1 `due` output

Machine-written, assistant-read. Stable format so the assistant can rely on it:

```
BRIEFING 2026-09-19
interrupted: teacher/python-async (1 attempts, opened 2026-09-19T14:02:00)
due: python-async(L2, 3d overdue), sql-indexes(L1, due today)
gap: distributed-tracing (L0, target L3)
question: 2026-09-07 why does our retry storm only happen on deploy?
promote: rollback - missed >= 5 times, teach it before adding a check
decay: 2 pending - run: python brain.py decay
```

`orphans` is not a `due` field — it belongs to `python brain.py graph`, which `AGENTS.md`
has `/start` run alongside `due` so the frontier actually reaches Scout. `due` only ever
reports the decay *count*; the items themselves come from `python brain.py decay`.

### 5.2 Graph metrics

Notes and skills are nodes; `[[links]]` are undirected edges.

| Metric | Computation |
|---|---|
| **Orphans** | degree 0 |
| **Hubs** | top 10% by degree |
| **Frontier** | skills at `level 0-1` adjacent to a hub, ranked by `(hub adjacency × target-role weight)` |
| **Bridges** | articulation points with degree ≥ 2 — nodes whose removal disconnects the graph |

Bridges use a plain articulation-point walk (Hopcroft–Tarjan). Correct, ~30 lines,
stdlib. A graph of a few thousand nodes needs nothing more.

## 6. The workflow graph

Declared as data in `config.json`-adjacent form and mirrored as a table in `AGENTS.md`
so the assistant reads the same thing the code does.

```
      ┌──────────────── resume if state.in_flight ──────────────┐
      │                                                          ▼
/start ──▶ assess ──▶ select ──▶ teach ──▶ verify ──┬─pass─▶ capture ──▶ schedule ──▶ /end
          (brain.py   (Scout)   (Teacher)  (Examiner)│        (Scribe)   (brain.py)
           due)                                      │
                                                     └─fail──▶ teach (attempt+1, different angle)
```

`attempts ≥ 3` routes to Critic instead of Teacher: the problem is a missing
prerequisite, not a bad explanation. Critic finds it, Scout re-selects, and the failed
attempt is recorded as evidence of the real gap.

## 7. Personas

One file each in `personas/`. Every file has the same four sections: **Gets**,
**Produces**, **Forbidden**, **Done when**.

| Persona | Gets | Produces | Forbidden |
|---|---|---|---|
| Scout | `due` output, `target.md`, skill graph | one skill + reason | teaching |
| Teacher | one skill, attempt count | explanation + worked example | asking questions |
| Examiner | the concept name only | 3 production-not-recognition questions | giving answers, seeing Teacher's reasoning |
| Scribe | the exchange | note with non-empty `links`, `local/` split | adding new content |
| Critic | notes, failed attempts | the missing prerequisite | encouragement |
| Archivist | whole graph | orphan/decay/archive actions | teaching |

All six run sequentially in one conversation on every assistant that ships here, so the
isolation — including Examiner not seeing Teacher's reasoning — is **instructed, not
enforced** (ADR-024, amending ADR-013). Running each in its own subagent context would
enforce it; nothing in this repo does that yet.

### 7.1 The work gate

A second graph, entered from `checks/REGISTRY.md` rather than `AGENTS.md`, running
during real work in the user's own repos (ADR-029).

```
request -> trigger? -no-> answer ungated
              |
             yes (writes code, changes design, costs > ~30 min)
              v
          restate -> run each check in checks/ and data/checks/ (<=1 question each)
              -> filter to questions that change the build (ask <=3)
              -> append one line per check run to data/misses.md (miss, or `| ok`)
              -> proceed
```

| Check | Slug | Asks |
|---|---|---|
| Tests | `tests` | the one check that fails if this breaks; unnamed inputs |
| Cost | `cost` | the smaller version; what happens if it is not done |
| Operations | `operations` | who finds out on failure; blast radius; dependencies |

Same four sections as a persona: **Gets**, **Produces**, **Forbidden**, **Done when**.
Fixed rather than synthesized per problem, because a persona generated from the problem
statement inherits the framing that contains the blind spot (ADR-030). The set grows
only by promotion.

**Miss line format**, matched by `MISS_RE` in `brain.py`:

```
- YYYY-MM-DD check-slug | what was not specified
- YYYY-MM-DD check-slug | ok
```

Slug is lowercase `[a-z0-9][a-z0-9-]*`. Non-matching lines are prose and are skipped
silently — the file has a header and the user may annotate it.

A text field of exactly `ok` (case-insensitive) is a **firing with no finding**, not a
miss. `miss_summary` returns it in the fourth element (`fired`, live counts by check)
and excludes it from `live`, from `promotions`, and from `expired` — an `ok` has nothing
to drain through decay. Promotion still counts raw misses; the denominator is recorded
because it cannot be reconstructed later (ADR-035).

**Promotion.** Live count ≥ `policy.promotion_threshold` (5) makes a slug a candidate:
the assistant writes `data/checks/<slug>.md` and it joins every subsequent gate.
`cmd_due` surfaces candidates at `/start` so Scout can also teach the underlying gap —
the single point where the work gate feeds the learning loop. Entries older than
`policy.miss_expiry_days` (90) are excluded from the count and drain via `decay`
(ADR-033).

## 8. Bootstrap

1. User: *"Read BOOTSTRAP.md and follow it."*
2. `BOOTSTRAP.md` asks the assistant to state which tool it is, and to confirm.
3. Assistant runs `python brain.py bootstrap <assistant>`.
4. Script copies that adapter, updates `config.json`, prints next step.
5. Assistant prints the absolute path of the clone and the one-line pointer the user
   pastes into their assistant's **global** settings, so the work gate also runs in the
   repos they work in. Machine-specific, never committed, optional.
6. Assistant runs `python brain.py due` → empty brain → cold-start interview (ADR-020).

Unknown assistant → `AGENTS.md` alone, `start`/`end` typed as words. Fully functional;
only slash commands are lost.

## 9. Error handling

Hostile-input assumption: files are hand-edited by humans and written by LLMs. Both
produce malformed output.

| Failure | Behavior |
|---|---|
| Malformed frontmatter | Warn to stderr with path, skip file, continue. Never abort. |
| Missing `data/` | `due`/`graph` print *"run `python brain.py init`"*, exit 0 |
| `config.json` unparseable | Fall back to built-in defaults, warn loudly |
| Broken `[[link]]` target | Report in `graph` as broken, not as orphan |
| Git absent or failing | Every git call is best-effort; the system works without git |
| `data/` has a remote | `init` **warns prominently** — ADR-007's guarantee is void. `due` does not check on every briefing: `README.md` tells users they may deliberately add their own private remote on a personal machine, and a warning on every session would punish that legitimate choice. A one-time check at `init` is the honest place for it. |
| Bad date in frontmatter | Treat as "due now", warn. Never crash the briefing. |

**Nothing in `brain.py` may raise an unhandled exception during `/start`.** A briefing
that fails is a system that gets abandoned.

## 10. Testing

`python brain.py selftest` — assertions against fixtures built in a temp directory, torn
down after. No pytest, no fixtures directory, no framework (C2).

67 tests as of this writing (`python brain.py selftest` is the source of truth for the
current count, not this document). Covers, at minimum:

1. Interval progression and reset on fail
2. Overdue detection across month and year boundaries
3. Frontmatter parsing: valid, malformed, missing, empty
4. Graph metrics against a hand-computed fixture graph with a known articulation point
5. Orphan detection, and broken-link vs orphan distinction
6. `bootstrap` idempotence — run twice, byte-identical tree
7. `bootstrap` additivity — install a second adapter, first survives untouched
8. `migrate` verifies `[[links]]` still resolve after a folder move (it does not rewrite
   them) and refuses a target that collides with an in-progress migration
9. `init` idempotence, and that it never configures a remote
10. `schedule` writes `interval_days`, `last_reviewed`, `next_review` and preserves the
    rest of the file's frontmatter and body
11. Config shape-checking — a wrong-typed `paths`/`policy` value falls back to its
    default with a warning instead of reaching a caller
12. `paths.data` and `paths.local` are pinned to their defaults; `notes`, `skills`, and
    `log` stay renameable and path-containment-checked
13. Path traversal and absolute-path rejection under both POSIX and Windows path flavors
14. A non-string `slug` in a skill file falls back to the filename
15. A corrupt `state.json` warns and falls back to the default rather than crashing `due`
16. The no-third-party-import gate itself (ADR-025)

Exit non-zero on any failure. Run after every `brain.py` edit.

## 11. Non-goals

Not built, and not by oversight: LangChain / LangGraph (ADR-019), any pip dependency,
a database, embeddings or vector search, a web UI, a bundled local model, cloud sync,
multi-user support, and retrieval/RAG (deferred, ADR-021).

## 12. Build order

Each stage is independently useful — a partial build is still worth having.

| Stage | Delivers | Useful alone? |
|---|---|---|
| 1 | `AGENTS.md`, `personas/`, `templates/`, `config.json` | Yes — works by hand, no Python |
| 2 | `brain.py init`, `due`, `selftest` | Yes — real briefings |
| 3 | `BOOTSTRAP.md`, `bootstrap`, `adapters/` | Yes — slash commands |
| 4 | `graph`, `migrate` | Yes — frontier and orphans |
| 5 | Cold-start interview, decay rules | Complete |

Stage 1 is the product. Everything after it is leverage on top.
