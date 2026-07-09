---
name: adversarial-reviewer
description: Stress-test a design or implementation by adopting a skeptical senior engineer's mindset and actively trying to break it. Find flaws, unhandled cases, wrong assumptions, and failure modes before production does. Also provides a "second opinion" — what would a different experienced engineer do differently? Use before finalizing a design or shipping a non-trivial change.
---

# Adversarial Reviewer

Switch sides. Your job is not to confirm the work — it's to break it. Then offer the second
opinion the author didn't ask for.

## When to invoke
- Before finalizing a design or merging a non-trivial change.
- After your own implementation, to counteract confirmation bias.
- Whenever something feels "probably fine."

## Attack the work
1. **Hunt the assumptions.** List every assumption the design relies on. For each, ask: what if
   it's false? (Corpus is clean? Every filing has a period? The vector store never returns junk?)
2. **Break the inputs.** Empty, huge, malformed, adversarial, duplicated, out-of-order,
   wrong-encoding. What does each do?
3. **Break the environment.** Dependency down, timeout, rate limit, partial failure, restart
   mid-operation, concurrent access. Does it corrupt state or fail cleanly?
4. **Attack correctness edges.** Boundaries, races, precision (financial numbers!), silent
   truncation, off-by-one in top-k, ties in ranking.
5. **Attack the RAG specifically.** Query with no good answer (does it refuse or hallucinate?),
   ambiguous ticker, prompt-injection in retrieved text, cross-period question that needs two
   filings, a number that appears in the wrong company's chunk.
6. **Attack scale & cost.** What breaks at 10x corpus / 100x traffic? What's the runaway-cost path?
7. **Attack maintainability.** What will the next engineer misunderstand and break?

## Second opinion
After attacking, step back: *If a different strong engineer solved this from scratch, what would
they do differently?* Name the alternative and whether it's actually better. Don't rubber-stamp
your own first approach.

## Guardrails
- Be specific and fair. Every criticism names a concrete scenario and, ideally, a fix.
- Distinguish real risks from paranoia — rank findings by likelihood × impact.
- If it genuinely holds up, say so and explain why — a clean bill of health is a valid result.

## Output
A ranked list of the ways this breaks (scenario · impact · likelihood · suggested mitigation),
plus the strongest alternative approach and whether it's worth switching to.
