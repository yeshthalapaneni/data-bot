# Data-bot — Design Notes

---

## 1. Architecture overview

```
Ingest (one-time)                 Runtime (per request)
────────────────────              ──────────────────────────────────────
CSVs ──► SQLite (5 tables)        User question (typed or 🎤 spoken)
                                       │
Markdown ──┐                           ▼
           ├──► ChromaDB        Streamlit app (app.py)
PDF ───────┘    (chunks +              │
                embeddings)            ▼
                                  Claude claude-sonnet-4-6
                                  (tool-use loop, up to 12 rounds)
                                   │                │
                                   ▼                ▼
                             query_database    search_documents
                             (sql_tool.py)    (rag_tool.py)
                                   │                │
                                   ▼                ▼
                                SQLite          ChromaDB
                                   │                │
                                   └────────┬───────┘
                                            ▼
                                     Synthesized answer
                                            │
                                            ▼
                                    Streamlit chat UI
```

One process, one deploy target — no separate frontend/backend to run or host.

---

## 2. Database: SQLite instead of Postgres

**Why:** Zero setup — no server to install or start. SQLite handles ~3 800 rows with sub-millisecond query times. The bottleneck is always Claude, not the DB.

**Schema decisions:**
- Boolean columns (`auto_renew`, `preferred_status`) are normalised from the CSV strings `"True"/"False"` to SQLite integers `1/0` at ingest time, so SQL comparisons work naturally (`WHERE auto_renew = 1`).
- Dates are kept as ISO-8601 strings (`YYYY-MM-DD`), matching SQLite's `date()` function expectations.
- Foreign keys are present but not enforced — the CSV data has some intentional orphans (invoices without a PO, POs without a contract).

---

## 3. Document retrieval: ChromaDB

**Why:** Embedded vector store — no separate service to run. ChromaDB uses `all-MiniLM-L6-v2` (ONNX runtime, ships with the package) so there's no API call for embeddings and no cold-start latency after the first query.

**Chunking strategy:**

| Document type | Strategy | Chunk size |
|---------------|----------|------------|
| Markdown contracts/policies | Split on `## / ###` headers first; slide window if section > 900 chars | ~900 chars, 100 overlap |
| PDF contracts | Fixed sliding window over concatenated page text | ~900 chars, 100 overlap |

Section-based chunking for Markdown preserves semantic boundaries (e.g. the "Renewal" clause stays in one chunk), which improves retrieval precision for clause-specific questions.

**Metadata stored per chunk:** `source` (filename), `contract_id`, `doc_type` (`contract` / `policy`), `chunk_index`. This lets the agent cite the exact source document in its answer.

---

## 4. Agent design: Claude with native tool use

**Model:** `claude-sonnet-4-6` — best balance of reasoning depth and speed for this task.

**Tools:**

| Tool | When Claude uses it |
|------|---------------------|
| `query_database` | Any quantitative question: spend totals, counts, date ranges, approval levels, PO lists, vendor status |
| `search_documents` | Contract clauses, policy rules, termination terms, auto-renewal language |

**Key prompt choices:**
- Reference date (`2026-04-21`) is baked into the system prompt so date arithmetic works without hardcoding.
- SQL schema is provided verbatim so Claude writes correct column/table names.
- Boolean storage format (`1/0`) and date format (`'YYYY-MM-DD'`) are called out explicitly.
- Anomaly categories are enumerated (split POs, payment-term mismatches, spend over cap, no-contract spend) so Claude proactively surfaces them even for general questions.

**Tool-use loop:** Up to 12 rounds. For cross-source questions (e.g. "invoices with terms shorter than their contract"), Claude typically calls `query_database` twice (once for invoices, once for contracts) then synthesises the join.

---

## 5. Interface: Streamlit, deliberately simple

A single chat screen — a message list, a text box, and a 🎤 recorder. No dashboards, no sidebars, no configuration.

- **Voice input:** `st.audio_input` captures a WAV clip in-browser; it's transcribed with the free Google Web Speech API (`SpeechRecognition`) and sent to the agent exactly like a typed question. No extra API key required.
- **Session-only history:** conversation state lives in `st.session_state` — no server-side persistence, matching the demo/MVP scope.
- **No streaming:** Streamlit re-runs the whole script per interaction, so the answer renders once it's ready rather than token-by-token. Trades perceived latency for simplicity.

---

## 6. Planted anomalies the agent can detect

The dataset includes intentional data quality issues:

| Anomaly | How to ask |
|---------|------------|
| Invoices with shorter payment terms than the contract | *"Find invoices whose payment terms differ from their contract"* |
| POs split to stay under approval thresholds | *"Are there split POs avoiding approval thresholds?"* |
| High spend vendors with no active contract | *"Vendors with >$50k YTD spend and no active contract?"* |
| Cumulative invoice spend exceeding the contract value cap | *"Flag contracts where invoice spend exceeded the cap"* |

---

## 7. Limitations

- **Currency normalisation:** amounts in EUR/GBP are not converted to USD before aggregation.
- **No streaming:** long answers have a perceived delay of 3–8 seconds.
- **Voice accuracy:** Google Web Speech API is free and keyless but less accurate than a paid transcription model on noisy audio.
- **No auth / rate limiting** — fine for a demo, not for production.
- **PDF extraction quality:** `pypdf` text extraction degrades on scanned or columnar PDFs.

---

## 8. What I'd do with more time

1. **Hybrid retrieval:** combine ChromaDB cosine similarity with BM25 keyword search for better exact-term/contract-ID recall.
2. **Streaming responses:** token-by-token rendering for faster perceived latency.
3. **FX normalisation:** store a computed `amount_usd` column at ingest time.
4. **Eval harness:** a golden-question set run after each change to catch regressions.
5. **Better STT:** swap Google Web Speech for a paid transcription API for noisier environments.
