"""Tests for mcp-dealflow server."""
import json
import sys
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import mcp_dealflow
from mcp_dealflow import (
    _init_db, _conn, _track_deal_stage, _flag_stalled_deal,
    _generate_deal_summary, _create_approval_request
)


@pytest.fixture(autouse=True)
def tmp_db(tmp_path):
    mcp_dealflow._db_path = str(tmp_path / "test_dealflow.db")
    _init_db()
    yield


def _create_deal(conn, name="Acme Corp", value=50000, stage="prospecting"):
    result = _track_deal_stage(conn, {
        "name": name, "company": name, "value": value,
        "stage": stage, "owner": "alice", "actor": "alice"
    })
    return json.loads(result[0].text)["id"]


class TestTrackDealStage:
    def test_create_deal(self):
        conn = _conn()
        result = _track_deal_stage(conn, {
            "name": "Big Deal", "company": "Acme", "value": 100000,
            "stage": "prospecting", "owner": "alice", "actor": "alice"
        })
        data = json.loads(result[0].text)
        assert data["status"] == "created"
        assert data["stage"] == "prospecting"
        conn.close()

    def test_advance_stage(self):
        conn = _conn()
        deal_id = _create_deal(conn)
        result = _track_deal_stage(conn, {"deal_id": deal_id, "stage": "qualification", "actor": "alice"})
        data = json.loads(result[0].text)
        assert data["stage"] == "qualification"
        assert data["previous"] == "prospecting"
        conn.close()

    def test_not_found(self):
        conn = _conn()
        result = _track_deal_stage(conn, {"deal_id": "nonexistent", "stage": "proposal", "actor": "bob"})
        assert "not found" in result[0].text
        conn.close()


class TestFlagStalled:
    def test_flag(self):
        conn = _conn()
        deal_id = _create_deal(conn)
        result = _flag_stalled_deal(conn, {"deal_id": deal_id, "reason": "No response", "actor": "alice"})
        data = json.loads(result[0].text)
        assert data["stalled"] is True
        conn.close()

    def test_list_stalled(self):
        conn = _conn()
        deal_id = _create_deal(conn)
        _flag_stalled_deal(conn, {"deal_id": deal_id, "reason": "Ghost", "actor": "alice"})
        result = _flag_stalled_deal(conn, {})
        data = json.loads(result[0].text)
        assert data["count"] == 1
        conn.close()


class TestDealSummary:
    def test_summary(self):
        conn = _conn()
        _create_deal(conn, "A", 10000)
        _create_deal(conn, "B", 20000, "qualification")
        result = _generate_deal_summary(conn, {})
        data = json.loads(result[0].text)
        assert data["total_deals"] == 2
        assert data["total_pipeline_value"] == 30000
        conn.close()


class TestApproval:
    def test_create_approval(self):
        conn = _conn()
        deal_id = _create_deal(conn)
        result = _create_approval_request(conn, {
            "deal_id": deal_id, "type": "discount",
            "requested_by": "alice", "approver": "bob", "notes": "15% off"
        })
        data = json.loads(result[0].text)
        assert data["status"] == "pending"
        conn.close()
