"""
Shared pytest fixtures for the F1 Race Intelligence test suite.
"""
import os
import pytest
import backend.cache as cache_mod


@pytest.fixture
def tmp_db(monkeypatch, tmp_path):
    """Redirect all cache reads/writes to an isolated temp SQLite file."""
    db_path = str(tmp_path / "test_cache.db")
    monkeypatch.setattr(cache_mod, "_DB_PATH", db_path)
    return db_path


@pytest.fixture
def app_client(monkeypatch, tmp_path):
    """
    FastAPI TestClient with:
    - SQLite cache redirected to a temp file
    - FastF1 prewarm task suppressed (non-fatal anyway, but speeds up tests)
    """
    db_path = str(tmp_path / "test_cache.db")
    monkeypatch.setattr(cache_mod, "_DB_PATH", db_path)

    from fastapi.testclient import TestClient
    from backend.main import app

    with TestClient(app) as client:
        yield client
