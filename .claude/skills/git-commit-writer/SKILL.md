---
name: git-commit-writer
description: Write clear Conventional-Commits messages and structure changes into logical commits. Use after an implementation phase or when the user asks to commit. Produces feat/fix/refactor/docs/test/chore messages with a focused subject and a body explaining the why. Note this project is not currently a git repo — offer to initialize one if the user wants version control.
---

# Git Commit Writer

A commit is a unit of intent, not a save point. Each commit should be a coherent change with a
message that explains *why* it exists.

## When to invoke
- After completing an implementation phase (from `implementation-planner`).
- When the user asks to commit or prepare a PR.

> ⚠️ The-RAG is **not currently a git repository**. If the user wants commits, offer to
> `git init` first. Don't assume version control exists.

## Conventional Commits format
```
<type>(<optional scope>): <imperative subject, ≤72 chars>

<body: what changed and WHY — the context a reviewer needs>
<blank line>
<optional footer: BREAKING CHANGE: …, refs #123>
```

**Types**
- `feat` — new capability · `fix` — bug fix · `refactor` — behavior-preserving restructure
- `docs` — documentation · `test` — tests · `perf` — performance · `chore` — tooling/deps/config
- `build`/`ci` — build system / pipelines

**Scopes for The-RAG**: `ingest`, `chunking`, `embed`, `retrieval`, `rerank`, `generation`,
`api`, `eval`, `corpus`.

## Rules for good commits
- **Atomic**: one logical change per commit. Don't mix a refactor with a feature (see
  `refactoring-expert`). Split unrelated changes.
- **Imperative subject**: "add fiscal-period filter", not "added"/"adds".
- **Explain the why** in the body when it isn't obvious from the diff. Reference the requirement
  or bug. Note tradeoffs and follow-ups.
- Keep the subject focused; wrap the body at ~72 cols.
- Never commit secrets, `.env`, large data, or generated artifacts — check `.gitignore` first.

## Examples
```
feat(chunking): section-aware splitter that preserves financial tables

Split 10-K/10-Q on canonical items before recursive paragraph splitting, and
keep tables whole so rows stay attached to their headers and periods. Fixes
retrieval returning header-less number fragments.

refactor(retrieval): extract VectorStore protocol from Qdrant client

No behavior change; decouples retrieval from the concrete store so the index
can be swapped and mocked in tests.
```

## Output
The commit message(s). If a change spans multiple concerns, propose how to split it into several
commits, each with its own message. End commit messages with the required co-author trailer.
