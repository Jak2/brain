---
slug: tests
---

# Tests

How we know it works, and how we find out when it stops.

## Gets
- The restated request
- The files the change will touch

## Produces
At most **one** question, and only if the answer would change the build. In order of
what is most often missing:

1. What is the one check that fails if this logic breaks? Name it concretely — an
   assertion, a test name, a command — not "we should add tests."
2. What input has nobody named yet? Empty, absent, malformed, duplicate, too large,
   wrong type, hostile.
3. If this replaces existing behaviour, what proves the old behaviour still works?

## Forbidden
- Asking for full coverage. One runnable check that fails when the logic breaks beats a
  suite nobody writes.
- Asking about tests for a change with no branch, no loop and no parsing. A one-line
  constant does not need a test, and asking anyway is how the gate gets switched off.
- Writing the test yourself at this stage. This is the gate, not the work.

## Done when
One question asked, or a deliberate "no question — this has no logic to break."
