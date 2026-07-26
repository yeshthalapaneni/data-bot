"""
Data-bot agent — Claude claude-sonnet-4-6 with two tools.

Exports:
  run_agent(message, history) -> dict          # synchronous, full response
  stream_agent_events(message, history)        # async generator → SSE events
"""

import asyncio
import json
import os
from functools import partial

import anthropic
from dotenv import load_dotenv

from tools.sql_tool import execute_sql
from tools.rag_tool import search_documents

load_dotenv()


def _get_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key
    try:
        import streamlit as st
        key = st.secrets.get("ANTHROPIC_API_KEY")
    except Exception:
        key = None
    if not key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Add it to Data-bot/.env locally, "
            "or under App settings -> Secrets on Streamlit Cloud."
        )
    return key


client = anthropic.Anthropic(api_key=_get_api_key())
MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = """You are Data-bot, an AI procurement and spend analytics agent sitting on top of Nimbus Retail Co.'s data.

== Reference date ==
Today is 2026-04-21. Use this when evaluating contract expiry, overdue invoices, or "last 12 months" windows.

== Your tools ==
• query_database  — run SQL SELECT queries against the structured database
• search_documents — semantic search over contract and policy documents

== Database schema ==
departments(department_id, name, cost_center_code, vp_name)

vendors(vendor_id, vendor_name, tax_id, country, category, onboarded_date,
        preferred_status, risk_rating, payment_terms_default, status)
  preferred_status / risk_rating: text; status: 'Active'|'Suspended'|'Inactive'

contracts(contract_id, vendor_id, contract_name, contract_type, start_date,
          end_date, auto_renew, notice_period_days, total_value_cap_usd,
          currency, payment_terms_days, status, document_path)
  auto_renew: INTEGER 1=yes 0=no; status: 'Active'|'Expired'|'Terminated'

purchase_orders(po_id, vendor_id, contract_id, department_id, po_date,
                line_description, total_amount, currency, status,
                requestor_name, approval_level)
  approval_level: 'Dept Head'|'VP'|'CFO'|'CEO'; status: 'Open'|'Received'|'Closed'|'Cancelled'

invoices(invoice_id, po_id, vendor_id, invoice_date, due_date, amount,
         currency, status, payment_terms_days, paid_date)
  status: 'Paid'|'Pending'|'Overdue'|'Disputed'

== SQL tips ==
- Dates are stored as TEXT 'YYYY-MM-DD'; use date() for comparisons.
- "Last 12 months": invoice_date >= date('2026-04-21','-12 months')
- "Next 90 days": end_date BETWEEN '2026-04-21' AND date('2026-04-21','+90 days')
- Year-to-date 2026: invoice_date >= '2026-01-01' AND invoice_date <= '2026-04-21'
- Most amounts are USD; a minority are EUR/GBP — note currency when aggregating.

== Anomalies to flag ==
• Invoices where payment_terms_days differs from the underlying contract's payment_terms_days
• POs from the same vendor on the same day whose amounts together cross an approval threshold
• Vendors with significant YTD spend but no active contract (policy requires contract > USD 25k/year)
• Cumulative invoice spend exceeding contracts.total_value_cap_usd

== Output style ==
- Be precise with numbers (commas, USD prefix).
- Use markdown tables for multi-row results.
- Cite source IDs (invoice_id, contract_id, po_id, document name).
- Use BOTH tools for cross-source questions.
- Flag anomalies with ⚠️.
"""

TOOLS = [
    {
        "name": "query_database",
        "description": (
            "Execute a read-only SQL SELECT query against the procurement database. "
            "Use for quantitative questions: spend totals, vendor lists, PO counts, "
            "contract dates, overdue invoices, approval levels, etc."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "sql": {"type": "string", "description": "A valid SQLite SELECT statement."}
            },
            "required": ["sql"],
        },
    },
    {
        "name": "search_documents",
        "description": (
            "Semantic search over contract and policy documents (Markdown + PDF). "
            "Use for contract clauses (auto-renewal, notice periods, payment terms, "
            "termination), and procurement / expense / vendor-risk policy questions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural-language search query."},
                "n_results": {"type": "integer", "description": "Number of chunks to retrieve (default 5).", "default": 5},
            },
            "required": ["query"],
        },
    },
]


