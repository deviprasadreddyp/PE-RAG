# The-RAG Skill Library

Small, single-responsibility skills that Claude Code auto-invokes based on their
`description`. Unix philosophy: one skill = one job; Claude composes them into a
staff-engineer workflow.

```
understand → design → plan → implement → review → test → optimize → document
```

## Groups

### Engineering (do this before writing code)
| Skill | Fires when |
|-------|-----------|
| `requirements-analyzer` | A feature/task is stated but underspecified — before any design or code. |
| `architecture-designer` | A new component/system needs module, API, data, and flow design. |
| `implementation-planner` | An approved design must become ordered, independently testable phases. |

### Quality
| Skill | Fires when |
|-------|-----------|
| `senior-code-reviewer` | After writing/changing code — folds in naming, DRY, SOLID, dead-code, logging, error-handling, API-consistency, PR review. |
| `refactoring-expert` | Code works but is messy; restructure without changing behavior. |
| `complexity-minimizer` | Something feels over-engineered; find the simplest correct version. |
| `testing-engineer` | New/changed behavior needs unit, integration, edge, and failure tests. |
| `security-auditor` | Reviewing auth, input handling, secrets, uploads, or prompt-injection surface. |
| `performance-optimizer` | Latency/throughput/redundant-work concerns in code or pipelines. |

### Reasoning (sharpen thinking before/around decisions)
| Skill | Fires when |
|-------|-----------|
| `tradeoff-analyzer` | Choosing between DBs, frameworks, algorithms, or architectures. |
| `root-cause-analyzer` | A bug/incident needs the underlying cause, not a symptom patch. |
| `adversarial-reviewer` | A design/implementation should be stress-tested by a skeptic (incl. "second opinion"). |

### AI / RAG (this project's core)
| Skill | Fires when |
|-------|-----------|
| `rag-reviewer` | Reviewing/designing chunking, embeddings, indexing, retrieval, reranking, context assembly. |
| `chunking-strategist` | Deciding how to split SEC filings into chunks + metadata. |
| `retrieval-evaluator` | Measuring retrieval/answer quality (recall@k, MRR, nDCG, faithfulness). |
| `llm-pipeline-reviewer` | Reviewing prompts, structured outputs, retries, streaming, fallbacks. |
| `cost-optimizer` | Reducing token/embedding/API spend. |
| `financial-document-handler` | Parsing SEC filings: XBRL stripping, tables, fiscal periods, numeric citation fidelity. |

### Operations
| Skill | Fires when |
|-------|-----------|
| `reliability-engineer` | Adding retries, backoff, idempotency, timeouts, circuit breakers, logging, metrics. |
| `documentation-writer` | Producing README/architecture/API docs and design-decision records. |
| `git-commit-writer` | Turning a change into Conventional-Commits messages. |

## Deliberate consolidations
To avoid overlapping descriptions (which degrade auto-invocation), these proposed skills
are folded in as checklists rather than shipped standalone:
- **Naming / Dead-code / DRY / SOLID / API-consistency / Logging / Error-handling / PR review** → `senior-code-reviewer`
- **Task decomposer / Progress tracker** → `implementation-planner` (+ the built-in TodoWrite)
- **Second opinion** → `adversarial-reviewer`
- **Dependency analyzer / Database reviewer** → `architecture-designer` + `rag-reviewer`
- **Embedding strategist** → `rag-reviewer` + `chunking-strategist`

Ask to split any of these back into its own skill if you want it to fire independently.

## Skill file format
Each skill is `<name>/SKILL.md` with YAML frontmatter (`name`, `description`) and a body.
The `description` is what Claude matches on — keep it specific and trigger-rich.
