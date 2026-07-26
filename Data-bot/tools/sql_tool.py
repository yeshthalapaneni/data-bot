import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from db import get_connection

MAX_ROWS = 200


def execute_sql(sql: str) -> str:
    """Execute a read-only SQL SELECT and return results as a JSON string."""
    stripped = sql.strip()
    if not stripped.upper().startswith("SELECT"):
        return "Error: only SELECT queries are permitted."

    conn = get_connection()
    try:
        cursor = conn.execute(stripped)
        rows = cursor.fetchmany(MAX_ROWS)
        columns = [d[0] for d in cursor.description]

        if not rows:
            return "Query returned no rows."

        results = [dict(zip(columns, row)) for row in rows]
        overflow = ""
        if len(rows) == MAX_ROWS:
            overflow = f"\n[Note: results capped at {MAX_ROWS} rows]"
        return json.dumps(results, indent=2, default=str) + overflow

    except sqlite3.Error as exc:
        return f"SQL error: {exc}"
    finally:
        conn.close()
