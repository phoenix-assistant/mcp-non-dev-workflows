"""MCP Compliance Server — SOC2, HIPAA, GDPR checklist automation with audit trails."""

import json
import sys
from pathlib import Path

import yaml
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from shared import get_db, generate_id, now_iso, log_audit

DEFAULT_DB = str(Path.home() / ".mcp" / "compliance.db")
DEFAULT_CONFIG = str(Path(__file__).parent / "frameworks.yaml")

app = Server("mcp-compliance")
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
        CREATE TABLE IF NOT EXISTS compliance_items (
            id TEXT PRIMARY KEY, framework TEXT, category TEXT,
            control_id TEXT, title TEXT, status TEXT DEFAULT 'not_started',
            assignee TEXT, due_date TEXT, evidence_ids TEXT DEFAULT '[]',
            created_at TEXT, updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS evidence (
            id TEXT PRIMARY KEY, compliance_item_id TEXT,
            title TEXT, description TEXT, file_path TEXT,
            collected_by TEXT, created_at TEXT,
            FOREIGN KEY (compliance_item_id) REFERENCES compliance_items(id)
        );
        CREATE TABLE IF NOT EXISTS reviews (
            id TEXT PRIMARY KEY, framework TEXT,
            scheduled_date TEXT, reviewer TEXT, status TEXT DEFAULT 'scheduled',
            notes TEXT, created_at TEXT
        );
    """)
    conn.close()


def _load_frameworks(config_path: str | None = None) -> dict:
    path = Path(config_path or DEFAULT_CONFIG)
    if path.exists():
        with open(path) as f:
            return yaml.safe_load(f) or {}
    return {}


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(name="check_compliance_status", description="Check compliance status for a framework (SOC2/HIPAA/GDPR) or all frameworks. Returns control items and their completion percentages.",
             inputSchema={"type": "object", "properties": {"framework": {"type": "string", "description": "Framework name: SOC2, HIPAA, GDPR, or 'all'", "default": "all"}, "status_filter": {"type": "string", "description": "Filter by status: not_started, in_progress, compliant, non_compliant"}}}),
        Tool(name="create_audit_evidence", description="Create and attach audit evidence to a compliance control item.",
             inputSchema={"type": "object", "properties": {"compliance_item_id": {"type": "string", "description": "ID of the compliance item"}, "title": {"type": "string"}, "description": {"type": "string"}, "file_path": {"type": "string", "description": "Path to evidence file (optional)"}, "collected_by": {"type": "string"}}, "required": ["compliance_item_id", "title", "description", "collected_by"]}),
        Tool(name="generate_compliance_report", description="Generate a compliance report for a framework with summary stats, gaps, and recommendations.",
             inputSchema={"type": "object", "properties": {"framework": {"type": "string", "description": "SOC2, HIPAA, or GDPR"}, "format": {"type": "string", "description": "Output format: summary or detailed", "default": "summary"}}, "required": ["framework"]}),
        Tool(name="schedule_review", description="Schedule a compliance review session.",
             inputSchema={"type": "object", "properties": {"framework": {"type": "string"}, "scheduled_date": {"type": "string", "description": "ISO date (YYYY-MM-DD)"}, "reviewer": {"type": "string"}, "notes": {"type": "string"}}, "required": ["framework", "scheduled_date", "reviewer"]}),
        Tool(name="initialize_framework", description="Initialize compliance checklist items from a framework template (SOC2/HIPAA/GDPR).",
             inputSchema={"type": "object", "properties": {"framework": {"type": "string", "description": "SOC2, HIPAA, or GDPR"}, "assignee": {"type": "string", "description": "Default assignee"}}, "required": ["framework"]}),
        Tool(name="update_control_status", description="Update the status of a compliance control item.",
             inputSchema={"type": "object", "properties": {"item_id": {"type": "string"}, "status": {"type": "string", "description": "not_started, in_progress, compliant, non_compliant"}, "actor": {"type": "string"}}, "required": ["item_id", "status", "actor"]}),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    _init_db()
    conn = _conn()
    try:
        if name == "check_compliance_status":
            return _check_compliance_status(conn, arguments)
        elif name == "create_audit_evidence":
            return _create_audit_evidence(conn, arguments)
        elif name == "generate_compliance_report":
            return _generate_compliance_report(conn, arguments)
        elif name == "schedule_review":
            return _schedule_review(conn, arguments)
        elif name == "initialize_framework":
            return _initialize_framework(conn, arguments)
        elif name == "update_control_status":
            return _update_control_status(conn, arguments)
        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]
    finally:
        conn.close()


def _check_compliance_status(conn, args):
    fw = args.get("framework", "all").upper()
    status_filter = args.get("status_filter")
    query = "SELECT * FROM compliance_items WHERE 1=1"
    params = []
    if fw != "ALL":
        query += " AND framework = ?"
        params.append(fw)
    if status_filter:
        query += " AND status = ?"
        params.append(status_filter)
    rows = conn.execute(query, params).fetchall()
    if not rows:
        return [TextContent(type="text", text=f"No compliance items found for {fw}. Use initialize_framework to set up.")]
    total = len(rows)
    by_status = {}
    for r in rows:
        by_status.setdefault(r["status"], 0)
        by_status[r["status"]] += 1
    pct_compliant = round(by_status.get("compliant", 0) / total * 100, 1)
    result = {"framework": fw, "total_controls": total, "by_status": by_status, "compliance_percentage": pct_compliant,
              "items": [dict(r) for r in rows[:50]]}
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


def _create_audit_evidence(conn, args):
    eid = generate_id()
    ts = now_iso()
    conn.execute("INSERT INTO evidence VALUES (?,?,?,?,?,?,?)",
                 (eid, args["compliance_item_id"], args["title"], args["description"],
                  args.get("file_path", ""), args["collected_by"], ts))
    # Append evidence ID to compliance item
    row = conn.execute("SELECT evidence_ids FROM compliance_items WHERE id=?", (args["compliance_item_id"],)).fetchone()
    if row:
        ids = json.loads(row["evidence_ids"])
        ids.append(eid)
        conn.execute("UPDATE compliance_items SET evidence_ids=?, updated_at=? WHERE id=?",
                     (json.dumps(ids), ts, args["compliance_item_id"]))
    log_audit(conn, "create_evidence", "evidence", eid, args["collected_by"],
              {"compliance_item_id": args["compliance_item_id"], "title": args["title"]})
    return [TextContent(type="text", text=json.dumps({"id": eid, "status": "created", "attached_to": args["compliance_item_id"]}))]


def _generate_compliance_report(conn, args):
    fw = args["framework"].upper()
    rows = conn.execute("SELECT * FROM compliance_items WHERE framework=?", (fw,)).fetchall()
    if not rows:
        return [TextContent(type="text", text=f"No data for {fw}. Initialize framework first.")]
    total = len(rows)
    by_status = {}
    gaps = []
    for r in rows:
        by_status.setdefault(r["status"], 0)
        by_status[r["status"]] += 1
        if r["status"] in ("not_started", "non_compliant"):
            gaps.append({"control_id": r["control_id"], "title": r["title"], "status": r["status"]})
    report = {
        "framework": fw, "generated_at": now_iso(), "total_controls": total,
        "status_breakdown": by_status,
        "compliance_percentage": round(by_status.get("compliant", 0) / total * 100, 1),
        "gaps": gaps[:20],
        "recommendations": _get_recommendations(gaps),
    }
    if args.get("format") == "detailed":
        report["all_items"] = [dict(r) for r in rows]
    return [TextContent(type="text", text=json.dumps(report, indent=2))]


def _get_recommendations(gaps):
    recs = []
    not_started = [g for g in gaps if g["status"] == "not_started"]
    non_compliant = [g for g in gaps if g["status"] == "non_compliant"]
    if non_compliant:
        recs.append(f"URGENT: {len(non_compliant)} controls are non-compliant. Address immediately.")
    if not_started:
        recs.append(f"{len(not_started)} controls haven't been started. Assign owners and set deadlines.")
    if not gaps:
        recs.append("All controls are in progress or compliant. Continue monitoring.")
    return recs


def _schedule_review(conn, args):
    rid = generate_id()
    conn.execute("INSERT INTO reviews VALUES (?,?,?,?,?,?,?)",
                 (rid, args["framework"].upper(), args["scheduled_date"], args["reviewer"],
                  "scheduled", args.get("notes", ""), now_iso()))
    log_audit(conn, "schedule_review", "review", rid, args["reviewer"],
              {"framework": args["framework"], "date": args["scheduled_date"]})
    conn.commit()
    return [TextContent(type="text", text=json.dumps({"id": rid, "status": "scheduled", "date": args["scheduled_date"]}))]


def _initialize_framework(conn, args):
    fw = args["framework"].upper()
    frameworks = _load_frameworks()
    if fw not in frameworks:
        # Use built-in defaults
        frameworks = _default_frameworks()
    if fw not in frameworks:
        return [TextContent(type="text", text=f"Unknown framework: {fw}. Supported: SOC2, HIPAA, GDPR")]
    existing = conn.execute("SELECT COUNT(*) as c FROM compliance_items WHERE framework=?", (fw,)).fetchone()["c"]
    if existing > 0:
        return [TextContent(type="text", text=f"{fw} already initialized with {existing} controls.")]
    ts = now_iso()
    assignee = args.get("assignee", "unassigned")
    items = []
    for cat, controls in frameworks[fw].items():
        for ctrl in controls:
            iid = generate_id()
            conn.execute("INSERT INTO compliance_items VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                         (iid, fw, cat, ctrl["id"], ctrl["title"], "not_started", assignee, "", "[]", ts, ts))
            items.append({"id": iid, "control_id": ctrl["id"], "title": ctrl["title"]})
    conn.commit()
    log_audit(conn, "initialize_framework", "framework", fw, assignee, {"count": len(items)})
    return [TextContent(type="text", text=json.dumps({"framework": fw, "controls_created": len(items), "items": items[:10]}))]


def _update_control_status(conn, args):
    ts = now_iso()
    conn.execute("UPDATE compliance_items SET status=?, updated_at=? WHERE id=?",
                 (args["status"], ts, args["item_id"]))
    log_audit(conn, "update_status", "compliance_item", args["item_id"], args["actor"],
              {"new_status": args["status"]})
    conn.commit()
    return [TextContent(type="text", text=json.dumps({"id": args["item_id"], "status": args["status"], "updated_at": ts}))]


def _default_frameworks():
    return {
        "SOC2": {
            "Security": [
                {"id": "CC6.1", "title": "Logical and physical access controls"},
                {"id": "CC6.2", "title": "System credentials management"},
                {"id": "CC6.3", "title": "Access based on authorization"},
                {"id": "CC6.6", "title": "Security measures against threats outside system boundaries"},
                {"id": "CC6.7", "title": "Restrict data movement to authorized users"},
                {"id": "CC6.8", "title": "Prevent unauthorized software"},
            ],
            "Availability": [
                {"id": "A1.1", "title": "System capacity and demand management"},
                {"id": "A1.2", "title": "Environmental protections and recovery"},
                {"id": "A1.3", "title": "Recovery infrastructure and testing"},
            ],
            "Confidentiality": [
                {"id": "C1.1", "title": "Confidential information identification"},
                {"id": "C1.2", "title": "Confidential information disposal"},
            ],
        },
        "HIPAA": {
            "Administrative": [
                {"id": "164.308(a)(1)", "title": "Security management process"},
                {"id": "164.308(a)(3)", "title": "Workforce security"},
                {"id": "164.308(a)(4)", "title": "Information access management"},
                {"id": "164.308(a)(5)", "title": "Security awareness and training"},
                {"id": "164.308(a)(6)", "title": "Security incident procedures"},
            ],
            "Technical": [
                {"id": "164.312(a)(1)", "title": "Access control"},
                {"id": "164.312(b)", "title": "Audit controls"},
                {"id": "164.312(c)(1)", "title": "Integrity controls"},
                {"id": "164.312(d)", "title": "Person or entity authentication"},
                {"id": "164.312(e)(1)", "title": "Transmission security"},
            ],
        },
        "GDPR": {
            "Data Protection": [
                {"id": "Art.5", "title": "Principles of data processing"},
                {"id": "Art.6", "title": "Lawfulness of processing"},
                {"id": "Art.7", "title": "Conditions for consent"},
                {"id": "Art.13", "title": "Information to be provided to data subjects"},
                {"id": "Art.15", "title": "Right of access by data subject"},
                {"id": "Art.17", "title": "Right to erasure"},
                {"id": "Art.20", "title": "Right to data portability"},
            ],
            "Security": [
                {"id": "Art.25", "title": "Data protection by design and default"},
                {"id": "Art.32", "title": "Security of processing"},
                {"id": "Art.33", "title": "Notification of data breach to authority"},
                {"id": "Art.35", "title": "Data protection impact assessment"},
            ],
        },
    }


def main():
    import asyncio
    _init_db()
    asyncio.run(_run())


async def _run():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    main()
