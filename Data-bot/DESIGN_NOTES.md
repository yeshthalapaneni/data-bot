# Data-bot — Design Notes

---

## 1. Architecture overview

```
Ingest (one-time)                 Runtime (per request)
────────────────────              ──────────────────────────────────────
CSVs ──► SQLite (5 tables)        User message
                                       │
Markdown ──┐                           ▼
           ├──► ChromaDB        FastAPI /api/chat
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
                                     + tool_calls log
                                     + sources list
                                            │
                                            ▼
                                     React chat UI
```

---

## 2. Database: SQLite instead of Postgres

**Why:** Zero setup — no server to install or start. SQLite handles ~3 800 rows with sub-millisecond query times. The bottleneck is always Claude, not the DB.

**Schema decisions:**
- Boolean columns (`auto_renew`, `preferred_status`) are normalised from the CSV strings `"True"/"False"` to SQLite integers `1/0` at ingest time, so SQL comparisons work naturally (`WHERE auto_renew = 1`).
- Dates are kept as ISO-8601 strings (`YYYY-MM-DD`), matching SQLite's `date()` function expectations.
- Foreign keys are present but not enforced with `PRAGMA foreign_keys` — the CSV data has some intentional orphans (invoices without a PO, POs without a contract).

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
- No emoji in answers — anomalies are flagged with the plain-text prefix `Anomaly:` instead.

**Tool-use loop:** Up to 12 rounds. For cross-source questions (e.g. "invoices with terms shorter than their contract"), Claude typically calls `query_database` twice (once for invoices, once for contracts) then synthesises the join.

---

## 5. API surface

```
POST /api/chat
  Body:  { message: string, history: [{role, content}] }
  Returns: { answer: string, tool_calls: [...], sources: [...] }

POST /api/chat/stream
  Same body, returns Server-Sent Events (tool_start / tool_end / text_delta / done)

GET /api/health
  Returns: { status: "ok", reference_date: "2026-04-21" }
```

Conversation history is passed from the frontend on every request and threaded into the messages array, giving the agent multi-turn memory without any server-side session state.

---

## 6. Frontend

Single-page React app (Vite + TypeScript + Tailwind CSS).

Notable UX choices:
- **Tool call drawer** — each assistant reply shows a collapsible "N tool calls" section revealing the exact SQL or search query used. This makes the agent's reasoning auditable.
- **Source pills** — `Database` and `Documents` pills indicate which store contributed to the answer.
- **Sidebar shortcuts** — 10 pre-seeded questions covering all four question tiers from the brief. Clicking one sends the full question immediately.
- **Error state** — if the API is unreachable, the assistant bubble shows an amber warning rather than silently failing.
- **Streaming** — `/api/chat/stream` gives token-by-token text plus live "querying database" / "searching documents" trace while the agent works.

---

## 7. Planted anomalies the agent can detect

The dataset includes intentional data quality issues:

| Anomaly | How to ask |
|---------|------------|
| Invoices with shorter payment terms than the contract | *"Find invoices whose payment terms differ from their contract"* |
| POs split to stay under approval thresholds | *"Are there split POs avoiding approval thresholds?"* |
| High spend vendors with no active contract | *"Vendors with >$50k YTD spend and no active contract?"* |
| Cumulative invoice spend exceeding the contract value cap | *"Flag contracts where invoice spend exceeded the cap"* |

---

## 8. Limitations

- **Currency normalisation:** amounts in EUR/GBP are not converted to USD before aggregation. The agent notes the currency but doesn't FX-convert.
- **Context window:** very long conversation histories could eventually exceed Claude's context limit. Production would use a sliding window or summary.
- **No auth / rate limiting** on the API — fine for local demo, not for production.
- **PDF extraction quality:** `pypdf` text extraction degrades on scanned or columnar PDFs. Three PDFs in this dataset extract cleanly.

---

## 9. What I'd do with more time

1. **Hybrid retrieval:** combine ChromaDB cosine similarity with BM25 keyword search (reciprocal rank fusion) to improve recall for exact term / contract-ID lookups.
2. **FX normalisation:** pull live or fixed EUR/GBP→USD rates at ingest time and store an `amount_usd` column on invoices and POs.
3. **Eval harness:** build a small golden-question set with expected answers and run it after each code change to catch regressions.
4. **Metadata filtering:** pass contract_id as a ChromaDB `where` filter when the user references a specific vendor or contract, to avoid cross-contamination from similar documents.
5. **Postgres + pgvector:** replace SQLite + ChromaDB with a single Postgres instance for production simplicity and better concurrency.
