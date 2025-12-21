"""Pytest configuration and fixtures."""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    """Create a test client for the FastAPI application."""
    return TestClient(app)


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Create mock authentication headers for testing."""
    # TODO: Implement proper auth token generation for tests
    return {"Authorization": "Bearer test-token"}
