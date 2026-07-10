"""Stage 16 — citation mapping (deterministic; no LLM).

Resolve the evidence ids the model referenced (``AnswerBody.citations`` plus any ``[E#]`` tokens
in the answer text) back to full ``Citation`` objects — ticker/company/form/period/section/
source_url — so the front-end can render clickable, traceable citations. Ids that don't resolve
to a retrieved evidence block are dropped (the model may only cite what it was given).
"""

from __future__ import annotations

import re

from src.schemas import AnswerBody, Citation, Evidence

_EID = re.compile(r"\bE(\d+)\b")


def inline_ids(body: AnswerBody) -> list[str]:
    """Evidence ids that appear in answer prose fields as ``[E#]`` tokens."""
    ids: list[str] = []
    text = " ".join([body.executive_summary, body.comparison, body.supporting_evidence,
                     body.limitations])
    for m in _EID.finditer(text):
        eid = f"E{m.group(1)}"
        if eid not in ids:
            ids.append(eid)
    return ids


def referenced_ids(body: AnswerBody) -> list[str]:
    """Evidence ids the answer cites: explicit ``citations`` first, then ``[E#]`` found in the text."""
    ids: list[str] = list(body.citations)
    for eid in inline_ids(body):
        if eid not in ids:
            ids.append(eid)
    return ids


def with_complete_source_list(body: AnswerBody, evidence: list[Evidence]) -> AnswerBody:
    """Return a body whose source list covers every final evidence block sent to generation.

    Inline ``[E#]`` citations remain the model's claim-level support. The structured
    ``citations`` field powers the UI/source list, so we deterministically append any final
    evidence ids that were in the prompt but omitted from the model's source list.
    """
    ids = referenced_ids(body)
    for e in evidence:
        if e.evidence_id not in ids:
            ids.append(e.evidence_id)
    return body.model_copy(update={"citations": ids})


def map_citations(body: AnswerBody, evidence: list[Evidence]) -> list[Citation]:
    """Map referenced evidence ids -> Citation objects (only ids present in ``evidence``)."""
    by_id = {e.evidence_id: e for e in evidence}
    out: list[Citation] = []
    seen: set[str] = set()
    for eid in referenced_ids(body):
        e = by_id.get(eid)
        if not e or eid in seen:
            continue
        seen.add(eid)
        c = e.chunk
        out.append(Citation(
            tag=e.tag, ticker=c.ticker, company=c.company, form=c.form,
            fiscal_period=c.fiscal_period or (f"FY{c.year}" if c.year else ""),
            section=c.section, source_url=c.source_url,
        ))
    return out
