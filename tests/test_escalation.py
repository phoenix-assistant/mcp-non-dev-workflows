"""Tests for mcp-escalation server."""
import json
import sys
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import mcp_escalation
from mcp_escalation import (
    _init_db, _conn, _create_escalation, _route_ticket,
    _track_sla, _auto_gather_context, _resolve_escalation
)


@pytest.fixture(autouse=True)
def tmp_db(tmp_path):
    mcp_escalation._db_path = str(tmp_path / "test_escalation.db")
    _init_db()
    yield


def _make_escalation(conn, severity="high", category="technical"):
    result = _create_escalation(conn, {
        "title": "Server down", "description": "Production DB unreachable",
        "severity": severity, "category": category,
        "source": "chat", "customer_id": "cust-1", "customer_name": "Acme",
        "actor": "alice"
    })
    return json.loads(result[0].text)["id"]


class TestCreateEscalation:
    def test_create(self):
        conn = _conn()
        result = _create_escalation(conn, {
            "title": "Login broken", "description": "SSO returning 500",
            "severity": "critical", "category": "technical", "actor": "bob"
        })
        data = json.loads(result[0].text)
        assert data["status"] == "open"
        assert data["assigned_team"] == "engineering"
        assert data["severity"] == "critical"
        conn.close()

    def test_routing_billing(self):
        conn = _conn()
        result = _create_escalation(conn, {
            "title": "Invoice wrong", "description": "Double charged",
            "severity": "medium", "category": "billing", "actor": "alice"
        })
        data = json.loads(result[0].text)
        assert data["assigned_team"] == "finance-support"
        conn.close()

    def test_routing_security(self):
        conn = _conn()
        result = _create_escalation(conn, {
            "title": "Data breach", "description": "Suspicious access",
            "severity": "critical", "category": "security", "actor": "alice"
        })
        data = json.loads(result[0].text)
        assert data["assigned_team"] == "security-ops"
        conn.close()


class TestRouteTicket:
    def test_reroute(self):
        conn = _conn()
        eid = _make_escalation(conn)
        result = _route_ticket(conn, {"escalation_id": eid, "team": "platform", "agent": "charlie", "actor": "bob"})
        data = json.loads(result[0].text)
        assert data["routed_to"] == "platform"
        conn.close()

    def test_not_found(self):
        conn = _conn()
        result = _route_ticket(conn, {"escalation_id": "nope", "actor": "bob"})
        assert "not found" in result[0].text
        conn.close()


class TestTrackSla:
    def test_single_ticket(self):
        conn = _conn()
        eid = _make_escalation(conn)
        result = _track_sla(conn, {"escalation_id": eid})
        data = json.loads(result[0].text)
        assert "sla_remaining_hours" in data
        assert data["sla_breached"] is False
        conn.close()

    def test_overview(self):
        conn = _conn()
        _make_escalation(conn)
        _make_escalation(conn, "low", "billing")
        result = _track_sla(conn, {})
        data = json.loads(result[0].text)
        assert data["total_open"] == 2
        conn.close()


class TestAutoGatherContext:
    def test_by_escalation(self):
        conn = _conn()
        eid = _make_escalation(conn)
        result = _auto_gather_context(conn, {"escalation_id": eid})
        data = json.loads(result[0].text)
        assert "customer_history" in data
        conn.close()

    def test_by_customer(self):
        conn = _conn()
        _make_escalation(conn)
        _make_escalation(conn)
        result = _auto_gather_context(conn, {"customer_id": "cust-1"})
        data = json.loads(result[0].text)
        assert data["customer_ticket_count"] == 2
        conn.close()


class TestResolve:
    def test_resolve(self):
        conn = _conn()
        eid = _make_escalation(conn)
        result = _resolve_escalation(conn, {"escalation_id": eid, "resolution": "Restarted DB", "actor": "alice"})
        data = json.loads(result[0].text)
        assert data["status"] == "resolved"
        conn.close()
