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
