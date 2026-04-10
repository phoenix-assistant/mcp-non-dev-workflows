# MCP for Non-Dev Workflows

> Pre-built MCP servers that bring AI agents to compliance, deal flow, and support — not just code.

Three production-ready MCP servers for operations teams:

| Server | What it does | Tools |
|--------|-------------|-------|
| **mcp-compliance** | SOC2, HIPAA, GDPR checklist automation with audit trails | `check_compliance_status`, `create_audit_evidence`, `generate_compliance_report`, `schedule_review`, `initialize_framework`, `update_control_status` |
| **mcp-dealflow** | Unified deal pipeline management | `track_deal_stage`, `flag_stalled_deal`, `generate_deal_summary`, `create_approval_request` |
| **mcp-escalation** | Smart support routing with SLA tracking | `create_escalation`, `route_ticket`, `track_sla`, `auto_gather_context`, `resolve_escalation` |

## Quick Start (Non-Developer Guide)

### Prerequisites
- Python 3.10+ ([download](https://python.org/downloads))
- [Claude Desktop](https://claude.ai/download) installed

### Install

```bash
# Clone the repo
git clone https://github.com/phoenix-assistant/mcp-non-dev-workflows.git
cd mcp-non-dev-workflows

# Create virtual environment and install
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -e .
```

### Configure Claude Desktop

Copy `claude_desktop_config.json` to your Claude Desktop config directory:

- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

Edit the file to set the correct `cwd` path to where you cloned the repo, and update `command` to point to the Python in your `.venv`:

```json
{
  "mcpServers": {
    "mcp-compliance": {
      "command": "/path/to/mcp-non-dev-workflows/.venv/bin/python",
      "args": ["-m", "mcp_compliance.server"],
      "cwd": "/path/to/mcp-non-dev-workflows"
    },
    "mcp-dealflow": {
      "command": "/path/to/mcp-non-dev-workflows/.venv/bin/python",
      "args": ["-m", "mcp_dealflow.server"],
      "cwd": "/path/to/mcp-non-dev-workflows"
    },
    "mcp-escalation": {
      "command": "/path/to/mcp-non-dev-workflows/.venv/bin/python",
      "args": ["-m", "mcp_escalation.server"],
      "cwd": "/path/to/mcp-non-dev-workflows"
    }
  }
}
```

Restart Claude Desktop. You'll see the tools available in your conversation.

## Use Cases

### Compliance Team
> "Initialize our SOC2 checklist, assign controls to team leads, and generate a gap report"

```
→ initialize_framework(framework="SOC2", assignee="sarah")
→ check_compliance_status(framework="SOC2")
→ generate_compliance_report(framework="SOC2")
```

### Sales Operations
> "Create a deal for Acme Corp at $150K, move it to proposal stage, and flag the stalled deals"

```
→ track_deal_stage(name="Acme Corp", company="Acme", value=150000, stage="prospecting", actor="rep1")
→ track_deal_stage(deal_id="...", stage="proposal", actor="rep1")
→ flag_stalled_deal()  # lists all stalled deals
```

### Support Manager
> "Create a critical escalation for the outage, check what's breaching SLA, and gather context"

```
→ create_escalation(title="Production outage", description="DB down", severity="critical", category="technical", actor="oncall")
→ track_sla()  # overview of all SLA status
→ auto_gather_context(customer_id="cust-123")
```

## Architecture

```
┌─────────────────────────────────┐
│     Claude Desktop / Agent      │
└──────────┬──────────────────────┘
           │ MCP (stdio)
┌──────────▼──────────────────────┐
│  mcp-compliance  │  mcp-dealflow │  mcp-escalation
│  (SQLite + YAML) │  (SQLite)     │  (SQLite + YAML)
└─────────────────────────────────┘
```

- **Persistence**: SQLite databases in `~/.mcp/` (auto-created)
- **Config**: YAML files for compliance frameworks and routing rules
- **Audit**: Append-only audit log in every server
- **Transport**: stdio (MCP standard)

## Configuration

### Compliance Frameworks
Edit `mcp_compliance/frameworks.yaml` to customize controls for your organization.

### Escalation Routing
Edit `mcp_escalation/routing_rules.yaml` to configure team routing and SLA rules.

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Run a server directly
python -m mcp_compliance.server
```

## License

MIT
