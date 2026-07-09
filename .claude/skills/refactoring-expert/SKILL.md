---
name: refactoring-expert
description: Restructure working code to be simpler, cleaner, and more modular WITHOUT changing its observable behavior. Use when code works but is hard to read, duplicated, deeply nested, or poorly factored, and after a feature lands to pay down debt. Always paired with tests that prove behavior is unchanged.
---

# Refactoring Expert

Improve structure without changing behavior. The rule: **tests green before, tests green after.**

## When to invoke
- Code works but is messy, duplicated, or hard to extend.
- After a feature lands, before moving on ("make it work, then make it right").

## Preconditions
- There are tests (or you add characterization tests first) that capture current behavior.
- If behavior *should* change, that's a feature/bugfix, not a refactor — do it separately.

## Techniques (apply the smallest that helps)
- **Extract function/method** — name a block by its intent; shrink long functions.
- **Extract module/class** — group data with the behavior that operates on it.
- **Introduce an interface** — decouple callers from a concrete implementation (e.g. swap a
  vector-store client behind a `VectorStore` protocol).
- **Replace conditionals with polymorphism / lookup tables** when a switch keeps growing.
- **Remove duplication** — but only real duplication (same reason to change), not lookalikes.
- **Simplify data flow** — reduce shared mutable state; prefer pure functions at the core.
- **Guard clauses** — flatten nested `if/else`; return early.
- **Rename** — the cheapest, highest-leverage refactor.

## Process
1. Confirm a green test baseline (add characterization tests if missing).
2. Make ONE structural change at a time. Re-run tests after each.
3. Commit each safe step separately (hand messages to `git-commit-writer`).
4. Stop when the code is clear — don't gold-plate. Check with `complexity-minimizer`.

## Guardrails
- Don't mix refactoring with behavior changes in one commit.
- Don't abstract on the first duplication — wait for the pattern to prove itself (rule of three).
- Prefer deleting code over adding cleverness.

## Output
The refactored code, a note of what changed structurally and why, and confirmation that the
test suite still passes (with the actual result, not an assumption).
