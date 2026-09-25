# Build prompt: `brain` — a repo-resident mentor driven by any AI assistant

Paste everything below the line into the LLM on the office laptop.

---

Build a project called `brain` from scratch. Read this whole spec first, then build it in the phase order at the end. Ask me nothing until you hit a real ambiguity.

## What it is

A mentor that lives in a git repo and is driven by whatever AI coding assistant I already have (Claude Code, Cursor, Copilot, Codex, Gemini CLI, Aider, Zed, Windsurf). It interviews me, finds what I don't know, teaches me, tests whether it stuck, writes it down, and resurfaces it before I forget.

It also sits beside me while I work and asks the questions I forgot to ask, then turns the ones I keep forgetting into lessons.

Hard constraints, non-negotiable (this runs on a locked-down corporate laptop):

- **Python 3.9+, standard library only.** No pip install, ever. No dependency, not even a "tiny" one.
- **No API key, no network call after clone, no account, no model download.**
- **The project has no LLM of its own.** It never calls a model. The intelligence is the assistant reading markdown instructions; the Python is a pure fact-computer. Do not add an LLM client, and do not add LangChain/LangGraph — a `pip install` under a corporate proxy is the thing being avoided, and there is no reachable model to call anyway.
- **Cross-platform** (Linux/macOS/Windows). Use `pathlib`, forward-slash config paths, no shell-isms.

## Core design ideas — keep these, they are the project

1. **Two surfaces, one bridge file.**
   - *Learning surface* (`AGENTS.md`), runs at `/start` and `/end`, cycle measured in weeks: teaches what I don't know.
   - *Work surface* (`checks/REGISTRY.md`), runs during real work in other repos, cycle measured in minutes: catches what I know but forgot to ask.
   - They meet at `data/misses.md`. The fast surface catches the miss; the slow surface removes the reason for it.

2. **Two git repos on purpose.**
   ```
   brain/           the system. public, pullable. the assistant NEVER writes here.
     data/          my brain. gitignored by the outer repo. its own git repo. NO REMOTE.
   ```
   No remote in `data/` means `git push` fails with "no configured push destination" — the safety is structural, not a policy anyone must remember. Tell the user plainly: **if the machine is reimaged, the brain is gone**; that is the accepted trade for not moving work-derived material off a corporate device. On a personal machine they can opt in with `cd data && git remote add origin <private-repo>`.

3. **The employer split.** Every capture splits in two: the generalized, employer-free *concept* goes to `data/notes/`; ticket IDs, internal service names, their code go to `data/local/`, which is gitignored again inside `data/`. `data/log/`, `data/HANDOVER.md` and `data/misses.md` must stay just as employer-free as notes.

4. **Facts come from Python, never from the assistant.** What is due, overdue, orphaned, highest-ranked — always from `brain.py`. The assistant must never reason about dates. Conversely **`brain.py` never writes notes**: it computes and reports, the assistant writes. `decay` lists what should leave; it deletes nothing.

5. **Verify before advance.** Being taught and being able to produce are different states. The inner loop does not advance on "yes, that makes sense" — only on me explaining it unprompted in my own words. On failure, re-teach *differently*: a new angle, not the same words louder.

6. **Every loop checkpoints to disk** so any loop can be abandoned mid-way and resumed, because its state is a file and not a conversation.

7. **Nothing accumulates forever.** An unbounded queue is what kills second-brain systems, so the system drains itself (see Decay).

8. **The knowledge graph is the honest answer to "what next".** Notes link with `[[wikilinks]]`; a note with zero links is rejected — if nothing connects, that is the finding, not a filing problem.

## Repo layout to produce

