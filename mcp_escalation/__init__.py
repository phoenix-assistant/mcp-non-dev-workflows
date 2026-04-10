"""MCP Escalation Server — Smart support routing with SLA tracking."""

import json
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

import yaml
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from shared import get_db, generate_id, now_iso, log_audit

DEFAULT_DB = str(Path.home() / ".mcp" / "escalation.db")
DEFAULT_CONFIG = str(Path(__file__).parent / "routing_rules.yaml")

app = Server("mcp-escalation")
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
        CREATE TABLE IF NOT EXISTS escalations (
            id TEXT PRIMARY KEY, title TEXT, description TEXT,
            severity TEXT DEFAULT 'medium', category TEXT,
            source TEXT, customer_id TEXT, customer_name TEXT,
            status TEXT DEFAULT 'open', assigned_team TEXT, assigned_agent TEXT,
            sla_deadline TEXT, sla_breached INTEGER DEFAULT 0,
            context TEXT DEFAULT '{}', resolution TEXT DEFAULT '',
            created_at TEXT, updated_at TEXT, resolved_at TEXT
        );
        CREATE TABLE IF NOT EXISTS ticket_history (
            id TEXT PRIMARY KEY, escalation_id TEXT, action TEXT,
            from_value TEXT, to_value TEXT, actor TEXT, timestamp TEXT,
            FOREIGN KEY (escalation_id) REFERENCES escalations(id)
        );
    """)
    conn.close()


def _load_rules(config_path: str | None = None) -> dict:
    path = Path(config_path or DEFAULT_CONFIG)
    if path.exists():
        with open(path) as f:
            return yaml.safe_load(f) or {}
    return _default_rules()


def _default_rules():
    return {
        "routing": {
            "billing": {"team": "finance-support", "sla_hours": 24},
            "technical": {"team": "engineering", "sla_hours": 4},
            "security": {"team": "security-ops", "sla_hours": 1},
            "account": {"team": "account-management", "sla_hours": 48},
            "general": {"team": "general-support", "sla_hours": 24},
        },
        "severity_multiplier": {
            "critical": 0.25, "high": 0.5, "medium": 1.0, "low": 2.0
        }
    }


def _calculate_sla(category: str, severity: str, rules: dict) -> str:
    route = rules.get("routing", {}).get(category, rules.get("routing", {}).get("general", {"sla_hours": 24}))
    mult = rules.get("severity_multiplier", {}).get(severity, 1.0)
    hours = route["sla_hours"] * mult
    deadline = datetime.now(timezone.utc) + timedelta(hours=hours)
    return deadline.isoformat()


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(name="create_escalation", description="Create a new support escalation with automatic routing.",
             inputSchema={"type": "object", "properties": {
                 "title": {"type": "string"}, "description": {"type": "string"},
                 "severity": {"type": "string", "enum": ["critical", "high", "medium", "low"]},
                 "category": {"type": "string", "description": "billing, technical, security, account, general"},
                 "source": {"type": "string", "description": "Origin: email, chat, phone, api"},
                 "customer_id": {"type": "string"}, "customer_name": {"type": "string"},
                 "actor": {"type": "string"}
             }, "required": ["title", "description", "severity", "category", "actor"]}),
        Tool(name="route_ticket", description="Route or re-route an escalation to a specific team or agent.",
             inputSchema={"type": "object", "properties": {
                 "escalation_id": {"type": "string"}, "team": {"type": "string"},
                 "agent": {"type": "string"}, "reason": {"type": "string"}, "actor": {"type": "string"}
             }, "required": ["escalation_id", "actor"]}),
        Tool(name="track_sla", description="Check SLA status for an escalation or get all breached/at-risk tickets.",
             inputSchema={"type": "object", "properties": {
                 "escalation_id": {"type": "string", "description": "Specific ticket (omit for overview)"},
                 "include_at_risk": {"type": "boolean", "description": "Include tickets within 25% of SLA deadline", "default": True}
             }}),
        Tool(name="auto_gather_context", description="Automatically gather context for an escalation from related tickets and history.",
             inputSchema={"type": "object", "properties": {
                 "escalation_id": {"type": "string"}, "customer_id": {"type": "string", "description": "Look up by customer instead"}
             }}),
        Tool(name="resolve_escalation", description="Resolve an escalation with a resolution note.",
             inputSchema={"type": "object", "properties": {
                 "escalation_id": {"type": "string"}, "resolution": {"type": "string"}, "actor": {"type": "string"}
             }, "required": ["escalation_id", "resolution", "actor"]}),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    _init_db()
    conn = _conn()
    try:
        if name == "create_escalation":
            return _create_escalation(conn, arguments)
        elif name == "route_ticket":
            return _route_ticket(conn, arguments)
        elif name == "track_sla":
            return _track_sla(conn, arguments)
        elif name == "auto_gather_context":
            return _auto_gather_context(conn, arguments)
        elif name == "resolve_escalation":
            return _resolve_escalation(conn, arguments)
        return [TextContent(type="text", text=f"Unknown tool: {name}")]
    finally:
        conn.close()


def _create_escalation(conn, args):
    eid = generate_id()
    ts = now_iso()
    rules = _load_rules()
    category = args["category"]
    severity = args["severity"]
    sla = _calculate_sla(category, severity, rules)
    team = rules.get("routing", {}).get(category, {}).get("team", "general-support")
    conn.execute("""INSERT INTO escalations (id,title,description,severity,category,source,customer_id,customer_name,
                    status,assigned_team,assigned_agent,sla_deadline,context,created_at,updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                 (eid, args["title"], args["description"], severity, category,
                  args.get("source", ""), args.get("customer_id", ""), args.get("customer_name", ""),
                  "open", team, "", sla, "{}", ts, ts))
    log_audit(conn, "create_escalation", "escalation", eid, args["actor"],
              {"severity": severity, "category": category, "team": team})
    conn.commit()
    return [TextContent(type="text", text=json.dumps({
        "id": eid, "status": "open", "assigned_team": team, "sla_deadline": sla, "severity": severity
    }))]


