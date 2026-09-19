# Decisions

Every design decision, why it was made, and what was rejected. The rejected options are
the useful part — they're the arguments you'd otherwise have again in six months.

**Adding one:** append at the end, next number, never renumber. Superseding an old
decision means marking it `Superseded by ADR-NNN` and writing a new one. Nothing is
deleted — a decision that turned out wrong is worth more than a missing one.

**Status values:** `Accepted` · `Rejected` · `Deferred` · `Superseded by ADR-NNN`

---

## ADR-001 — Drive the user's existing assistant instead of shipping an LLM

**Date:** 2026-09-19 · **Status:** Accepted

The system ships no model and makes no API call. It is a set of markdown instructions
that whatever assistant the user already has will read and act on.

**Why.** The target environment is a corporate laptop with no reachable AI API. But
those laptops usually *do* have an approved assistant — Cursor, Copilot — already
installed and already cleared by IT. The model is present; only the direction is
missing. Supplying direction needs no install, no key, no approval.

**Rejected:** bundling a local model (Ollama / llama-cpp). Needs a 1–4GB download, is
slow on corporate CPUs, and puts an LLM binary on a managed machine — a fight not worth
picking for a personal learning tool.

---

## ADR-002 — `AGENTS.md` is the single source of truth

**Date:** 2026-09-19 · **Status:** Accepted

One protocol file. Every other assistant-facing file is a one-line pointer to it.

**Why.** `AGENTS.md` was formalized in August 2025 (OpenAI, Google, Cursor, Factory) and
donated to the Linux Foundation's Agentic AI Foundation in December 2025. **30+ agents
read it natively** — Codex, Copilot, Cursor, Gemini CLI, Jules, Aider, Zed, Windsurf,
Devin. Writing it once covers nearly the whole field.

Claude Code is the notable exception: it reads `CLAUDE.md`. Solved with an `@AGENTS.md`
import on line 1, not with a second copy of the protocol.

**Rejected:** maintaining a full instruction file per assistant. Guaranteed drift — one
copy gets edited, the others rot, and the bug only shows up on the machine you're not
sitting at.

---

## ADR-003 — Adapters are additive, never destructive

**Date:** 2026-09-19 · **Status:** Accepted

Bootstrap installs the adapter for the detected assistant and touches no other. Running
it twice changes nothing. Nothing is ever renamed or deleted.

**Why.** People switch assistants and switch back. Cursor in March, Claude in June,
Cursor again in September. Every adapter that survives is one that doesn't have to be
rebuilt. They cost a few hundred bytes each and they don't conflict — tool config files
coexist by design.

**Rejected:** regenerating the structure per assistant. Throws away work, breaks the
other machine, and makes switching back a rebuild instead of a no-op.

---

## ADR-004 — A bootstrap document asks the assistant to identify itself

**Date:** 2026-09-19 · **Status:** Accepted

`README.md` and `AGENTS.md` both open by pointing at `BOOTSTRAP.md`. That file asks the
assistant which tool it is, confirms, then runs `python brain.py bootstrap`.

**Why.** Reliable auto-detection from the filesystem alone isn't possible — the
assistant knows what it is and nothing else does. Asking is one question, once.

**Note.** The document *asks*; the script *acts*. Deterministic file generation stays in
Python so it produces identical output regardless of which model answered.

---

## ADR-005 — Core folder names are invariant by default, configurable by design

**Date:** 2026-09-19 · **Status:** Accepted (softened from original)

`notes/ skills/ log/` keep their names. Paths are declared in `config.json`, so renaming
is one edit plus `python brain.py migrate`.

**Why.** Renaming breaks `git log --follow`, and the history *is* the growth record. It
also orphans notes when a user switches assistants on the same machine.

**Originally argued on stronger grounds and corrected.** The first version of this
decision claimed folder renaming would cause permanent merge conflicts between a work
machine and a home machine. The user pointed out they will never push from the work
laptop, so those two machines never sync. The argument was wrong and was dropped. What
remains — history and orphaning — is real but smaller, so this is a strong default with
a cheap escape hatch rather than a rule.

**Recorded for the assistant** as a standing instruction in `AGENTS.md`, so it's read
every session rather than living only here.

---

## ADR-006 — Config over codegen: assistants configure `brain.py`, they don't rewrite it