```
brain/
  README.md            the pitch, quick start, how it works, troubleshooting
  BOOTSTRAP.md         the six steps a fresh assistant reads first
  AGENTS.md            THE protocol — read natively by 30+ assistants
  DECISIONS.md         every decision as an ADR, including what was rejected
  brain.py             the engine, stdlib only
  selftest.py          the test suite, stdlib only, asserts
  config.json          paths + policy. the only tracked file bootstrap edits
  .gitignore           contains the literal line `data/`
  personas/            scout, teacher, examiner, scribe, critic, archivist
  checks/              REGISTRY.md, tests.md, cost.md, operations.md
  templates/           note.md, skill.md, log.md, interview.md
  adapters/claude/     CLAUDE.md (one line: @AGENTS.md) + .claude/commands/{start,end}.md
  adapters/cursor/     .cursor/commands/{start,end}.md
  adapters/copilot/    .github/copilot-instructions.md + .github/prompts/
  adapters/gemini/     GEMINI.md
  docs/design.md       full architecture
  docs/prior-art.md    what else exists, what was borrowed, what was rejected

  data/                created by `brain.py init`, never committed upstream
    target.md  state.json  HANDOVER.md  questions.md  misses.md
    notes/  skills/  log/  checks/  local/
```

`AGENTS.md` is the single source of truth. Every per-assistant file is a one-line pointer to it, so there is nothing to keep in sync.

## config.json (exact shape)

```json
{
  "schema": 1,
  "paths": {
    "data": "data", "notes": "data/notes", "skills": "data/skills",
    "log": "data/log", "local": "data/local", "checks": "data/checks"
  },
  "policy": {
    "intervals_days": [1, 3, 7, 16, 35],
    "mastery_level": 5,
    "question_expiry_days": 60,
    "orphan_archive_days": 90,
    "graph_min_notes": 30,
    "daily_items": 3,
    "miss_expiry_days": 90,
    "promotion_threshold": 5
  },
  "assistants": []
}
```

Path rules, enforced in code with a warning + fallback to default (never a crash):
- `data` and `local` are **pinned** and cannot be renamed — the outer `.gitignore` matches the literal `data/` and `data/.gitignore` matches the literal `local/`; renaming either would silently drop a gitignore layer and risk pushing notes into the public repo.
- `notes`, `skills`, `log`, `checks` are renameable; then `python brain.py migrate` moves them with `git mv` so history survives, and verifies `[[links]]` still resolve (they do — link targets are file stems, so a folder move leaves them valid).
- Paths must be relative, forward-slash, and inside the data root. Anything else: warn, fall back.

## brain.py — CLI surface

```
python brain.py init                       create data/, its git repo (no remote), starter files
python brain.py bootstrap <name>           install one assistant's adapter (additive, idempotent)
python brain.py due                        today's briefing
python brain.py graph                      orphans, broken links, hubs, frontier, bridges
python brain.py decay                      what should leave the system
python brain.py misses                     per check: missed / times it ran, what to promote
python brain.py schedule <slug> pass|fail  record a review outcome, reschedule the skill
python brain.py migrate                    move folders to match config.json, verify links
python brain.py selftest                   run the suite
```

`<name>` ∈ `claude|cursor|copilot|gemini`. **No auto-detection** — the assistant states which it is and passes the name. Invoking with no name exits 2 (argparse `choices`).

Implementation notes that matter:

- **`due` must never raise.** A failed briefing kills the habit. Missing/garbled dates mean *due now*, never silently never-due.
- Frontmatter: hand-rolled `---`-delimited `key: value` parser (no PyYAML). Coerce ints and `[]` lists. A malformed file warns and is skipped, never crashes the command.
- `schedule`: on pass advance one step in `intervals_days`, on fail step back one, clamped both ends; unknown current interval resets to the first. It writes `interval_days`, `last_reviewed`, `next_review` — the assistant never computes those by hand.
- `due` output lines: `BRIEFING <date>`, optional `interrupted: <persona>/<skill> (<n> attempts, opened <ts>)`, `due: slug(L2, 3d overdue), …` capped at `daily_items`, `gap: <slug> (L1, target L3)` picked by largest `level - target_level` deficit, `question: <oldest open>`, optional `promote: …`, optional `decay: N pending`. Empty brain prints `cold start: no skills yet - run the interview in templates/interview.md`.
- `graph`: build an undirected adjacency from skill slugs + note stems + every `[[link]]` target. A link target with no file is a **broken** node. Drop self-links. A note stem colliding with a skill slug warns and keeps the skill classification. Always print counts, broken links and orphans; print hubs/frontier/bridges only at ≥ `graph_min_notes` notes (below that print `metrics: need 30 notes …` — by design, not a bug; Scout falls back to its next preference).
  - hubs = top 10% by degree; frontier = skills at level ≤ 1 adjacent to a hub, ranked by degree; bridges = Hopcroft–Tarjan articulation points with degree ≥ 2.
  - The recursive DFS is fine to ~900 chained notes; leave a comment naming that ceiling and the iterative upgrade path.
