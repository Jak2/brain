# brain

A mentor that lives in your repo and works with whatever AI assistant you already have.

Clone it. Point your assistant at it. It interviews you, finds what you don't know,
teaches you, tests whether it stuck, writes it down, and brings it back before you
forget it.

No API key. No pip install. No account. No network after the clone.
Works on a locked-down corporate laptop.

---

## Why this exists

Some engineers seem to implement, learn, and ship far more than the hours allow.
They aren't faster readers. Two things separate them:

1. **Their knowledge is connected.** A new problem lands next to five things they
   already know instead of on empty ground. That's compounding, and it's measurable
   — see [The knowledge graph](#the-knowledge-graph).
2. **Their state lives outside their head.** They get interrupted and lose nothing,
   because every loop they're running has a checkpoint on disk.

`brain` is built to produce both on purpose instead of by luck.

## What this is not

- Not a note-taking app. It writes notes, but the notes are a side effect.
- Not an AI. It has no model. It *drives* the assistant you already have.
- Not a cloud service. Nothing leaves your machine.
- Not a syllabus. It teaches what your actual work exposes, plus what your target
  role needs and your work never shows you.

---

## Requirements

- Python 3.9+ (standard library only — nothing to install)
- git
- An AI coding assistant: **Claude Code, Cursor, GitHub Copilot, Codex, Gemini CLI,
  Windsurf, Zed, Aider,** or anything else that reads `AGENTS.md`

That's the whole list.

---

## Quick start

```bash
git clone <repo-url> brain
cd brain
python brain.py init
```

Then open the folder in your assistant and say:

> Read BOOTSTRAP.md and follow it.

It will ask which assistant it is, install the right adapter, and hand you your first
lesson. Setup ends with you having learned something, not with a configuration screen.

From then on, two commands:

| Command | What happens |
|---|---|
| `/start` | Reads your brain. Gives you three things: one review that's due, one gap worth closing, one open question. |
| `/end` | Writes today's notes, updates your skill levels, schedules reviews, commits. |

If your assistant doesn't support slash commands, type `start` and `end`. `AGENTS.md`
defines both, so every assistant understands them.

---

## How it works

### Two repositories, on purpose

```
brain/                  <- the system. public. you pull updates. you never write here.
  AGENTS.md  brain.py  personas/  templates/  adapters/

  data/                 <- your brain. gitignored above. its own git repo. NO REMOTE.
    target.md  notes/  skills/  log/  questions.md  local/
```

This split does two jobs at once:

- **The outer repo holds no data**, so `git pull` for system updates is always clean.
  No conflicts, no stashing, forever.
- **The inner repo has no remote**, so `git push` fails with *"no configured push
  destination."* Your notes cannot be pushed anywhere by accident.

That second one matters on a work laptop. See [Using this at work](#using-this-at-work).

You still get commits, history, and undo on your own brain — locally.

### The day loop

```
/start ──> assess ──> select ──> teach ──> verify ──┬─(you can explain it)──> capture ──> schedule ──> /end
                                    ^               │
                                    └──(you can't)──┘  re-teach, differently
```

**The verify step is the point.** Being taught something and being able to produce it
are different states, and only the second one lasts. The loop does not advance until
you can explain the thing in your own words without prompting. When you can't, it
teaches it again a *different* way — not louder, differently.

### Three loops, each with a checkpoint

| Loop | Cycle | Exits when | Checkpoint on disk |
|---|---|---|---|
| Inner (minutes) | teach → verify → re-teach | you explain it unprompted | note written |
| Day | `/start` → work → `/end` | commit exists | git commit |
| Review (spaced) | resurface → recall → re-schedule | skill hits level 5 | `next_review` in the skill file |

Every loop can be abandoned mid-way and resumed, because its state is a file, not a
conversation.

### Decay — why the queue won't bury you

Most second brains die from an unbounded to-do queue. This one drains itself:

- A skill at level 5 leaves the review rotation.
- A question unanswered for 60 days closes as *"turned out not to matter."*
- A note never linked in 90 days becomes an archive candidate.

Nothing accumulates forever. That's deliberate, and it's why the system survives a busy
month.

### The knowledge graph

Every note links to other notes and skills with `[[wikilinks]]`. A note with zero links
is rejected — if nothing connects, that's the finding, not a filing problem.

Once you have ~30 notes, `python brain.py graph` reports what you cannot see by
re-reading your own notes:

| Metric | What it means about you |
|---|---|
| **Orphans** | You memorized a fact, not a concept. Connect it or drop it. |
| **Hubs** | Your real foundations — measured, not as you imagine them. |
| **Frontier** | Unlearned skills adjacent to your hubs. The cheapest next lesson with the highest chance of sticking. |
| **Bridges** | Notes joining two clusters. The closest measurable proxy for senior-engineer range. |

**Frontier is the honest answer to "what should I learn next?"** — better than a
syllabus, better than a hunch.

### Personas

The workflow above is a graph, and its nodes are personas. A persona is only useful if
it has a different *contract*, not a different voice. "Now be skeptical" is theater.
"You may read only these five notes and must output three falsifiable questions" is a
function.

| Persona | Gets | Must produce | Forbidden from |
|---|---|---|---|
| **Scout** | `target.md` + skill graph | one skill to attack, with the reason | teaching |
| **Teacher** | that skill | explanation + worked example | asking questions |
| **Examiner** | the concept only — *not* Teacher's reasoning | 3 questions requiring production, not recognition | giving answers |
| **Scribe** | the exchange | a note with `[[links]]` | adding new content |
| **Critic** | your notes | where you're fooling yourself | being encouraging |
| **Archivist** | the whole graph | orphans, bridges, decay actions | teaching |

The **forbidden** column is what makes these real. Examiner not seeing Teacher's
reasoning is what makes the test fair.

On an assistant with real subagents (Claude Code), each persona runs in its own context
and the isolation is enforced. Everywhere else they run sequentially in one thread and
the isolation is instructed. It degrades honestly — the contracts don't change.

---

## Cold start

A fresh clone has an empty brain. There is nothing to reason over, so the first
`/start` is an **interview, not a dashboard**. Five questions:

1. What do you actually do all day?
2. What do you want to be doing in 18 months?
3. What do you nod along to in meetings without really following?
4. What have you tried to learn and dropped? Why?
5. How much time per day, honestly?

From those it writes `target.md` and seeds 8–12 skill files at honest levels — then
teaches you one thing immediately.

Answer question 3 truthfully. It's the one that makes this worth running.

---

## Using this at work

Designed for a laptop you don't own.

**Nothing to install.** Python stdlib and git. No pip, no model download, no network
call after the clone. Nothing for IT to approve or block.

**Your employer's information never enters git.** Every `/end` splits what it captured:

| Goes to | Contains | In git |
|---|---|---|
| `data/notes/` | the **concept**, employer-free — *"async task starvation when a sync call blocks the loop"* | yes (local only) |
| `data/local/` | the **context** — ticket IDs, internal service names, their code | **never**, gitignored twice |

The knowledge is yours and comes with you. The specifics stay on the machine.

**You cannot push by accident.** `data/` has no git remote. There is no policy to
remember and no hook to bypass — the operation has nowhere to go.

**If your machine is reimaged, your brain is gone.** That is the accepted trade for not
moving work-derived material off a corporate device. Know it going in.

### If you *are* allowed to back up your brain

On a machine where that's fine — your own — opt in with one command:

```bash
cd data && git remote add origin <your-private-repo>
```

Use a **private** repo. Everything else is unchanged.

---

## Switching assistants

Adapters are additive. Bootstrap installs the key for whichever assistant is running
and **touches no other**. Use Cursor in March and Claude in June and both adapters sit
in the repo; switch back and yours is still there. Running bootstrap twice changes
nothing.

Your data doesn't move or convert — it's plain markdown in `data/`, and the new
assistant reads it directly. `data/HANDOVER.md`, written by every `/end`, carries only
the **in-flight session state**: what was mid-teach, which question is still open, what
was about to happen. Not your knowledge — that's already on disk.

| Assistant | Instructions read from | Commands installed to |
|---|---|---|
| Codex, Aider, Zed, Windsurf, Devin | `AGENTS.md` (native) | — |
| Cursor | `AGENTS.md` (native) | `.cursor/commands/` |
| Claude Code | `CLAUDE.md` → `@AGENTS.md` | `.claude/commands/` |
| GitHub Copilot | `.github/copilot-instructions.md` | `.github/prompts/` |
| Gemini CLI | `GEMINI.md` | — (type `start` / `end`) |

`AGENTS.md` is the single source of truth. Every other file is a one-line pointer to
it, so there is nothing to keep in sync.

---

## Commands

```
python brain.py init        Create data/, its git repo, and the starting files
python brain.py bootstrap   Detect the assistant, install its adapter (additive)
python brain.py due         Today's briefing: reviews due, top gap, oldest question
python brain.py graph       Orphans, hubs, frontier, bridges
python brain.py migrate     Rename folders safely — rewrites [[links]], keeps history
python brain.py selftest    Verify date math, parsing, graph metrics, idempotence
```

`brain.py` is standard library only and cross-platform. Run `selftest` after any edit.

---

## Layout

```
brain/
  README.md            this file
  BOOTSTRAP.md         what a new assistant reads first
  AGENTS.md            THE protocol — read by 30+ assistants natively
  DECISIONS.md         every design decision and why, including what was rejected
  brain.py             the engine. stdlib only.
  config.json          paths and policy. the only file bootstrap edits.
  personas/            scout, teacher, examiner, scribe, critic, archivist
  templates/           note, skill, log, handover
  adapters/            per-assistant command templates
  docs/design.md       full architecture

  data/                yours. gitignored. own git repo, no remote.
    target.md          target role and ranked gaps
    state.json         where each loop stopped
    HANDOVER.md        in-flight session state
    notes/             YYYY-MM-DD-slug.md, one concept each, [[linked]]
    skills/            one file per skill: level 0-5, evidence, next_review
    log/               one file per day
    questions.md       open queue
    local/             employer specifics. never in git, anywhere.
```

---

## Customizing

**Renaming folders:** change `config.json`, never paths in code. Run
`python brain.py migrate` first — it rewrites `[[links]]` and preserves git history.

**Editing `brain.py`:** it's yours. Run `python brain.py selftest` afterwards.

**Changing how it teaches:** `AGENTS.md` and `personas/` are plain markdown. The
workflow graph is a table you can edit. Changing teaching policy means editing a table,
not rewriting a prompt and hoping.

---

## Why no LangChain or LangGraph

Both need *your Python process to call an LLM.* Here the model lives inside your
assistant and isn't reachable from your code, so there'd be nothing to call —
structurally inert, not merely heavy. And `pip install langchain langgraph` pulls 100+
transitive packages onto a machine under proxy and security scanning.

Their good ideas cost nothing to keep: explicit state object, nodes as pure functions,
conditional edges, a checkpointer for durable resume. All of that is here, in markdown
and stdlib Python.

Because the graph is declared as **data**, porting to real LangGraph the day you get an
API key is transcription, not redesign.

---

## Troubleshooting

**`/start` does nothing** — your assistant may not support slash commands. Type `start`.

**Assistant ignores the rules** — confirm the adapter for *your* tool exists
(`python brain.py bootstrap`), and that you opened the `brain/` folder itself as the
workspace root, not a parent directory.

**"No data yet"** — run `python brain.py init`.

**Reviews never come due** — check `next_review` in `data/skills/`. Then
`python brain.py selftest` to confirm the date math.

**`git push` fails in `data/`** — working as designed. See
[Using this at work](#using-this-at-work).

---

## Design decisions

Every decision, its rationale, and the alternatives that were rejected:
[DECISIONS.md](DECISIONS.md). Read it before proposing a change — the rejected options
are the useful part.