**Date:** 2026-09-19 · **Status:** Accepted

`brain.py` reads `config.json`. Bootstrap writes `config.json`. The engine is not
regenerated per assistant.

**Why.** Letting each assistant rewrite the engine means Cursor's version diverges from
Claude's, `selftest` silently stops testing the real thing, and the one deterministic
component in the system becomes the least predictable.

**User override, accepted:** editing `brain.py` is not forbidden — each person owns their
copy and may adapt it. The requirement is `python brain.py selftest` afterwards. Switching
assistants mid-stream is handled by the handover capsule (ADR-016).

---

## ADR-007 — Two nested repositories: public system, local-only data

**Date:** 2026-09-19 · **Status:** Accepted

`brain/` is the public system repo. `brain/data/` is gitignored by it and is its own git
repo **with no remote configured**.

**Why.** One structure solves two problems:

- The outer repo contains no data, so `git pull` for system updates never conflicts.
- The inner repo has no remote, so `git push` fails with *"no configured push
  destination."*

The second is the important one. On a work laptop the downside of an accidental push is
a fireable offense, and the only protection worth relying on is one that makes the
operation impossible rather than discouraged.

**Rejected:** a `pre-push` git hook. Hooks can be bypassed, aren't installed by clone,
and depend on being remembered. No remote requires nothing of the user.

---

## ADR-008 — The system repository must be public

**Date:** 2026-09-19 · **Status:** Accepted

Derived, not chosen. Corporate laptops typically block personal GitHub login, so the
only available operation is an anonymous HTTPS clone — which requires a public repo.

**Consequence, binding:** no personal data may ever enter the system repo. Not a resume,
not a CV, not a target role, not a real skill assessment. Every personal artifact lives
in `data/`. This is why `target.md` is generated at cold start rather than shipped.

---

## ADR-009 — Brain data never leaves the machine; every clone starts cold

**Date:** 2026-09-19 · **Status:** Accepted

**Why.** Notes derived from an employer's code cannot legally leave their device. Rather
than partially mitigate that, the design accepts it: each machine's brain is
self-contained and dies with the machine.

**Consequence.** Cold start is not an edge case, it's the normal first run — which is
why it's designed as a lesson rather than a setup screen (ADR-020).

**Reframe worth recording.** The system was initially designed as *one person's* brain
that syncs between their machines. The user corrected this: it is a **distributable
system** anyone can clone, where the data is always local. That correction removed the
sync problem entirely rather than solving it.

---

## ADR-010 — Two-tier capture: concepts are portable, context is not

**Date:** 2026-09-19 · **Status:** Accepted

Every `/end` splits what it captured. The generalized concept goes to `data/notes/`
(employer-free). Specifics — ticket IDs, internal service names, their code — go to
`data/local/`, gitignored even inside the data repo.

**Why.** *"Async task starvation when a sync call blocks the loop"* is knowledge you
learned and it's yours. The ticket number and the service name are theirs. The split is
at the source, so the boundary is maintained by the act of writing rather than by
remembering to clean up later.

---

## ADR-011 — Teaching is reactive first, gap-driven second

**Date:** 2026-09-19 · **Status:** Accepted

Real work is the default material. The skill map decides quiet days and flags what the
job never exposes you to.

**Why.** Reactive material is free, real, and already in front of you. Gap-driven
coverage catches what reactive alone can't — you only learn what your tickets happen to
touch.

**Rejected:** a fixed curriculum. Dies in week three when work gets busy, and the
abandonment poisons the whole system.

---

## ADR-012 — Two commands: `/start` and `/end`

**Date:** 2026-09-19 · **Status:** Accepted

Mentor behavior is always on. Two bookends structure the day.

**Why.** The write-back is the whole system — an agent that teaches without recording
leaves nothing behind. `/end` is an explicit checkpoint, which is far more reliable than
trusting an agent to volunteer a file write mid-conversation.

**Rejected:** fully ad-hoc with no commands (agents skip unprompted writes and the brain
silently stops growing); a six-command set (`/teach /quiz /gap /log …` — in practice
people use two).

---

## ADR-013 — Personas are graph nodes with enforced contracts

**Date:** 2026-09-19 · **Status:** Accepted

Scout, Teacher, Examiner, Scribe, Critic, Archivist. Each has a defined input, a
required output, and — critically — a **forbidden** list.