def _call_claude(messages: list) -> object:
    """Synchronous Claude call — runs in a thread executor."""
    return client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        tools=TOOLS,
        messages=messages,
    )


# ── synchronous agent (kept for compatibility) ────────────────────────────────

def run_agent(message: str, history: list[dict]) -> dict:
    messages: list[dict] = history + [{"role": "user", "content": message}]
    tool_calls_log: list[dict] = []
    sources: set[str] = set()

    for _ in range(12):
        response = _call_claude(messages)

        if response.stop_reason == "end_turn":
            answer = " ".join(b.text for b in response.content if hasattr(b, "text"))
            return {"answer": answer.strip(), "tool_calls": tool_calls_log, "sources": sorted(sources)}

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                name, inp = block.name, dict(block.input)
                result = execute_sql(inp["sql"]) if name == "query_database" else search_documents(inp.get("query", ""), inp.get("n_results", 5))
                sources.add("Database" if name == "query_database" else "Documents")
                tool_calls_log.append({"tool": name, "input": inp, "result": result[:3000]})
                tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": result})
            messages.append({"role": "user", "content": tool_results})

    return {"answer": "Could not complete the request.", "tool_calls": tool_calls_log, "sources": sorted(sources)}


# ── streaming agent ───────────────────────────────────────────────────────────

async def stream_agent_events(message: str, history: list[dict]):
    """
    Async generator that yields SSE-formatted data lines.

    Event types:
      tool_start  — agent is about to call a tool
      tool_end    — tool call finished
      text_delta  — a word of the final answer
      done        — stream complete; includes full tool_calls + sources
      error       — something went wrong
    """
    loop = asyncio.get_running_loop()
    messages: list[dict] = history + [{"role": "user", "content": message}]
    tool_calls_log: list[dict] = []
    sources: set[str] = set()

    def _sse(payload: dict) -> str:
        return f"data: {json.dumps(payload)}\n\n"

    for _ in range(12):
        try:
            response = await loop.run_in_executor(None, partial(_call_claude, messages))
        except Exception as exc:
            yield _sse({"type": "error", "message": str(exc)})
            return

        if response.stop_reason == "end_turn":
            answer = " ".join(b.text for b in response.content if hasattr(b, "text"))
            words = answer.split(" ")
            for i, word in enumerate(words):
                yield _sse({"type": "text_delta", "text": word + (" " if i < len(words) - 1 else "")})
                await asyncio.sleep(0.016)  # ~60 words/sec
            yield _sse({"type": "done", "tool_calls": tool_calls_log, "sources": sorted(sources)})
            return

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []

            for block in response.content:
                if block.type != "tool_use":
                    continue

                name = block.name
                inp = dict(block.input)
                tool_id = block.id

                yield _sse({"type": "tool_start", "tool": name, "input": inp, "id": tool_id})

                try:
                    if name == "query_database":
                        result = await loop.run_in_executor(None, partial(execute_sql, inp.get("sql", "")))
                        sources.add("Database")
                    elif name == "search_documents":
                        result = await loop.run_in_executor(
                            None, partial(search_documents, inp.get("query", ""), inp.get("n_results", 5))
                        )
                        sources.add("Documents")
                    else:
                        result = f"Unknown tool: {name}"
                except Exception as exc:
                    result = f"Tool error: {exc}"

                tool_calls_log.append({"tool": name, "input": inp, "result": result[:3000]})
                yield _sse({"type": "tool_end", "tool": name, "id": tool_id})

                tool_results.append({"type": "tool_result", "tool_use_id": tool_id, "content": result})

            messages.append({"role": "user", "content": tool_results})
            continue

        break

    yield _sse({"type": "error", "message": "Agent loop exhausted without a final answer."})
