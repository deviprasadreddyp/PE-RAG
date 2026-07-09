---
name: root-cause-analyzer
description: Diagnose the underlying cause of a bug, failure, or incident instead of patching the symptom. Keep asking "why?" until you reach the true origin, form a falsifiable hypothesis, and verify it against evidence before fixing. Use for any non-obvious bug, flaky behavior, wrong RAG answers, or production incident.
---

# Root Cause Analyzer

A symptom fix that doesn't understand the cause usually reappears elsewhere. Find the real
origin, prove it, then fix it — and prevent the class of bug.

## When to invoke
- A bug whose cause isn't immediately obvious.
- Flaky/intermittent behavior. Wrong or hallucinated RAG answers. A production incident.

## Method
1. **Reproduce.** Get a reliable, minimal reproduction. If you can't reproduce it, you can't
   confirm you fixed it. Capture the exact inputs, environment, and observed vs expected.
2. **Gather evidence.** Logs, stack traces, inputs, recent changes, metrics. Follow the data;
   don't theorize in a vacuum.
3. **Form ONE falsifiable hypothesis** about the cause. Predict what you'd see if it's true.
4. **Test the hypothesis** against evidence (add a log/probe, bisect the change, isolate a
   component). Confirm or reject. Repeat with a new hypothesis if rejected.
5. **Ask "why?" repeatedly** (5 Whys) to go from proximate to root cause:
   *wrong answer → retrieved wrong chunk → chunk lacked period metadata → header parser
   dropped the fiscal quarter → filename-only parsing ignored the header block.*
6. **Fix the root**, not just the surface. Then ask: what else has this same root cause?
7. **Prevent recurrence.** Add a regression test (`testing-engineer`) and, if warranted, a guard
   or invariant so the whole class can't recur.

## RAG failure triage
When an answer is wrong, localize the stage before blaming the model:
- **Retrieval failure** — was the correct chunk even in the top-k? (Check with `retrieval-evaluator`.)
  If not, the bug is in chunking / embedding / filtering, not generation.
- **Context assembly** — was the right chunk retrieved but truncated/dropped from the prompt?
- **Generation** — was the context correct but the model ignored it or hallucinated?
- **Data** — was the source itself wrong/stale/mis-parsed (e.g. XBRL noise, wrong period)?

## Guardrails
- Don't fix by coincidence — if you don't know *why* a change worked, you're not done.
- Resist the first plausible story; verify it. Correlation with a recent change ≠ cause.

## Output
Reproduction · evidence · confirmed root cause (with the "why" chain) · the fix · the regression
test · what class of bug this prevents.