**Why.** A persona with only a different voice is theater. A persona with a different
contract is a function. *"Be skeptical"* does nothing; *"read only these five notes,
output three falsifiable questions, give no answers"* does.

The sharpest case: **Examiner must not see Teacher's reasoning**, or the test is rigged.

**Execution differs by assistant, contracts don't.** With real subagents (Claude Code)
each persona gets its own context and isolation is enforced. Elsewhere they run
sequentially in one thread and isolation is instructed. Honest degradation — same
definitions either way.

---

## ADR-014 — Two graphs, sequenced

**Date:** 2026-09-19 · **Status:** Accepted

**Workflow graph** — session states as data (a table), personas as nodes, conditional
edges. Built first; it's what runs. Editing teaching policy means editing a table, not
rewriting a prompt.

**Knowledge graph** — notes linked with `[[wikilinks]]`, yielding orphans, hubs,
frontier, bridges. Metrics switch on at ~30 notes, below which they're noise.

**Why frontier matters most.** Unlearned skills adjacent to existing hubs are the
cheapest next lesson with the highest attach rate. That's a better answer to *"what
next?"* than either a syllabus or a hunch.

**Why bridges matter.** Notes joining two clusters are the closest measurable proxy for
what makes senior engineers seem to absorb things faster — connected knowledge, so new
problems land next to something known.

---

## ADR-015 — `[[links]]` are mandatory from note #1

**Date:** 2026-09-19 · **Status:** Accepted

A note with zero links is invalid. Enforced twice: Scribe's contract rejects it at write
time, and `brain.py graph` flags it at every `/start`.

**Why.** Metrics can be computed at any point in the future. Links cannot be
retrofitted, because nobody goes back and re-reads 200 notes to add them. Cheap on day
one, impossible on day two hundred.

**When nothing connects,** that *is* the finding — Scribe says so out loud rather than
quietly filing an orphan. A concept attached to nothing you know is a concept you
haven't learned yet.

---

## ADR-016 — `HANDOVER.md` carries in-flight state only, not knowledge

**Date:** 2026-09-19 · **Status:** Accepted

Every `/end` writes `data/HANDOVER.md`: what was mid-teach, which question is open, what
was about to happen next.

**Why.** Switching from Cursor to Claude on the same machine is not a cold start — the
notes, skills, and logs are all sitting right there and the new assistant reads them
directly. The only thing genuinely lost is the state of the conversation that was
interrupted. That's all this file carries.

**Correction recorded.** An earlier draft described the new assistant "picking up cold."
The user pointed out this is wrong: the data is local and present. Only session state
transfers.

---

## ADR-017 — Every loop has an explicit exit condition and a disk checkpoint

**Date:** 2026-09-19 · **Status:** Accepted

| Loop | Exits when | Checkpoint |
|---|---|---|
| Inner | you can explain it unprompted | note written |
| Day | commit exists | git commit |
| Review | skill reaches level 5 | `next_review` in skill file |

**Why.** Getting interrupted and losing nothing is the single most visible habit of
engineers who appear to do more than the hours allow. It isn't memory — it's state kept
outside the head. A loop whose state is a file can be abandoned mid-way and resumed. A
loop whose state is a conversation cannot.

**The inner loop's verify step is non-negotiable.** Being taught and being able to
produce are different states, and only the second lasts. On failure it re-teaches
*differently*, not again.

---

## ADR-018 — Decay is built in from day one

**Date:** 2026-09-19 · **Status:** Accepted

Level-5 skills leave the review rotation. Questions unanswered for 60 days close as
*"turned out not to matter."* Notes unlinked for 90 days become archive candidates.

**Why.** The most common death of a second-brain system is an unbounded queue that turns
into a guilt machine. The drain has to exist before the queue does — retrofitting it
means first confronting a backlog of four hundred items, which is exactly when people
quit.

---

## ADR-019 — No LangChain, no LangGraph, no dependencies at all

**Date:** 2026-09-19 · **Status:** Rejected (the libraries) / Accepted (their model)

**Why rejected.** Both require *your Python process to call an LLM*. Here the model lives
inside the assistant and is not reachable from user code, so LangGraph would have nothing
to call — structurally inert, not merely heavy. Separately, `pip install langchain
langgraph` pulls 100+ transitive packages onto a machine under proxy and security
scanning, for a personal learning tool.

