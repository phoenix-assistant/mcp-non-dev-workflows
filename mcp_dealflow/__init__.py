"""MCP Deal Flow Server — Unified deal pipeline management."""

import json
import sys
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from shared import get_db, generate_id, now_iso, log_audit

DEFAULT_DB = str(Path.home() / ".mcp" / "dealflow.db")

app = Server("mcp-dealflow")
_db_path = DEFAULT_DB


def _conn():
    return get_db(_db_path)


def _init_db():
    conn = _conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id TEXT PRIMARY KEY, timestamp TEXT, action TEXT,
            entity_type TEXT, entity_id TEXT, actor TEXT, details TEXT
        );
        CREATE TABLE IF NOT EXISTS deals (
            id TEXT PRIMARY KEY, name TEXT, company TEXT, value REAL,
            stage TEXT DEFAULT 'prospecting', owner TEXT,
            contact_name TEXT, contact_email TEXT,
            notes TEXT DEFAULT '', tags TEXT DEFAULT '[]',
            stalled_flag INTEGER DEFAULT 0, stalled_reason TEXT DEFAULT '',
            created_at TEXT, updated_at TEXT, stage_entered_at TEXT
        );
        CREATE TABLE IF NOT EXISTS stage_history (
            id TEXT PRIMARY KEY, deal_id TEXT, from_stage TEXT, to_stage TEXT,
            changed_by TEXT, changed_at TEXT,
            FOREIGN KEY (deal_id) REFERENCES deals(id)
        );
        CREATE TABLE IF NOT EXISTS approval_requests (
            id TEXT PRIMARY KEY, deal_id TEXT, type TEXT, requested_by TEXT,
            approver TEXT, status TEXT DEFAULT 'pending',
            notes TEXT, created_at TEXT, resolved_at TEXT,
            FOREIGN KEY (deal_id) REFERENCES deals(id)
        );
    """)
    conn.close()

VALID_STAGES = ["prospecting", "qualification", "proposal", "negotiation", "closed_won", "closed_lost"]


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(name="track_deal_stage", description="Create a new deal or move an existing deal to a new stage.",
             inputSchema={"type": "object", "properties": {
                 "deal_id": {"type": "string", "description": "Existing deal ID (omit to create new)"},
                 "name": {"type": "string"}, "company": {"type": "string"},
                 "value": {"type": "number"}, "stage": {"type": "string", "enum": VALID_STAGES},
                 "owner": {"type": "string"}, "contact_name": {"type": "string"},
                 "contact_email": {"type": "string"}, "notes": {"type": "string"},
                 "actor": {"type": "string"}
             }, "required": ["stage", "actor"]}),
        Tool(name="flag_stalled_deal", description="Flag a deal as stalled with a reason, or list all stalled deals.",
             inputSchema={"type": "object", "properties": {
                 "deal_id": {"type": "string", "description": "Deal to flag (omit to list stalled)"},
                 "reason": {"type": "string"}, "actor": {"type": "string"}
             }}),
        Tool(name="generate_deal_summary", description="Generate pipeline summary with stats, stage breakdown, and at-risk deals.",
             inputSchema={"type": "object", "properties": {
                 "owner": {"type": "string", "description": "Filter by deal owner (optional)"},
                 "stage": {"type": "string", "description": "Filter by stage (optional)"}
             }}),
        Tool(name="create_approval_request", description="Create an approval request for a deal (discount, terms, etc).",
             inputSchema={"type": "object", "properties": {
                 "deal_id": {"type": "string"}, "type": {"type": "string", "description": "discount, terms, exception"},
                 "requested_by": {"type": "string"}, "approver": {"type": "string"},
                 "notes": {"type": "string"}
             }, "required": ["deal_id", "type", "requested_by", "approver"]}),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    _init_db()
    conn = _conn()
    try:
        if name == "track_deal_stage":
            return _track_deal_stage(conn, arguments)
        elif name == "flag_stalled_deal":
            return _flag_stalled_deal(conn, arguments)
        elif name == "generate_deal_summary":
            return _generate_deal_summary(conn, arguments)
        elif name == "create_approval_request":
            return _create_approval_request(conn, arguments)
        return [TextContent(type="text", text=f"Unknown tool: {name}")]
    finally:
        conn.close()


def _track_deal_stage(conn, args):
    ts = now_iso()
    deal_id = args.get("deal_id")
    if deal_id:
        row = conn.execute("SELECT * FROM deals WHERE id=?", (deal_id,)).fetchone()
        if not row:
            return [TextContent(type="text", text=f"Deal {deal_id} not found")]
        old_stage = row["stage"]
        conn.execute("UPDATE deals SET stage=?, updated_at=?, stage_entered_at=? WHERE id=?",
                     (args["stage"], ts, ts, deal_id))
        conn.execute("INSERT INTO stage_history VALUES (?,?,?,?,?,?)",
                     (generate_id(), deal_id, old_stage, args["stage"], args["actor"], ts))
        if args["stage"] not in ("closed_won", "closed_lost"):
            conn.execute("UPDATE deals SET stalled_flag=0, stalled_reason='' WHERE id=?", (deal_id,))
        log_audit(conn, "stage_change", "deal", deal_id, args["actor"],
                  {"from": old_stage, "to": args["stage"]})
        conn.commit()
        return [TextContent(type="text", text=json.dumps({"id": deal_id, "stage": args["stage"], "previous": old_stage}))]
    else:
        deal_id = generate_id()
        conn.execute("""INSERT INTO deals (id,name,company,value,stage,owner,contact_name,contact_email,notes,tags,created_at,updated_at,stage_entered_at)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                     (deal_id, args.get("name", ""), args.get("company", ""), args.get("value", 0),
                      args["stage"], args.get("owner", ""), args.get("contact_name", ""),
                      args.get("contact_email", ""), args.get("notes", ""), "[]", ts, ts, ts))
        log_audit(conn, "create_deal", "deal", deal_id, args["actor"], {"stage": args["stage"]})
        conn.commit()
        return [TextContent(type="text", text=json.dumps({"id": deal_id, "status": "created", "stage": args["stage"]}))]