- `misses`: parse `- YYYY-MM-DD check-slug | text` lines from `data/misses.md`. `text == "ok"` (case-insensitive) is a **pass**, not a miss. Drop anything older than `miss_expiry_days`. Print one row per check that ever fired: `<slug>  <missed> / <times it ran>` — a `0 / 9` row is the most useful row in the table, so iterate firings, not misses. A slug missed ≥ `promotion_threshold` times while unexpired is a promotion candidate. Promotion counts **raw misses today, not the rate**; the `ok` lines are recorded anyway because a denominator cannot be reconstructed after the fact.
- `init` is idempotent and never overwrites content. Writes `data/.gitignore` containing `local/`. `git init` failure warns ("history disabled, everything else works") and continues. If `data/` already has a remote, warn loudly that the no-push guarantee is void and print the removal command.
- `bootstrap` copies `adapters/<name>/**` into the clone, byte-comparing to skip unchanged files, appends the name to `config.json.assistants`, and prints "Other adapters untouched." Running it twice changes nothing. Installing Cursor must never touch the Claude adapter.
- No `install.lock.json`: bootstrap only writes inside the clone, so git already records what it added and `git clean` removes it.

## AGENTS.md — the protocol the assistant obeys

Standing rules: (1) facts from `brain.py`, never from you; (2) never write to the system repo, everything goes in `data/`; (3) split every capture concept/context; (4) folder names come from `config.json`, never hardcode — except literal `data`, which is pinned; (5) every note carries ≥1 `[[link]]`; (6) one concept per note, a session log is not a note.

`/start` (or the bare word `start`): run `due`, `graph`, `misses`; set `last_start`; **if `interrupted:` appears, resume that persona and skill first and select no new work**; empty brain → run the cold-start interview; otherwise enter the graph at `assess` and hand Scout the graph output; if `promote:` appeared, hand those slugs to Scout too and say they came from the work gate — something missed five times in real work outranks a frontier skill, it is a gap with evidence attached.

`/end` (or `end`): Scribe writes notes + the `data/local/` split → per touched skill update `level` and `evidence` then run `brain.py schedule <slug> pass|fail` → append `data/log/YYYY-MM-DD.md` → rewrite `data/HANDOVER.md` with in-flight state or "Nothing in flight." → set `in_flight` to null and `last_end` → `git -C data add -A && git -C data commit -m "<what was learned>"` → **never `git push`**.

Workflow graph, declared as a table (so porting it to a real graph engine later is transcription, not redesign):

| From | Persona | On pass | On fail |
|---|---|---|---|
| assess | *(brain.py due)* | select | — |
| select | Scout | teach | — |
| teach | Teacher | verify | — |
| verify | Examiner | capture | teach (attempts + 1) |
| capture | Scribe | schedule | — |
| schedule | *(brain.py)* | end | — |

Before Teacher begins (first attempt or resume), write `in_flight` to `data/state.json`: `{"persona":"teacher","skill":"<slug>","attempts":N,"opened":"<ISO ts>"}`. Re-teaches update `attempts` in place; `opened` does not change. `/end` clears it.

**At `attempts >= 3` go to Critic, not Teacher** — three failures is a missing prerequisite, not a bad explanation. Critic names the prerequisite as a skill slug and creates `data/skills/<slug>.md` from the template at an honest level if absent, because Scout only selects from files that exist there.

Levels: `0` unknown · `1` heard of · `2` can follow · `3` can use · `4` can debug · `5` can teach. Level 3 requires having used it; level 4 requires having fixed something broken with it. **Never award a level from a good explanation alone.**

