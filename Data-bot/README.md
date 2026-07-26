# Data-bot — an agent sitting on top of your data

A conversational AI agent that answers natural-language procurement and finance questions for **Nimbus Retail Co.** It reasons across structured data (vendors, contracts, POs, invoices) and unstructured documents (contract files, policy docs), and always shows exactly which SQL query or document search it used.

---

## Architecture at a glance

```
User browser
    │  HTTP (Vite proxy → localhost:8000)
    ▼
React + Tailwind UI   (frontend/ — port 5173)
    │
    ▼
FastAPI (backend/main.py — port 8000)
    │
    ▼
Claude claude-sonnet-4-6 (agent.py)
    │
    ├── tool: query_database ──► SQLite  (databot.db)
    │                            5 tables, ~3 800 rows total
    │
    └── tool: search_documents ► ChromaDB (chroma_db/)
                                 ~18 documents chunked & embedded
                                 (all-MiniLM-L6-v2 via ONNX)
```

---

## Quick start

### Prerequisites

| Tool | Version |
|------|---------|
| Python | 3.11+ |
| Node.js | 18+ |
| An Anthropic API key | — |

### 1. Environment

```bash
cd Data-bot/backend
cp .env.example .env
# open .env and paste your ANTHROPIC_API_KEY
```

### 2. Backend

```bash
cd Data-bot/backend
pip install -r requirements.txt

# Load the CSVs into SQLite and embed the docs into ChromaDB.
# Only needs to run once (re-run to reset from scratch).
python ingest.py

uvicorn main:app --reload --port 8000
```

### 3. Frontend

```bash
cd Data-bot/frontend    # in a new terminal tab
npm install
npm run dev             # starts on http://localhost:5173
```

Open **http://localhost:5173** and start asking questions.

---

## What the agent can answer

| Tier | Example questions |
|------|-------------------|
| **Structured only** | "Top 10 vendors by YTD spend?" / "How many active contracts by type?" |
| **Document only** | "What are the auto-renewal terms for Orion Logistics?" / "What does the procurement policy say about PO splitting?" |
| **Cross-source** | "Which contracts auto-renew in the next 90 days, and what's the notice window?" / "Invoices with payment terms shorter than the contract?" |
| **Anomaly detection** | Split POs under approval thresholds · Spend with no contract · Contract cap breaches · Duplicate-looking invoices |

---

## Project layout

```
Data-bot/
├── backend/
│   ├── main.py            FastAPI app — POST /api/chat, GET /api/health
│   ├── agent.py           Claude tool-use loop
│   ├── ingest.py          CSV → SQLite + docs → ChromaDB
│   ├── db.py              SQLite connection helper
│   ├── tools/
│   │   ├── sql_tool.py    Safe SELECT executor
│   │   └── rag_tool.py    ChromaDB semantic search
│   └── requirements.txt
├── frontend/
│   ├── src/App.tsx        Full chat UI (single component)
│   ├── src/index.css      Tailwind base + scrollbar styles
│   └── (Vite + Tailwind config)
├── README.md
└── DESIGN_NOTES.md
```

---

## Re-ingesting from scratch

```bash
cd Data-bot/backend
python ingest.py   # deletes databot.db and chroma_db/, rebuilds both
```

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `ANTHROPIC_API_KEY` not found | Ensure `.env` is in `Data-bot/backend/` or export the var in your shell |
| `Document store not ready` | Run `python ingest.py` before starting the server |
| CORS error in browser | Make sure the API server is running on port 8000 |
| Slow first query after ingest | ChromaDB loads the embedding model on first search — subsequent queries are fast |
