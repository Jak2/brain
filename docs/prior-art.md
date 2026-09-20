# Prior art — what already exists, and what was taken from it

**Surveyed 2026-09-20.** A search for projects making the same bet as `brain`: markdown
that drives whatever AI assistant you already have, no model of its own.

Two repositories were cloned and read at source rather than judged from their READMEs:
`itechmeat/open-second-brain` and `ChenChenyaqi/learn-anything`.

This file records what was found, what was taken, and what was deliberately not taken.
The operational half — which deferred items get built and what observation triggers each
— lives in [Waiting on real use](../README.md#waiting-on-real-use), because that is a
decision you make from your own log, not from this survey.

---

## 1. What exists

### Closest to the learning half — `learn-anything`

[ChenChenyaqi/learn-anything](https://github.com/ChenChenyaqi/learn-anything) · MIT ·
~456 stars. The same core bet, reached independently: markdown that drives the assistant
you already have, `AGENTS.md`-compatible, spaced repetition, `state.json` as the single
source of truth, a knowledge map, Socratic deep-dives.

Someone arrived at the same conclusion and is ahead on adoption. That validates the bet
and is worth saying plainly.

It differs where it matters here: it is a Node CLI installed with `npm`, which fails the
hardest constraint outright. No personas, no contracts, no forbidden column. Its
knowledge map is rendered markdown, not a graph — no orphans, hubs, frontier or bridges.
No decay, no two-repo no-remote safety, no work gate.

### Closest to the verify step — Covate

An MCP server that quizzes you on code your AI just wrote and blocks the AI from
continuing until you pass. A harder verify gate than Examiner, and the direct answer to
this project's unproven item: an Examiner can be talked past by a willing user.

Two disqualifiers: it installs as an MCP server, and its ledger is hosted with GitHub
sign-in — work-derived material leaving the machine. Non-starter here. The blocking
mechanism is still the right idea.

### Closest to the work gate — the spec-driven family

GitHub Spec Kit, BMAD-METHOD, OpenSpec, `buildermethods/agent-os`. All active, all
overlapping with "clarify before you build". BMAD's multi-agent personas are the nearest
existing thing to personas-as-contracts.

None of them logs what *you personally* keep missing, counts it, promotes it into a
permanent check, or feeds it back into learning. They are also heavy — a whole ceremony
per feature, with no trigger condition. The trigger rule in
[`checks/REGISTRY.md`](../checks/REGISTRY.md) is the thing they don't have.

### Closest to the mechanics — `open-second-brain`

[itechmeat/open-second-brain](https://github.com/itechmeat/open-second-brain) ·
TypeScript on Bun, MCP, an Obsidian vault. Adapters for eight runtimes. The only project
found whose internals overlap closely enough that reading the code taught something the
README did not. Most of the ledger below comes from it.

### Adjacent, not competing

`arkangelai/second-brain`, `oweindl/SecondBrain`, Karpathy's LLM Wiki pattern — markdown
knowledge vaults with `agents.md` as the control plane. Knowledge management; no
teaching, no verify, no skill levels. GoCard, LearnKit for Obsidian, FSRS — markdown
spaced repetition with better scheduling than the fixed table here, and no connection to
your work or your assistant.

### Honest verdict

Nothing found does all five: zero install, teach → verify → capture, graph metrics as
the selection signal, structural no-push safety, and a work gate feeding learning
through a miss log. The combination is unoccupied.

Two pillars are individually better served elsewhere — `learn-anything` on adoption and
breadth, Covate on making verify unfakeable. And an unoccupied combination is not the
same as one worth occupying. That gets settled by running it, not by this survey.

The two real differentiators on a work laptop are the boring ones: nothing to install
(stdlib Python, not npm) and nothing leaves the machine (no remote, no hosted ledger).
Both of the closest projects fail one of those.

---

## 2. Taken

### Record the denominator — **shipped**, ADR-035

`open-second-brain` tracks `_applied_count` **and** `_violated_count` on every
preference file. `data/misses.md` recorded only the violations, so five misses could
mean five gates out of five or five out of two hundred — indistinguishable, and
unrecoverable afterwards, since a gate that passed leaves no other trace.

The gate now logs one line per check it runs, `| ok` when it found nothing.
`brain.py misses` prints `missed / times the check ran`.

Their preference frontmatter, for reference:

```yaml
_applied_count: 0
_violated_count: 0
_evidenced_by: []
_last_evidence_at: null
_confidence_value: 0
_status: unconfirmed
unconfirmed_until: "2026-05-25T11:00:00Z"   # 14 days after created_at
```

---

## 3. Taken in principle, deferred in practice

Each of these is designed and not built. The trigger conditions are in
[Waiting on real use](../README.md#waiting-on-real-use); the sources are here.

**Rate-based promotion.** `confidence.ts` computes
`value = wilson_low(applied, applied + violated) × freshness`, where freshness decays
linearly to zero at `stale_evidence_days`. Wilson rather than a raw ratio, so one
success out of one does not outrank ten out of ten. Two useful properties: decay folds
into the value instead of needing a separate expiry pass, and the bound is conservative
by construction. Roughly twenty lines of statistics on data that does not exist yet.

**Auto-close.** Their gap tasks close themselves when the topic recalls cleanly again
(`gap-loop.ts`, `autoCloseRecalledGaps`). A promoted check here is permanent once
written, which is wrong: a habit you have fixed should stop being asked about.

**Retire with a reason.** A retired preference moves to `retired/` carrying
`retired_reason: stale-no-evidence`, `retired_at`, `retired_by`, and an `aliases:` entry
so existing links still resolve. Nothing is deleted. `brain.py decay` currently drops
expired misses into nothing, which makes decay a claim rather than something you can
audit.

**Blocking verify.** Covate's mechanism, not Covate. A `verify` step that marks state
blocked and instructs the assistant to refuse new work until cleared.

**A single priority score for Scout.** From `learn-anything`'s `/learn-review`:

```
priority = (1 - confidence) × (days_since_last_practice + 1) × w
w = 1.0 needs_practice · 0.6 in_progress · 0.3 mastered · 0.1 unexplored
```

One line. Scout currently combines graph metrics and due dates with no explicit
combining rule, which is fine until it visibly is not.

---

## 4. Not taken

**An `install.lock.json` adapter manifest.** Recommended, then withdrawn on reading our
own code: `cmd_bootstrap` writes only inside this clone, so git already records exactly
what it added and `git clean` removes it. `open-second-brain` needs a sidecar manifest
because it installs into MCP configs, hooks and editor settings across eight runtimes,
outside its own folder. This project mutates nothing outside the clone.

**`learn-anything`'s breadth** — 30+ tools. That is the trap, not the lesson. A system
with zero sessions run does not need more surface.

**Spec-driven ceremony** — Spec Kit and BMAD run a full process per feature. The trigger
rule is what they lack; importing what they have would import the reason their gates get
switched off.

**MCP servers, hosted ledgers, npm, Bun, Obsidian.** Each fails either "no install" or
"nothing leaves the machine". Those two constraints are not preferences.

**FSRS.** A better scheduler than the fixed interval table, unconnected to anything
else. Worth porting only if review scheduling ever becomes the part that is failing.

---

## 5. What this survey cannot settle

Every ranking above is inference from someone else's design decisions, made against
their usage, not yours. Zero real sessions have run here. The item that actually breaks
first is probably not the one ranked highest — which is why nothing in section 3 is
built, and why each one waits on an observation rather than an argument.