Decay: level 5 leaves the review rotation; a question open past `question_expiry_days` closes as "turned out not to matter"; a note unlinked past `orphan_archive_days` is proposed for archiving; a miss older than `miss_expiry_days` drops, and only unexpired misses count toward promotion.

## Personas — contracts, not voices

A persona is useful only if it has a different *contract*. "Now be skeptical" is theater; "you may read only these five notes and must output three falsifiable questions" is a function. One file each, with Gets / Must produce / Forbidden from:

| Persona | Gets | Must produce | Forbidden from |
|---|---|---|---|
| Scout | `target.md` + skill graph | one skill to attack, with the reason | teaching |
| Teacher | that skill | explanation + worked example | asking questions |
| Examiner | the concept only — **not** Teacher's reasoning | 3 questions requiring production, not recognition | giving answers |
| Scribe | the exchange | a note with `[[links]]` | adding new content |
| Critic | my notes | where I am fooling myself | being encouraging |
| Archivist | the whole graph | orphans, bridges, decay actions | teaching, deleting without asking |

The **forbidden** column is what makes them real; Examiner not seeing Teacher's reasoning is what makes the test fair. Be honest in the README that today the personas run sequentially in one context, so this isolation is *instructed, not enforced* — an instruction to ignore what you just read is weaker than never having read it. Subagent isolation is deferred, not shipped.

## The work gate (checks/REGISTRY.md)

Trigger rule is load-bearing. A lookup, an explanation, a read, a one-line fix → answer it, **no gate**. Anything that writes non-trivial code, changes a design, picks a dependency, or commits more than ~30 minutes → run the gate. When genuinely unclear, run it: a wrong "no gate" costs a day, a wrong "gate" costs one extra question. (A gate that fires on "what does this function do" gets switched off in three days and then catches nothing.)

Steps: **restate** the request in one sentence including every assumption filled in silently (the miss lives in the silent assumptions) → **run every check** in `checks/` and `data/checks/`, at most one question each → **filter** to questions whose answer changes what gets built, ask at most 3; if more than three survive, the scope is too big to start — say so and propose a smaller first slice → **log one line per check that ran** to `data/misses.md`, employer-free:
```
- 2026-09-20 tests | no failing case named
- 2026-09-20 cost | ok
```
→ **proceed**.

Three fixed checks ship: `tests` (how do we know it works, and how do we find out when it breaks), `cost` (is this worth it, what is the smaller version), `operations` (what happens at 3am when it fails). **They are fixed on purpose and run whether or not the prompt hints at them** — a persona synthesized from my problem statement inherits the framing the blind spot lives in, so it reproduces the miss instead of catching it. Do not add per-problem persona generation.

Promotion: a slug missed ≥ `promotion_threshold` times while unexpired earns `data/checks/<slug>.md`, which then runs on every gate. Promoted checks live under `data/`, never in the system repo. `brain.py due` surfaces candidates at `/start` — that is the one point where the work surface feeds the learning surface.

## BOOTSTRAP.md — six steps, then stop

1. Identify yourself: `claude` | `cursor` | `copilot` | `gemini` | `none`, and ask me to confirm. `none` skips step 2; `AGENTS.md` alone is fully functional and only slash commands are lost.
2. `python brain.py bootstrap <answer>`.
3. `python brain.py init`.
4. Read `AGENTS.md` in full; read each `personas/*.md` as you enter that node.
5. Offer the work-gate pointer: print this clone's absolute path and the exact line to paste into the assistant's **global** user instructions (`~/.claude/CLAUDE.md`, Cursor Settings → Rules → User Rules, Copilot user `settings.json`, etc.):
   `Before any build or design task, read <abs-path>/checks/REGISTRY.md and follow it.`
   Machine-specific, so never committed. Say it is optional and that skipping it costs only the work gate.
6. `python brain.py due`. Empty brain → run `templates/interview.md`.

**End the first session with me having learned one thing, not with a configuration summary.** If setup finishes and I learned nothing, this repo gets closed and never reopened.

## Cold start — the interview (5 questions)

1. What do you actually do all day?
2. What do you want to be doing in 18 months?
3. What do you nod along to in meetings without really following?
4. What have you tried to learn and dropped? Why?
5. How much time per day, honestly?

