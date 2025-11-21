"""Tests for health check endpoints.
"""

from fastapi.testclient import TestClient
from legal_portal.api.main import app

client = TestClient(app)


def test_root_endpoint():
    """Test the root endpoint returns basic info."""
    response = client.get("/")

    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Legal Document Analysis API"
    assert data["version"] == "1.0.0"
    assert data["status"] == "running"


def test_health_check():
    """Test basic health check endpoint."""
    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "Legal Document Analysis API"
    assert "version" in data
