---
name: complexity-minimizer
description: Relentlessly ask "can this be simpler?" and produce the simplest correct version of a design or implementation. Use when something feels over-engineered, has too many layers/abstractions/config knobs, or when reviewing a design before committing to it. The goal is the least machinery that solves the actual requirement.
---

# Complexity Minimizer

The best code is the code you didn't write. Fight incidental complexity; keep only what the
requirement demands.

## When to invoke
- A design or implementation feels heavier than the problem.
- Lots of layers, indirection, generics, config flags, or "future-proofing."
- Before committing to an architecture or merging a feature.

## Questions to ask, in order
1. **Is this needed at all?** Can the requirement be met by deleting code or doing nothing?
2. **Is there a simpler shape?** A function instead of a class; a dict instead of a hierarchy;
   a library call instead of a hand-rolled implementation.
3. **Am I solving a problem I actually have?** Speculative generality (abstractions with one
   implementer, config nobody sets, extension points nobody uses) is complexity with no payoff.
4. **Can I reduce moving parts?** Fewer services, fewer states, fewer branches, less shared
   mutable state.
5. **Is the data model too clever?** Simple, explicit data beats clever encodings.
6. **Would a new engineer be surprised?** Surprise is a complexity smell.

## Heuristics
- YAGNI: build for today's requirement, not an imagined one. Extensibility comes from clean
  boundaries, not from pre-built knobs.
- Prefer boring, obvious solutions. Cleverness is a loan against future understanding.
- One good abstraction beats three mediocre ones; zero beats one you don't need yet.
- Deleting a feature/option is a valid and often best answer.

## Guardrail
Simpler ≠ fewer characters at the cost of clarity. Don't collapse readable code into a dense
one-liner. Simplicity is about **fewer concepts to hold in your head**, not golf.

## Output
The simplest version that still meets the requirement, plus a short list of what you removed
and why it was safe to remove.
