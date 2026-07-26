from __future__ import annotations

from pathlib import Path
import chromadb

CHROMA_PATH = Path(__file__).parent.parent / "chroma_db"
COLLECTION_NAME = "databot_docs"

_client = None
_collection = None


def _get_collection():
    global _client, _collection
    if _collection is None:
        _client = chromadb.PersistentClient(path=str(CHROMA_PATH))
        _collection = _client.get_collection(COLLECTION_NAME)
    return _collection


def search_documents(query: str, n_results: int = 5) -> str:
    """Semantic search over contract and policy documents."""
    try:
        collection = _get_collection()
    except Exception as exc:
        return f"Document store not ready: {exc}. Run ingest.py first."

    results = collection.query(
        query_texts=[query],
        n_results=min(n_results, 10),
        include=["documents", "metadatas", "distances"],
    )

    docs = results["documents"][0]
    metas = results["metadatas"][0]
    dists = results["distances"][0]

    if not docs:
        return "No relevant documents found."

    output_parts = []
    for i, (doc, meta, dist) in enumerate(zip(docs, metas, dists)):
        source = meta.get("source", "unknown")
        doc_type = meta.get("doc_type", "")
        contract_id = meta.get("contract_id", "")
        relevance = round((1 - dist) * 100, 1)

        header = f"[{i+1}] {source}"
        if contract_id:
            header += f" | Contract: {contract_id}"
        header += f" | Type: {doc_type} | Relevance: {relevance}%"
        output_parts.append(f"{header}\n{doc}")

    return "\n\n---\n\n".join(output_parts)
