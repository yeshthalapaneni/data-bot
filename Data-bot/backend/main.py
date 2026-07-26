"""FastAPI entrypoint.  Run: uvicorn main:app --reload --port 8000"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import uvicorn

from db import get_connection
from agent import run_agent, stream_agent_events

app = FastAPI(title="Data-bot API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── startup warmup ─────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    """Preload ChromaDB embedding model so the first query isn't slow."""
    import asyncio
    loop = asyncio.get_running_loop()
    try:
        from tools.rag_tool import _get_collection
        await loop.run_in_executor(None, _get_collection)
        print("✓ ChromaDB warmed up")
    except Exception as exc:
        print(f"⚠ ChromaDB warmup failed: {exc}")


# ── models ────────────────────────────────────────────────────────────────────

class HistoryMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[HistoryMessage] = []


# ── endpoints ─────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "Data-bot API", "reference_date": "2026-04-21"}


@app.get("/api/stats")
async def stats():
    """Dashboard KPI counts fetched on welcome screen load."""
    conn = get_connection()
    try:
        active_vendors = conn.execute(
            "SELECT COUNT(*) FROM vendors WHERE status = 'Active'"
        ).fetchone()[0]

        active_contracts = conn.execute(
            "SELECT COUNT(*) FROM contracts WHERE status = 'Active'"
        ).fetchone()[0]

        ytd_spend = conn.execute(
            """SELECT COALESCE(SUM(amount), 0) FROM invoices
               WHERE invoice_date >= '2026-01-01'
                 AND invoice_date <= '2026-04-21'
                 AND currency = 'USD'"""
        ).fetchone()[0]

        open_pos = conn.execute(
            "SELECT COUNT(*) FROM purchase_orders WHERE status = 'Open'"
        ).fetchone()[0]

        anomaly_count = conn.execute(
            """SELECT COUNT(*) FROM (
                 SELECT i.invoice_id FROM invoices i
                 JOIN purchase_orders p ON i.po_id = p.po_id
                 JOIN contracts c ON p.contract_id = c.contract_id
                 WHERE i.payment_terms_days < c.payment_terms_days
               )"""
        ).fetchone()[0]

        return {
            "active_vendors": int(active_vendors),
            "active_contracts": int(active_contracts),
            "ytd_spend": float(ytd_spend),
            "open_pos": int(open_pos),
            "anomalies": int(anomaly_count),
        }
    finally:
        conn.close()


@app.post("/api/chat")
async def chat(req: ChatRequest):
    """Synchronous endpoint (kept for compatibility)."""
    try:
        history = [{"role": m.role, "content": m.content} for m in req.history]
        result = run_agent(req.message, history)
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    """SSE streaming endpoint — yields tool events + text deltas in real time."""
    history = [{"role": m.role, "content": m.content} for m in req.history]

    return StreamingResponse(
        stream_agent_events(req.message, history),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