From those, write `data/target.md` (target role + ranked gaps) and seed 8–12 skill files at honest levels, then teach one thing immediately. Budget 20–30 min. Flag question 3 as the one that decides whether the system is worth running — an inflated skill map sends it after the wrong things for months.

## Templates

- `note.md` — frontmatter `id, skill, source, confidence, created`; sections **What** (one concept, plain words, with a `[[link]]`), **Why it matters** (the failure it prevents), **Proof** (the worked example or what I said back at verify).
- `skill.md` — frontmatter `slug, level, target_level, last_reviewed, next_review, interval_days, evidence: []`; sections **Level rationale** (why this level and not the next, one line), **Gap to target**.
- `log.md` — `# YYYY-MM-DD` with **Taught / Verified** (pass|fail and what I actually said) **/ Captured** (`[[note-slug]]`) **/ Next**.
- `interview.md` — the five questions and what to write from them.

## selftest.py

Stdlib `assert`s, run via `python brain.py selftest`, exit non-zero on failure. Cover at minimum: date math and interval advance/step-back/clamping; frontmatter parse + malformed-file skip; graph metrics (orphans, broken links, hubs, frontier, bridges, self-link drop, note/skill collision); miss parsing with `ok` lines, expiry, and promotion threshold; `due` never raising on an empty/garbled brain; `init` and `bootstrap` idempotence; path validation rejecting absolute paths, `..`, backslashes, and renames of pinned `data`/`local`. Use temp dirs, never touch a real `data/`.

## DECISIONS.md

One ADR per decision — context, decision, **and the rejected alternatives with why**, because the rejected options are the useful part. At minimum cover: markdown-as-protocol over code; two repos; `data/` with no remote; `AGENTS.md` as the single source of truth; fixed checks over synthesized personas; stdlib-only / no LangChain; logging gate passes as the denominator; promotion by raw count for now; pinned `data`/`local` paths; no auto-detection of assistant.

## Deliberately deferred — do NOT build these

State them in the README as designed-not-built, each with the *observable condition* that triggers building it. **The rule: nothing here gets built until two weeks of real sessions have run.**

- Rate-based promotion (Wilson bound on missed/fired) — build when `misses` visibly misranks 5/5 below 6/180.
- Auto-closing a promoted check after a month of clean `ok`s.
- Retire-with-a-reason into `data/retired/` instead of dropping.
- Blocking verify (assistant refuses to advance until I pass).
- A single Scout priority score: `(1 - confidence) × (days_since_practice + 1) × weight`.
- Personas synthesized per problem.
- Persona isolation in real subagents.
- `brain.py week`, a staleness line, capturing the answer at verify, `export --safe`.

## Build order

1. `config.json` + `brain.py` skeleton: config loading with path validation, frontmatter, dates, `init`, `selftest` wiring. Commit.
2. `due`, `graph`, `schedule`, `decay` + their tests. Commit.
3. `AGENTS.md`, `personas/`, `templates/`. Commit.
4. `checks/` (registry + three checks), `misses`, promotion, and the `due` promote line. Commit.
5. `adapters/` + `bootstrap` + `BOOTSTRAP.md`. Commit.
6. `migrate`, `README.md`, `DECISIONS.md`, `docs/`. Commit.

After every phase run `python brain.py selftest` and paste the output. Do not tell me a phase is done without it. Conventional commits, one logical change each.

## Tone for the docs you write

Plain, specific, no marketing. Every claim must be one the code actually honors — if the code does not do it, the doc says so out loud rather than implying otherwise. Tables and small diagrams over paragraphs. Include a Troubleshooting section covering: `/start` does nothing (type `start`), the assistant ignoring the rules (wrong adapter, or the workspace root is a parent folder), "no data yet" (`init`), reviews never coming due (check `next_review`, then `selftest`), `git push` failing in `data/` (working as designed), the work gate never firing (the global pointer line is missing), and `promote:` never appearing (`0 / 9` rows mean it is running and finding nothing — the good outcome; `misses: none logged` means it is not running at all).