def _flag_stalled_deal(conn, args):
    deal_id = args.get("deal_id")
    if not deal_id:
        rows = conn.execute("SELECT id, name, company, stage, stalled_reason, value FROM deals WHERE stalled_flag=1").fetchall()
        return [TextContent(type="text", text=json.dumps({"stalled_deals": [dict(r) for r in rows], "count": len(rows)}))]
    conn.execute("UPDATE deals SET stalled_flag=1, stalled_reason=?, updated_at=? WHERE id=?",
                 (args.get("reason", "No reason provided"), now_iso(), deal_id))
    log_audit(conn, "flag_stalled", "deal", deal_id, args.get("actor", "system"), {"reason": args.get("reason", "")})
    conn.commit()
    return [TextContent(type="text", text=json.dumps({"id": deal_id, "stalled": True}))]


def _generate_deal_summary(conn, args):
    query = "SELECT * FROM deals WHERE 1=1"
    params = []
    if args.get("owner"):
        query += " AND owner=?"
        params.append(args["owner"])
    if args.get("stage"):
        query += " AND stage=?"
        params.append(args["stage"])
    rows = conn.execute(query, params).fetchall()
    deals = [dict(r) for r in rows]
    by_stage = {}
    total_value = 0
    stalled_count = 0
    for d in deals:
        by_stage.setdefault(d["stage"], {"count": 0, "value": 0})
        by_stage[d["stage"]]["count"] += 1
        by_stage[d["stage"]]["value"] += d["value"] or 0
        total_value += d["value"] or 0
        if d["stalled_flag"]:
            stalled_count += 1
    return [TextContent(type="text", text=json.dumps({
        "total_deals": len(deals), "total_pipeline_value": total_value,
        "by_stage": by_stage, "stalled_count": stalled_count,
        "deals": deals[:20]
    }, indent=2))]


def _create_approval_request(conn, args):
    rid = generate_id()
    ts = now_iso()
    conn.execute("INSERT INTO approval_requests VALUES (?,?,?,?,?,?,?,?,?)",
                 (rid, args["deal_id"], args["type"], args["requested_by"],
                  args["approver"], "pending", args.get("notes", ""), ts, ""))
    log_audit(conn, "create_approval", "approval_request", rid, args["requested_by"],
              {"deal_id": args["deal_id"], "type": args["type"]})
    conn.commit()
    return [TextContent(type="text", text=json.dumps({"id": rid, "status": "pending", "approver": args["approver"]}))]


def main():
    import asyncio
    _init_db()
    asyncio.run(_run())


async def _run():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    main()
