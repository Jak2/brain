# Check registry — the work gate

You are about to help with real work. Before you start, run this.

This is the second half of `brain`. `AGENTS.md` is the *learning* loop: it runs at
`/start` and `/end` and teaches what the person doesn't know. This file is the *work*
gate: it runs during the work itself and catches what the person forgot to ask for.

The two are connected at one point — the miss log. See [Promotion](#promotion).

## When to run this

Not on every message. A gate that fires on "what does this function do" gets switched
off in three days, and then it catches nothing at all.

| The request is | Do |
|---|---|
| a lookup, an explanation, a read, a one-line fix | answer it, no gate |
| anything that writes non-trivial code, changes a design, picks a dependency, or commits more than ~30 minutes | **run the gate** |

When it is genuinely unclear which, run the gate. A wrong "no gate" costs a day; a
wrong "gate" costs one extra question.

## The gate

```
request ──> restate it ──> run each check ──> keep only the questions
                             (one question       that change the build
                              each, at most)              │
                                                          v
             proceed <── log what was missed <── ask (max 3)
```

**1. Restate.** One sentence: what you are about to build, including every assumption
you filled in yourself. Assumptions you made silently are where the miss lives.

**2. Run each check.** Read every file in `checks/` and, if the folder exists,
`data/checks/` — those are the person's own, promoted from repeated misses. Each check
produces at most one question.

**3. Filter.** Keep only questions whose answer would change what you build. Drop the
rest. **Ask at most three.** If more than three survive, the scope is too big to start —
say that instead, and propose a smaller first slice.

**4. Log.** Append one line to `data/misses.md` **for every check you ran**, not only
the ones that found something:

```
- YYYY-MM-DD check-slug | what they did not specify
- YYYY-MM-DD check-slug | ok
```

`ok` means the check ran and found nothing — they had already covered it, or it did not
apply. Those lines are the denominator: five misses out of five runs and five out of two
hundred are different findings, and without the `ok` lines they look identical. A gate
that logged only misses cannot tell them apart afterwards, so log both at the time.

The date is today. The slug is the check's `slug:` field. Keep the text employer-free —
the same split as `AGENTS.md` standing rule 3. Specifics go to `data/local/`.

**5. Proceed.** Do the work.

## The checks

Fixed, and they run whether or not the request hints at them. That is the point: a
check you only run when the prompt suggests it inherits the prompt's blind spot.

| Check | Asks |
|---|---|
| [tests](tests.md) | how do we know it works, and how do we know when it breaks |
| [cost](cost.md) | is this worth what it costs, and what is the cheaper version |
| [operations](operations.md) | what happens at 3am when this fails |

Do not invent new personas per problem. The framing you would generate them from is the
framing with the gap in it.

## Promotion

`python brain.py misses` counts the log and prints `missed / times the check ran`. A
check slug **missed** `policy.promotion_threshold` times or more (default 5) while still
unexpired is a **promotion candidate**: it is not an occasional oversight, it is a
standing hole.

Promotion counts raw misses today, not the rate. The `ok` lines are recorded anyway
because a denominator cannot be reconstructed after the fact — see "Waiting on real use"
in `README.md`.

Promote it by writing `data/checks/<slug>.md` in the same shape as the files here. It
then runs on every gate, forever, exactly like the three fixed ones.

Promoted checks live under `data/`, never in this folder — `AGENTS.md` standing rule 2
holds here too, and a personal check belongs in the repo that has no remote.

`python brain.py due` surfaces promotion candidates at `/start`, which is where the work
gate feeds the learning loop: something you keep missing is a gap worth teaching, not
just a checklist item worth adding.

Misses older than `policy.miss_expiry_days` (default 90) expire and drain through
`python brain.py decay`. Only unexpired misses count toward promotion — the question is
whether you *still* do this, not whether you once did.