**What was kept, free.** Explicit state object, nodes as pure functions, conditional
edges, and a checkpointer for durable resume. All expressible in markdown plus stdlib
Python.

**Door deliberately left open.** Because the workflow graph is declared as *data* rather
than baked into prose, porting to real LangGraph — if an API key ever becomes available
— is transcription, not redesign.

**Generalized:** the whole system is standard library only. Nothing to install is what
makes it viable on a machine you don't control.

---

## ADR-020 — Cold start is an interview, not a dashboard

**Date:** 2026-09-19 · **Status:** Accepted

First `/start` on an empty brain asks five questions, writes `target.md`, seeds 8–12
skill files at honest levels, then teaches one thing immediately.

**Why.** Every clone begins empty (ADR-009), so this is the first thing every user ever
sees. A screen that says *"no data yet"* is where they close the folder. The first
session must end with something learned, not something configured.

**The load-bearing question is #3** — *"what do you nod along to in meetings without
really following?"* It's the one that surfaces real gaps, because it's the one people
don't volunteer.

---

## ADR-021 — Retrieval (RAG) deferred until ~150 notes

**Date:** 2026-09-19 · **Status:** Deferred

Until then, an assistant can read the relevant subset of `data/` directly and the
knowledge graph narrows what "relevant" means.

**Revisit when** `python brain.py graph` reports enough notes that `/start` becomes slow
or the assistant starts missing obviously related material. Local, offline retrieval is
the upgrade — not an API.

---

## ADR-022 — Links live in the note body only, never in frontmatter

**Date:** 2026-09-19 · **Status:** Accepted · **Amends:** ADR-015

The knowledge graph is built by scanning `[[wikilinks]]` in the body. There is no
`links:` key in frontmatter.

**Why.** An earlier draft had both — a `links:` list *and* wikilinks in the prose. Two
sources of the same fact desync the moment anyone edits one and not the other, and the
graph would then depend on which one the parser happened to trust.

**Side benefit:** it forces links into the sentence where the connection is actually
explained, rather than into a metadata list nobody reads. A link with no surrounding
sentence is a link nobody thought about.

---

## ADR-023 — Tests ship with the tool, in `selftest.py`, with no framework

**Date:** 2026-09-19 · **Status:** Accepted

Every assertion lives in `selftest.py`, run by `python brain.py selftest`. Plain
functions and `assert`. No pytest, no fixtures directory, no config.

**Why.** A test framework is a dependency (C2), so on the target machine it cannot be
installed — and a test suite that only runs on the developer's laptop is exactly the one
that's stale when it matters. Shipping the checks means anyone who edits `brain.py` on
any machine can verify it in one command, offline.

**Kept separate from `brain.py`** so the engine stays readable. Not deleted from the
distribution: this tool is meant to be modified by its users, and `selftest` is what
makes that safe.

---

## ADR-024 — Persona isolation is instructed, not enforced

**Date:** 2026-09-19 · **Status:** Accepted · **Amends:** ADR-013

All six personas run sequentially in one conversation, on every assistant. No shipped
file asks any assistant to run a persona in a separate context.

**Why this is recorded as a correction.** ADR-013 claimed that on an assistant with real
subagents each persona would get its own context and the isolation would be *enforced*,
degrading to *instructed* elsewhere. Final verification searched every shipped file —
`AGENTS.md`, `personas/`, `adapters/`, `BOOTSTRAP.md` — for any instruction to that
effect and found none. The only place the claim existed was the README describing it.

**What it costs.** Examiner is told not to use Teacher's reasoning, but it has read it.
An instruction to ignore what you just read is weaker than never having read it, so the
test is not as independent as the design wants.

**Left unbuilt deliberately.** Adding it means per-assistant subagent wiring, which is
exactly the tool-specific complexity the adapter design exists to avoid. The honest
position is a documented limitation rather than a claim nothing implements.

---

## ADR-025 — The dependency check matches module names, not whole lines

**Date:** 2026-09-19 · **Status:** Accepted

The no-third-party-imports gate extracts each imported module name and matches it
against an allow-list with `grep -vx`.

**Why.** The original check piped `grep -nE '^\s*(import|from) ' brain.py selftest.py`
into a second grep whose allow-list contained `brain` and `selftest`. Every output line
is prefixed with its own filename, so the filename alone satisfied the exclude pattern
and **every line passed regardless of what was imported**. `import requests` in
`brain.py` would have produced a clean run. The gate had been green for the whole build
while testing nothing.

