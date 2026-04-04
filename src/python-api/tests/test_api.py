"""Tests for all FastAPI endpoints in OneStopAgent."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient
from main import app
from services.project_store import store


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_store():
    """Clear the in-memory store before each test."""
    store.projects.clear()
    store.chat_histories.clear()
    yield


@pytest.fixture
def client():
    return TestClient(app)


USER_HEADER = {"x-user-id": "test-user-1"}

PROJECT_BODY = {
    "description": "AI-powered supply chain optimization",
    "customer_name": "Nike",
    "active_agents": ["business-value", "architect", "cost", "roi"],
}


def _create_project(client: TestClient, headers=None, body=None):
    """Helper to create a project and return the response."""
    return client.post(
        "/api/projects",
        json=body or PROJECT_BODY,
        headers=headers or USER_HEADER,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Health & Info
# ═══════════════════════════════════════════════════════════════════════════


class TestHealthAndInfo:
    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

    def test_info(self, client):
        resp = client.get("/api/info")
        assert resp.status_code == 200
        data = resp.json()
        assert "version" in data
        assert "framework" in data


# ═══════════════════════════════════════════════════════════════════════════
# Project CRUD
# ═══════════════════════════════════════════════════════════════════════════


class TestProjectCRUD:
    def test_create_project(self, client):
        resp = _create_project(client)
        assert resp.status_code == 200
        assert "projectId" in resp.json()

    def test_create_project_missing_user_id(self, client):
        resp = client.post("/api/projects", json=PROJECT_BODY)
        assert resp.status_code == 422

    def test_list_projects_empty(self, client):
        resp = client.get("/api/projects", headers=USER_HEADER)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_projects_after_create(self, client):
        _create_project(client)
        resp = client.get("/api/projects", headers=USER_HEADER)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["customerName"] == "Nike"

    def test_get_project(self, client):
        pid = _create_project(client).json()["projectId"]
        resp = client.get(f"/api/projects/{pid}", headers=USER_HEADER)
        assert resp.status_code == 200
        assert resp.json()["description"] == PROJECT_BODY["description"]

    def test_get_project_not_found(self, client):
        resp = client.get("/api/projects/fake-id", headers=USER_HEADER)
        assert resp.status_code == 404

    def test_get_project_wrong_user(self, client):
        """Multi-tenant isolation: user-2 cannot see user-1's project."""
        pid = _create_project(client).json()["projectId"]
        resp = client.get(
            f"/api/projects/{pid}",
            headers={"x-user-id": "test-user-2"},
        )
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# Agent Toggle
# ═══════════════════════════════════════════════════════════════════════════


class TestAgentToggle:
    def test_get_agents(self, client):
        pid = _create_project(client).json()["projectId"]
        resp = client.get(f"/api/projects/{pid}/agents", headers=USER_HEADER)
        assert resp.status_code == 200
        data = resp.json()
        assert "agents" in data
        assert len(data["agents"]) > 0

    def test_toggle_agent_off(self, client):
        pid = _create_project(client).json()["projectId"]
        resp = client.patch(
            f"/api/projects/{pid}/agents/roi",
            json={"active": False},
            headers=USER_HEADER,
        )
        assert resp.status_code == 200
        agents = resp.json()["agents"]
        roi = next(a for a in agents if a["agentId"] == "roi")
        assert roi["active"] is False

    def test_cannot_deactivate_pm(self, client):
        pid = _create_project(client).json()["projectId"]
        resp = client.patch(
            f"/api/projects/{pid}/agents/pm",
            json={"active": False},
            headers=USER_HEADER,
        )
        assert resp.status_code == 400

    def test_cannot_deactivate_architect(self, client):
        pid = _create_project(client).json()["projectId"]
        resp = client.patch(
            f"/api/projects/{pid}/agents/architect",
            json={"active": False},
            headers=USER_HEADER,
        )
        assert resp.status_code == 400


# ═══════════════════════════════════════════════════════════════════════════
# Chat History
# ═══════════════════════════════════════════════════════════════════════════


class TestChatHistory:
    def test_empty_chat(self, client):
        pid = _create_project(client).json()["projectId"]
        resp = client.get(f"/api/projects/{pid}/chat", headers=USER_HEADER)
        assert resp.status_code == 200
        assert resp.json()["messages"] == []

    def test_chat_has_correct_structure(self, client):
        pid = _create_project(client).json()["projectId"]
        resp = client.get(f"/api/projects/{pid}/chat", headers=USER_HEADER)
        data = resp.json()
        assert "messages" in data
        assert "hasMore" in data
        assert "nextCursor" in data


# ═══════════════════════════════════════════════════════════════════════════
# Company Search (fallback)
# ═══════════════════════════════════════════════════════════════════════════


class TestCompanySearch:
    def test_company_fallback_small(self, client):
        resp = client.get("/api/company/fallback/small", params={"name": "TestCo"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["employeeCount"] == 200
        assert data["name"] == "TestCo"

    def test_company_fallback_enterprise(self, client):
        resp = client.get("/api/company/fallback/enterprise", params={"name": "BigCo"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["employeeCount"] == 25_000

    def test_company_fallback_invalid_size(self, client):
        resp = client.get("/api/company/fallback/huge", params={"name": "Test"})
        assert resp.status_code == 400


# ═══════════════════════════════════════════════════════════════════════════
# Workflow Visualization
# ═══════════════════════════════════════════════════════════════════════════


class TestWorkflowVisualization:
    def test_workflow_endpoint(self, client):
        resp = client.get("/api/workflow")
        assert resp.status_code == 200
        assert "mermaid" in resp.text.lower()


# ═══════════════════════════════════════════════════════════════════════════
# Security Guards
# ═══════════════════════════════════════════════════════════════════════════


class TestSecurityGuards:
    def test_pptx_download_no_file(self, client):
        pid = _create_project(client).json()["projectId"]
        resp = client.get(
            f"/api/projects/{pid}/export/pptx",
            headers=USER_HEADER,
        )
        assert resp.status_code == 404

    def test_projects_require_user_header(self, client):
        """All project-scoped endpoints must require x-user-id."""
        # GET /api/projects
        assert client.get("/api/projects").status_code == 422
        # POST /api/projects
        assert client.post("/api/projects", json=PROJECT_BODY).status_code == 422
        # GET /api/projects/{id}
        assert client.get("/api/projects/any-id").status_code == 422
        # GET /api/projects/{id}/chat
        assert client.get("/api/projects/any-id/chat").status_code == 422
        # GET /api/projects/{id}/agents
        assert client.get("/api/projects/any-id/agents").status_code == 422
