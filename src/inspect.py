"""Stage inspection report — the observability payoff.

    python -m src.inspect

Prints per-stage artifact counts, a sample from each stage, and sanity checks
over the whole pipeline; exits non-zero if any hard check fails. Checks that
depend on not-yet-built stages (embeddings / vector store) are reported as
"pending" rather than failing, so inspect is meaningful both mid-build and after
a full build. (This module is ``src.inspect`` — namespaced under the package, so
it does not shadow the stdlib ``inspect``.)
"""

from __future__ import annotations

from dataclasses import dataclass

from src.observability import list_artifacts, load_artifact, stage_count
from src.pipeline import store as store_mod


@dataclass
class Check:
    name: str
    ok: bool
    detail: str


def _counts(base) -> dict:
    chunk_docs = list_artifacts("chunks", base=base)
    total_chunks = sum(len(load_artifact("chunks", d, base=base)) for d in chunk_docs)
    emb_docs = list_artifacts("embeddings", base=base)
    total_emb = sum(len(load_artifact("embeddings", d, base=base)) for d in emb_docs)
    vs = store_mod._vectorstore_dir(base)
    chroma = store_mod.ChromaVectorStore(persist_dir=vs).count() if any(vs.glob("*.sqlite3")) else None
    return {
        "raw": stage_count("raw", "txt", base=base),
        "cleaned": stage_count("cleaned", "txt", base=base),
        "metadata": stage_count("metadata", base=base),
        "sections": stage_count("sections", base=base),
        "chunk_files": len(chunk_docs),
        "chunks": total_chunks,
        "embeddings": total_emb,
        "chroma": chroma,
        "bm25": (vs / "bm25.json").exists(),
        "_chunk_docs": chunk_docs,
        "_emb_docs": set(emb_docs),
    }


def _checks(base, c: dict) -> list[Check]:
    out: list[Check] = []

    # 1. no XBRL survived into cleaned text
    bad = [d for d in list_artifacts("cleaned", "txt", base=base)
           if "us-gaap:" in load_artifact("cleaned", d, "txt", base=base)]
    out.append(Check("cleaned:no-xbrl", not bad,
                     f"{len(bad)} file(s) still contain 'us-gaap:'" if bad
                     else f"clean across {c['cleaned']} files"))

    # 2. every chunk has full metadata + non-empty embed_text
    miss_meta = miss_embed = 0
    for d in c["_chunk_docs"]:
        for ch in load_artifact("chunks", d, base=base):
            if not (ch.get("ticker") and ch.get("form") and ch.get("company")):
                miss_meta += 1
            if not ch.get("embed_text"):
                miss_embed += 1
    out.append(Check("chunks:full-metadata", miss_meta == 0,
                     f"{miss_meta} chunk(s) missing metadata" if miss_meta else f"all {c['chunks']} tagged"))
    out.append(Check("chunks:embed_text-set", miss_embed == 0,
                     f"{miss_embed} chunk(s) missing embed_text" if miss_embed else f"all {c['chunks']} enriched"))

    # 3. section spans are valid, contiguous, and cover the whole cleaned doc
    bad_sec = []
    for d in list_artifacts("sections", base=base):
        spans = load_artifact("sections", d, base=base)
        ok = (bool(spans) and spans[0]["start"] == 0
              and all(s["start"] <= s["end"] for s in spans)
              and all(spans[i]["end"] == spans[i + 1]["start"] for i in range(len(spans) - 1)))
        try:
            ok = ok and spans[-1]["end"] == len(load_artifact("cleaned", d, "txt", base=base))
        except FileNotFoundError:
            pass
        if not ok:
            bad_sec.append(d)
    out.append(Check("sections:valid-offsets", not bad_sec,
                     f"{len(bad_sec)} file(s) invalid" if bad_sec
                     else f"contiguous & covering across {c['sections']} files"))

    # 4. embeddings count == chunk count (pending until Stage 7 runs)
    if not c["_emb_docs"]:
        out.append(Check("embeddings==chunks", True, "pending — run embed"))
    else:
        mism = [d for d in c["_chunk_docs"]
                if len(load_artifact("chunks", d, base=base))
                != (len(load_artifact("embeddings", d, base=base)) if d in c["_emb_docs"] else 0)]
        out.append(Check("embeddings==chunks", not mism,
                         f"{c['embeddings']}/{c['chunks']} embedded; {len(mism)} doc mismatch" if mism
                         else f"{c['embeddings']} == {c['chunks']}"))

    # 5. Chroma collection size == chunk count (pending until Stage 8 runs)
    if c["chroma"] is None:
        out.append(Check("chroma==chunks", True, "pending — run store"))
    else:
        out.append(Check("chroma==chunks", c["chroma"] == c["chunks"], f"{c['chroma']} vs {c['chunks']}"))

    return out


def run_inspect(base=None) -> dict:
    counts = _counts(base)
    checks = _checks(base, counts)
    return {"counts": counts, "checks": checks, "ok": all(ch.ok for ch in checks)}


def _samples(base) -> list[str]:
    lines = []
    if (raw := list_artifacts("raw", "txt", base=base)):
        lines.append("  raw     : " + load_artifact("raw", raw[0], "txt", base=base)[:80].replace("\n", " "))
    if (cl := list_artifacts("cleaned", "txt", base=base)):
        lines.append("  cleaned : " + load_artifact("cleaned", cl[0], "txt", base=base)[:80].replace("\n", " "))
    if (md := list_artifacts("metadata", base=base)):
        m = load_artifact("metadata", md[0], base=base)
        lines.append(f"  metadata: {m.get('ticker')} {m.get('form')} {m.get('fiscal_period')} ({m.get('company')})")
    if (ck := list_artifacts("chunks", base=base)):
        c0 = load_artifact("chunks", ck[0], base=base)[0]
        lines.append(f"  chunk   : [{c0['section']}] {c0['text'][:60]!r}")
    return lines


def main(base=None) -> int:
    r = run_inspect(base=base)
    c = r["counts"]
    print("PE-RAG pipeline inspection")
    print(f"  counts: raw {c['raw']} | cleaned {c['cleaned']} | metadata {c['metadata']} | "
          f"sections {c['sections']} | chunks {c['chunks']} ({c['chunk_files']} files) | "
          f"embeddings {c['embeddings']} | chroma {c['chroma']} | bm25 {c['bm25']}")
    print("  samples:")
    for s in _samples(base):
        print(s)
    print("  checks:")
    for ch in r["checks"]:
        print(f"    [{'PASS' if ch.ok else 'FAIL'}] {ch.name:22} {ch.detail}")
    print("OK" if r["ok"] else "FAILED — see [FAIL] checks above")
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
