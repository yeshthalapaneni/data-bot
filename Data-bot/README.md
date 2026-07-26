# Data-bot — an agent sitting on top of your data

A single, simple chat app that answers natural-language procurement and finance questions for **Nimbus Retail Co.** — type or speak your question, and Data-bot reasons across structured data (vendors, contracts, POs, invoices) and unstructured documents (contracts, policies), citing what it used.

---

## Architecture at a glance

```
Streamlit UI (app.py)  — chat + 🎤 voice input
        │
        ▼
Claude claude-sonnet-4-6 (agent.py)
        │
        ├── tool: query_database ──► SQLite  (databot.db)
        │
        └── tool: search_documents ► ChromaDB (chroma_db/)
```

One process, one app, one URL.

---

## Quick start

```bash
cd Data-bot
cp .env.example .env
# open .env and paste your ANTHROPIC_API_KEY

pip install -r requirements.txt

# Load the CSVs into SQLite and embed the docs into ChromaDB (run once)
python ingest.py

streamlit run app.py
```

Open the local URL Streamlit prints and start asking questions — or click the 🎤 recorder and just ask out loud.

---

## What it can answer

| Tier | Example questions |
|------|-------------------|
| **Structured only** | "Top 10 vendors by YTD spend?" / "How many active contracts by type?" |
| **Document only** | "What are the auto-renewal terms for Orion Logistics?" / "What does the procurement policy say about PO splitting?" |
| **Cross-source** | "Which contracts auto-renew in the next 90 days, and what's the notice window?" |
| **Anomaly detection** | Split POs under approval thresholds · spend with no contract · contract cap breaches |

---

## Project layout

```
Data-bot/
├── app.py            Streamlit UI — chat + voice input
├── agent.py          Claude tool-use loop
├── ingest.py         CSV → SQLite + docs → ChromaDB
├── db.py             SQLite connection helper
├── tools/
│   ├── sql_tool.py   Safe SELECT executor
│   └── rag_tool.py   ChromaDB semantic search
├── requirements.txt
├── .env.example
└── DESIGN_NOTES.md
```

---

## Voice input

The 🎤 recorder uses Streamlit's built-in `st.audio_input`, transcribed with the free Google Web Speech API (no extra API key needed). For best results, ask a short, clear question.

---

## Re-ingesting from scratch

```bash
python ingest.py   # deletes databot.db and chroma_db/, rebuilds both
```

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `ANTHROPIC_API_KEY` not found | Make sure `.env` is in `Data-bot/` |
| `Document store not ready` | Run `python ingest.py` before starting the app |
| Voice input says "couldn't understand" | Speak clearly and check your mic permissions in the browser |
