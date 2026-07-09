# Prompt Iteration Log

The required log of how the answer prompt evolved. Append an entry every time
`sec_rag/generation/prompt.py` changes (see `skills/prompt-template.md`). Newest first.

Format:
```
## vN — YYYY-MM-DD
Changed: <what changed in the prompt>
Why:     <the failure or goal that motivated it>
Effect:  <measured change on the eval set — faithfulness / numeric / recall / refusal>
```

---

<!-- No entries yet. The first entry is added when the Generation phase (implementation-plan
     Phase 4) builds prompt.py. Example of what the first real entry should look like:

## v1 — <date>
Changed: initial grounded, cite-or-refuse system prompt.
Why:     baseline; enforce "answer only from context", inline citations, numeric fidelity, refusal.
Effect:  eval baseline — faithfulness X, numeric-correctness Y, refusal-correctness Z.
-->