**The general lesson, worth more than the fix:** a verification step that has never
failed is not evidence of correctness until you have watched it fail on purpose. This
one was caught only because a reviewer questioned a passing check instead of recording
the pass.

---

## ADR-026 — `paths.data` and `paths.local` are pinned to their defaults

**Date:** 2026-09-19 · **Status:** Accepted · **Amends:** ADR-005

`config.json`'s `paths.data` and `paths.local` can no longer be changed. A non-default
value warns and falls back to the default. `notes`, `skills`, and `log` stay renameable,
same as before.

**Why.** ADR-005 promised every folder was renameable. That promise was too wide: the
outer repo's `.gitignore` matches the literal string `data/`, and `cmd_init` hardcodes
the literal string `local/` into `data/.gitignore`. Renaming `paths.data` moves the
entire brain — `local/` included — out from under the outer `.gitignore` and into the
public, pushable repo. Renaming `paths.local` alone drops the inner ignore layer the same
way, even with `data/` left at its default.

**Rejected:** teaching `.gitignore`, `cmd_init`, and `cmd_migrate` about an arbitrary
data root and local folder, so both stay fully renameable. Correct in principle, but a
bigger and riskier change than the problem justified — three more places would need to
agree on a path that, if any one of them lagged, would silently leak private notes into
a public repo. Pinning the two names that the ignore layers hardcode is the smaller,
safer fix, and it costs nothing: nobody had a reason to rename the data root itself.

---

## ADR-027 — Scheduling moved into `brain.py schedule`

**Date:** 2026-09-19 · **Status:** Accepted

`python brain.py schedule <slug> pass|fail` computes the next `interval_days` from the
fixed table, sets `last_reviewed` to today, and writes `next_review`, directly to the
skill file. It is the only command that writes to `data/skills/*.md`.

**Why.** The design always said date arithmetic must not be the LLM's job (§2, "the
assistant decides language, never dates or scheduling"), but no command existed to do it
on the assistant's behalf, so `AGENTS.md` handed the assistant the interval table
directly and asked it to apply it by hand — the exact thing the design forbade.
`next_interval` was already implemented and tested in `selftest.py`, with no caller
anywhere in `brain.py` outside the test suite. Wiring it to a subcommand closes the gap
between what was built and what was used.

**Rejected:** leaving the interval table in `AGENTS.md` and trusting the assistant to
apply it correctly every time. Works until it doesn't — a single off-by-one on the
interval table silently corrupts a review schedule, and nothing would catch it.

---

## ADR-028 — The four read-but-never-written fields

**Date:** 2026-09-19 · **Status:** Accepted

A final whole-branch review found four places `brain.py` parses and reports on, that no
shipped instruction ever told an assistant to create: `state.json`'s `in_flight` (and
`last_start`/`last_end`), `data/questions.md`, a skill file named by Critic but never
written to disk, and `python brain.py graph`'s output, which nothing in the loop ever
ran. Each is now given an explicit owner in `AGENTS.md` or a persona file.

**Why record the class, not just the four fixes.** Each instance passed review alone —
the code that reads a field is correct, and the docs that describe the field are
accurate. The defect only exists in the gap between the two, and a reviewer looking at
either half separately has nothing to trip on. `cmd_due` correctly prints `interrupted:`
from `in_flight`; nothing in `AGENTS.md` was wrong about *how* to resume it; the only
thing missing was any instruction that ever set it in the first place. Same shape for
the other three.

**What would catch it next time.** Per-field or per-file traceability: for every field a
command reads from `data/`, name the instruction that writes it, in one place, and treat
a field with no listed writer as a bug regardless of how correct the reader and the
prose describing it both are. This review's own final step — reading `AGENTS.md`
end-to-end and building that table — is the check; it should run again after any change
that adds a new field to `state.json`, a new template, or a new `brain.py` reader.

**Rejected:** trusting that a persona's `Produces` section implies someone writes the
things a sibling `Gets` section reads. It doesn't — `Produces` and `Gets` are contracts
between personas in the same loop, not a registry of every file `brain.py` touches, and
none of the four gaps here were between two personas in one loop; they were between the
engine and the entire protocol.
