"""Tests for mcp-compliance server."""
import json
import sys
import pytest
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import tempfile
from mcp_compliance import (
    app, _init_db, _conn, _db_path, _check_compliance_status,
    _create_audit_evidence, _generate_compliance_report, _schedule_review,
    _initialize_framework, _update_control_status
)
import mcp_compliance


@pytest.fixture(autouse=True)
def tmp_db(tmp_path):
    mcp_compliance._db_path = str(tmp_path / "test_compliance.db")
    _init_db()
    yield
    

class TestInitializeFramework:
    def test_init_soc2(self):
        conn = _conn()
        result = _initialize_framework(conn, {"framework": "SOC2", "assignee": "alice"})
        data = json.loads(result[0].text)
        assert data["framework"] == "SOC2"
        assert data["controls_created"] == 11  # 6+3+2
        conn.close()

    def test_init_hipaa(self):
        conn = _conn()
        result = _initialize_framework(conn, {"framework": "HIPAA"})
        data = json.loads(result[0].text)
        assert data["controls_created"] == 10
        conn.close()

    def test_init_gdpr(self):
        conn = _conn()
        result = _initialize_framework(conn, {"framework": "GDPR"})
        data = json.loads(result[0].text)
        assert data["controls_created"] == 11
        conn.close()

    def test_duplicate_init(self):
        conn = _conn()
        _initialize_framework(conn, {"framework": "SOC2"})
        result = _initialize_framework(conn, {"framework": "SOC2"})
        assert "already initialized" in result[0].text
        conn.close()


class TestCheckCompliance:
    def test_empty(self):
        conn = _conn()
        result = _check_compliance_status(conn, {"framework": "SOC2"})
        assert "No compliance items" in result[0].text
        conn.close()

    def test_with_data(self):
        conn = _conn()
        _initialize_framework(conn, {"framework": "SOC2"})
        result = _check_compliance_status(conn, {"framework": "SOC2"})
        data = json.loads(result[0].text)
        assert data["total_controls"] == 11
        assert data["compliance_percentage"] == 0.0
        conn.close()


class TestAuditEvidence:
    def test_create_evidence(self):
        conn = _conn()
        _initialize_framework(conn, {"framework": "SOC2"})
        items = conn.execute("SELECT id FROM compliance_items LIMIT 1").fetchone()
        item_id = items["id"]
        result = _create_audit_evidence(conn, {
            "compliance_item_id": item_id, "title": "Access log export",
            "description": "Q1 access logs", "collected_by": "alice"
        })
        data = json.loads(result[0].text)
        assert data["status"] == "created"
        assert data["attached_to"] == item_id
        conn.close()


class TestReport:
    def test_generate_report(self):
        conn = _conn()
        _initialize_framework(conn, {"framework": "SOC2"})
        result = _generate_compliance_report(conn, {"framework": "SOC2"})
        data = json.loads(result[0].text)
        assert data["total_controls"] == 11
        assert len(data["gaps"]) == 11  # all not_started
        conn.close()


class TestUpdateStatus:
    def test_update(self):
        conn = _conn()
        _initialize_framework(conn, {"framework": "SOC2"})
        item = conn.execute("SELECT id FROM compliance_items LIMIT 1").fetchone()
        result = _update_control_status(conn, {"item_id": item["id"], "status": "compliant", "actor": "bob"})
        data = json.loads(result[0].text)
        assert data["status"] == "compliant"
        conn.close()


class TestScheduleReview:
    def test_schedule(self):
        conn = _conn()
        result = _schedule_review(conn, {"framework": "SOC2", "scheduled_date": "2025-06-01", "reviewer": "alice"})
        data = json.loads(result[0].text)
        assert data["status"] == "scheduled"
        conn.close()
