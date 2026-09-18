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
  templates/{note,skill,log,handover,target}.md
  adapters/
    claude/{CLAUDE.md,commands/{start,end}.md}
    cursor/commands/{start,end}.md
    copilot/{copilot-instructions.md,prompts/{start,end}.prompt.md}
    gemini/{GEMINI.md,commands/{start,end}.toml}
  docs/design.md
  .gitignore                    -> data/

  data/                         created by `brain.py init`; own .git, no remote
    target.md  state.json  HANDOVER.md  questions.md
    notes/  skills/  log/
    local/                      gitignored inside data/ as well
    .gitignore                  -> local/
```

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
  },
  "bootstrapped": ["cursor", "claude"]
}
```

`in_flight` is `null` when clean. A non-null value on `/start` means the previous
session was interrupted — resume it before selecting anything new (ADR-017).

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

Renaming a folder = edit `paths`, run `brain.py migrate` (ADR-005).

## 5. `brain.py`

Standard library only. `pathlib`, `json`, `datetime`, `re`, `argparse`, `subprocess`
(git), `shutil`. No third-party imports, ever.

| Subcommand | Does |
|---|---|
| `init` | Create `data/` tree from templates. `git init` inside it. **Verify no remote is set.** Idempotent. |
| `bootstrap <assistant>` | Copy `adapters/<assistant>/` into place. Append to `config.json.assistants`. **Never deletes.** Idempotent. |
| `due` | Print the briefing: overdue reviews, top gap, oldest open question, interrupted session. |
| `graph` | Orphans, hubs, frontier, bridges. Below `graph_min_notes`, prints note count only. |
| `migrate` | Move folders per changed `paths`, rewrite `[[links]]`, `git mv` to preserve history. |
| `selftest` | Assertions against temp fixtures. Exit non-zero on failure. |

### 5.1 `due` output

Machine-written, assistant-read. Stable format so the assistant can rely on it:

```
BRIEFING 2026-09-19
interrupted: teacher/python-async (1 attempt, opened 14:02 yesterday)
due: python-async(L2, 3d overdue), sql-indexes(L1, due today)
gap: distributed-tracing (L0, target L3, blocks 2 target-role items)
question: "why does our retry storm only happen on deploy?" (open 12d)
orphans: 2
```

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

On assistants with real subagents, each runs in an isolated context. Elsewhere,
sequentially in one thread with the isolation instructed (ADR-013).

## 8. Bootstrap

1. User: *"Read BOOTSTRAP.md and follow it."*
2. `BOOTSTRAP.md` asks the assistant to state which tool it is, and to confirm.
3. Assistant runs `python brain.py bootstrap <assistant>`.
4. Script copies that adapter, updates `config.json`, prints next step.
5. Assistant runs `python brain.py due` → empty brain → cold-start interview (ADR-020).

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
| `data/` has a remote | `init` and `due` both **warn prominently** — ADR-007's guarantee is void |
| Bad date in frontmatter | Treat as "due now", warn. Never crash the briefing. |

**Nothing in `brain.py` may raise an unhandled exception during `/start`.** A briefing
that fails is a system that gets abandoned.

## 10. Testing

`python brain.py selftest` — assertions against fixtures built in a temp directory, torn
down after. No pytest, no fixtures directory, no framework (C2).

Covers:

1. Interval progression and reset on fail
2. Overdue detection across month and year boundaries
3. Frontmatter parsing: valid, malformed, missing, empty
4. Graph metrics against a hand-computed fixture graph with a known articulation point
5. Orphan detection, and broken-link vs orphan distinction
6. `bootstrap` idempotence — run twice, byte-identical tree
7. `bootstrap` additivity — install a second adapter, first survives untouched
8. `migrate` rewrites `[[links]]` and leaves no dangling references
9. `init` idempotence, and that it never configures a remote

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
