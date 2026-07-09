# Skill: frontend-streamlit

**Purpose.** The demo front-end — a required deliverable. A clean input field for a business
question, the grounded answer, its sources, the retrieved chunks (for transparency), and
latency/cost. Built for a live client-style demo.

**When to invoke.** Work in `app.py`.

## How to do it
1. **Input.** A single `st.text_input`/`st.text_area` for the business question + a "Run" button, and
   a couple of example questions the demo can click.
2. **Answer.** Render the grounded answer as markdown (it contains inline citation tags).
3. **Sources.** Show the cited filings as a list/table with a link to each `source_url`
   (ticker · form · period · section).
4. **Transparency panel.** An expander showing the retrieved chunks and their scores — this sells the
   "grounded, not guessed" story to the client.
5. **Telemetry.** Show end-to-end latency and token/cost usage (`Answer.usage`) — proves the
   single-call design and its cost.
6. **Cache the pipeline.** Load the vector store / embedder once with `@st.cache_resource`; never
   re-index on every keystroke.
7. **Secrets.** Read `ANTHROPIC_API_KEY` from env / `.env`. Never render or log it.

## Bad example
```python
# BAD: rebuilds the whole index on every run, shows answer only, leaks nothing traceable
q = st.text_input("Question")
if st.button("Go"):
    build_index()                       # re-ingests the corpus on every click (minutes, $$$)
    st.write(answer(q).answer)          # no sources, no chunks, no latency/cost
```

## Good example
```python
import streamlit as st, time
from sec_rag.generation.answer import answer

@st.cache_resource
def pipeline(): return load_pipeline()      # store + embedder loaded once

st.title("The-RAG — SEC Filings Q&A")
q = st.text_area("Business question", placeholder="Compare risk factors: Apple, Tesla, JPMorgan")
if st.button("Answer") and q:
    t0 = time.perf_counter()
    res = answer(q)                          # the single-call pipeline
    st.markdown(res.answer)
    st.subheader("Sources")
    for c in res.sources:
        st.markdown(f"- [{c['tag']}]({c['url']})")
    with st.expander("Retrieved context"):
        for r in res.retrieved: st.caption(f"{r.tag}  score={r.score:.3f}"); st.text(r.text[:800])
    st.caption(f"⏱ {time.perf_counter()-t0:.1f}s · {res.usage['input_tokens']}+"
               f"{res.usage['output_tokens']} tok")
```

## Failure modes seen
- Re-indexing inside the request path → multi-minute clicks, runaway cost.
- Answer shown with no sources/chunks → the demo can't defend "grounded."
- API key printed in the UI or logs.
- Blocking UI with no spinner on a slow call → looks frozen in the demo.

## MUST NOT
- MUST NOT build/refresh the index inside the front-end request path.
- MUST NOT display or log the API key.
- MUST NOT show an answer without its sources and retrieved context.
- MUST NOT make a second answer-generating LLM call from the UI (single-call rule).
