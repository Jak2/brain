---
slug: operations
---

# Operations

What happens at 3am when this fails.

Development asks *does it work*. Operations asks *how does it tell you it stopped, and
what does the person on call do next*. The second question is the one that is almost
never in the prompt.

## Gets
- The restated request
- Where this runs: a script, a service, a job, a build step

## Produces
At most **one** question:

1. When this fails, who finds out and how? A silent failure is worse than a loud one.
2. What is the blast radius of getting it wrong — one request, one user, one table, or
   everything? And is the operation reversible?
3. What does it depend on that can be down, slow, or full? Network, disk, a credential
   that expires, a quota.

## Forbidden
- Asking for monitoring, alerting, dashboards or retries on a local script that nobody
  operates. Scale the question to where the thing actually runs.
- Demanding a rollback plan for something that is trivially re-runnable.
- Turning one question into an availability review. One question.

## Done when
One question asked, or a deliberate "no question — nothing operates this."
