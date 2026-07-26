"""
Data-bot ingestion pipeline.
Run once (or to re-ingest):  python ingest.py

What it does:
  1. Loads the 5 CSVs into a local SQLite database (databot.db)
  2. Parses Markdown and PDF contract/policy documents
  3. Chunks them by section and indexes them in a ChromaDB vector store
"""

import re
import sys
import shutil
from pathlib import Path

import pandas as pd
import chromadb
import pypdf

BASE_DIR = Path(__file__).parent           # Data-bot/
ROOT_DIR = BASE_DIR.parent                 # repo root
DATA_DIR = ROOT_DIR / "data"
DOCS_DIR = ROOT_DIR / "docs"
DB_PATH = BASE_DIR / "databot.db"
CHROMA_PATH = BASE_DIR / "chroma_db"

COLLECTION_NAME = "databot_docs"

REDIRECT_SENTINEL = "This contract is authored as a PDF"

# ── helpers ───────────────────────────────────────────────────────────────────

def normalize_booleans(df: pd.DataFrame) -> pd.DataFrame:
    """Convert 'True'/'False' string columns to SQLite 1/0 integers."""
    for col in df.columns:
        if df[col].dtype == object:
            unique = set(df[col].dropna().unique())
            if unique <= {"True", "False"}:
                df[col] = df[col].map({"True": 1, "False": 0})
    return df


def chunk_markdown(text: str, max_chunk: int = 900, overlap: int = 100) -> list[str]:
    """
    Split markdown by top-level headers (##).
    If a section exceeds max_chunk, slide a window over it.
    """
    sections = re.split(r"\n(?=#{1,3} )", text)
    chunks: list[str] = []
    for section in sections:
        section = section.strip()
        if len(section) < 60:
            continue
        if len(section) <= max_chunk:
            chunks.append(section)
        else:
            start = 0
            while start < len(section):
                end = min(start + max_chunk, len(section))
                chunks.append(section[start:end])
                start += max_chunk - overlap
    return chunks


def chunk_text(text: str, chunk_size: int = 900, overlap: int = 100) -> list[str]:
    """Fixed-size sliding-window chunker."""
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start += chunk_size - overlap
    return chunks


def extract_contract_id(stem: str) -> str:
    """'CTR-0010_polaris_consulting_msa' → 'CTR-0010'"""
    return stem.split("_")[0]

# ── step 1: structured data ───────────────────────────────────────────────────

def ingest_csvs() -> None:
    import sqlite3

    # Remove stale DB so we always start fresh
    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(DB_PATH)

    tables = {
        "departments": DATA_DIR / "departments.csv",
        "vendors": DATA_DIR / "vendors.csv",
        "contracts": DATA_DIR / "contracts.csv",
        "purchase_orders": DATA_DIR / "purchase_orders.csv",
        "invoices": DATA_DIR / "invoices.csv",
    }

    for table_name, csv_path in tables.items():
        df = pd.read_csv(csv_path)
        df = normalize_booleans(df)
        df.to_sql(table_name, conn, if_exists="replace", index=False)
        print(f"  ✓  {table_name:<20}  {len(df):>5} rows")

    conn.commit()
    conn.close()

# ── step 2: document embeddings ───────────────────────────────────────────────

def ingest_documents() -> None:
    # Wipe and recreate chroma collection for idempotency
    if CHROMA_PATH.exists():
        shutil.rmtree(CHROMA_PATH)

    client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    collection = client.create_collection(
        COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )

    documents: list[str] = []
    metadatas: list[dict] = []
    ids: list[str] = []

    def add_chunks(chunks: list[str], source: str, contract_id: str, doc_type: str) -> None:
        for i, chunk in enumerate(chunks):
            doc_id = f"{source}__{i}"
            if doc_id in ids:
                doc_id = f"{doc_id}__dup"
            documents.append(chunk)
            metadatas.append({
                "source": source,
                "contract_id": contract_id,
                "doc_type": doc_type,
                "chunk_index": i,
            })
            ids.append(doc_id)

    # ── contracts ────────────────────────────────────────────────────────────
    contracts_dir = DOCS_DIR / "contracts"

    # First pass: collect which contract IDs have PDFs (skip their .md stubs)
    pdf_contract_ids = {
        extract_contract_id(p.stem)
        for p in contracts_dir.glob("*.pdf")
    }

    for md_path in contracts_dir.glob("*.md"):
        content = md_path.read_text(encoding="utf-8")
        if REDIRECT_SENTINEL in content:
            continue  # handled by the PDF pass
        cid = extract_contract_id(md_path.stem)
        chunks = chunk_markdown(content)
        add_chunks(chunks, md_path.name, cid, "contract")
        print(f"  ✓  {md_path.name:<55}  {len(chunks):>3} chunks  (markdown)")

    for pdf_path in contracts_dir.glob("*.pdf"):
        cid = extract_contract_id(pdf_path.stem)
        try:
            reader = pypdf.PdfReader(pdf_path)
            pages_text = [page.extract_text() or "" for page in reader.pages]
            full_text = "\n\n".join(t for t in pages_text if t.strip())
            chunks = chunk_text(full_text)
            add_chunks(chunks, pdf_path.name, cid, "contract")
            print(f"  ✓  {pdf_path.name:<55}  {len(chunks):>3} chunks  (pdf)")
        except Exception as exc:
            print(f"  ⚠  {pdf_path.name}: {exc}", file=sys.stderr)

    # ── policies ─────────────────────────────────────────────────────────────
    for md_path in (DOCS_DIR / "policies").glob("*.md"):
        content = md_path.read_text(encoding="utf-8")
        chunks = chunk_markdown(content)
        add_chunks(chunks, md_path.name, "", "policy")
        print(f"  ✓  {md_path.name:<55}  {len(chunks):>3} chunks  (policy)")

    if documents:
        # Batch upsert in groups of 100 to avoid memory spikes
        batch = 100
        for start in range(0, len(documents), batch):
            collection.add(
                documents=documents[start : start + batch],
                metadatas=metadatas[start : start + batch],
                ids=ids[start : start + batch],
            )
        unique_sources = len({m["source"] for m in metadatas})
        print(f"\n  ✓  Indexed {len(documents)} chunks from {unique_sources} documents")
    else:
        print("  ⚠  No documents found to index.", file=sys.stderr)

# ── entrypoint ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n━━━ Data-bot Ingestion ━━━\n")

    print("Step 1 — Structured data → SQLite")
    ingest_csvs()

    print("\nStep 2 — Documents → ChromaDB")
    ingest_documents()

    print("\n✅  Ingestion complete.  Run: uvicorn main:app --reload\n")