def _route_ticket(conn, args):
    eid = args["escalation_id"]
    ts = now_iso()
    row = conn.execute("SELECT assigned_team, assigned_agent FROM escalations WHERE id=?", (eid,)).fetchone()
    if not row:
        return [TextContent(type="text", text=f"Escalation {eid} not found")]
    updates = []
    params = []
    if args.get("team"):
        updates.append("assigned_team=?")
        params.append(args["team"])
    if args.get("agent"):
        updates.append("assigned_agent=?")
        params.append(args["agent"])
    updates.append("updated_at=?")
    params.append(ts)
    params.append(eid)
    conn.execute(f"UPDATE escalations SET {','.join(updates)} WHERE id=?", params)
    conn.execute("INSERT INTO ticket_history VALUES (?,?,?,?,?,?,?)",
                 (generate_id(), eid, "route", row["assigned_team"], args.get("team", row["assigned_team"]),
                  args["actor"], ts))
    log_audit(conn, "route_ticket", "escalation", eid, args["actor"],
              {"team": args.get("team"), "agent": args.get("agent"), "reason": args.get("reason", "")})
    conn.commit()
    return [TextContent(type="text", text=json.dumps({"id": eid, "routed_to": args.get("team"), "agent": args.get("agent")}))]


def _track_sla(conn, args):
    now = datetime.now(timezone.utc)
    if args.get("escalation_id"):
        row = conn.execute("SELECT * FROM escalations WHERE id=?", (args["escalation_id"],)).fetchone()
        if not row:
            return [TextContent(type="text", text="Not found")]
        d = dict(row)
        if d["sla_deadline"]:
            deadline = datetime.fromisoformat(d["sla_deadline"])
            d["sla_remaining_hours"] = round((deadline - now).total_seconds() / 3600, 1)
            d["sla_breached"] = now > deadline
        return [TextContent(type="text", text=json.dumps(d, indent=2))]
    # Overview
    rows = conn.execute("SELECT * FROM escalations WHERE status NOT IN ('resolved','closed')").fetchall()
    breached = []
    at_risk = []
    healthy = []
    for r in rows:
        d = dict(r)
        if d["sla_deadline"]:
            deadline = datetime.fromisoformat(d["sla_deadline"])
            remaining = (deadline - now).total_seconds() / 3600
            d["sla_remaining_hours"] = round(remaining, 1)
            if remaining < 0:
                d["sla_breached"] = True
                breached.append(d)
            elif remaining < (deadline - datetime.fromisoformat(d["created_at"])).total_seconds() / 3600 * 0.25:
                at_risk.append(d)
            else:
                healthy.append(d)
    result = {"breached": breached, "at_risk": at_risk if args.get("include_at_risk", True) else [],
              "healthy_count": len(healthy), "total_open": len(rows)}
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


def _auto_gather_context(conn, args):
    context = {"related_tickets": [], "customer_history": [], "audit_trail": []}
    eid = args.get("escalation_id")
    cid = args.get("customer_id")
    if eid:
        row = conn.execute("SELECT * FROM escalations WHERE id=?", (eid,)).fetchone()
        if row:
            cid = cid or row["customer_id"]
            history = conn.execute("SELECT * FROM ticket_history WHERE escalation_id=? ORDER BY timestamp DESC LIMIT 20",
                                   (eid,)).fetchall()
            context["audit_trail"] = [dict(h) for h in history]
    if cid:
        related = conn.execute("SELECT id,title,severity,status,created_at FROM escalations WHERE customer_id=? ORDER BY created_at DESC LIMIT 10",
                               (cid,)).fetchall()
        context["customer_history"] = [dict(r) for r in related]
        context["related_tickets"] = [dict(r) for r in related if r["status"] in ("open", "in_progress")]
        context["customer_ticket_count"] = len(related)
    return [TextContent(type="text", text=json.dumps(context, indent=2))]


def _resolve_escalation(conn, args):
    eid = args["escalation_id"]
    ts = now_iso()
    conn.execute("UPDATE escalations SET status='resolved', resolution=?, resolved_at=?, updated_at=? WHERE id=?",
                 (args["resolution"], ts, ts, eid))
    log_audit(conn, "resolve", "escalation", eid, args["actor"], {"resolution": args["resolution"]})
    conn.commit()
    return [TextContent(type="text", text=json.dumps({"id": eid, "status": "resolved", "resolved_at": ts}))]


def main():
    import asyncio
    _init_db()
    asyncio.run(_run())


async def _run():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    main()
