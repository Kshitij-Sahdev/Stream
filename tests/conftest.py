import tempfile
import os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch, tmp_path):
    test_data_dir = tmp_path / "stream_test_data"
    test_data_dir.mkdir(parents=True, exist_ok=True)
    (test_data_dir / "originals").mkdir(exist_ok=True)
    (test_data_dir / "hls").mkdir(exist_ok=True)

    # Monkeypatch config paths to use temp test directory
    monkeypatch.setattr("app.config.DATA_DIR", test_data_dir)
    monkeypatch.setattr("app.config.ORIGINALS_DIR", test_data_dir / "originals")
    monkeypatch.setattr("app.config.HLS_DIR", test_data_dir / "hls")
    monkeypatch.setattr("app.config.DB_PATH", test_data_dir / "stream.db")

    # Initialize the test DB
    from app.database import init_db
    init_db()

    yield test_data_dir

@pytest.fixture
def client():
    from app.main import app
    with TestClient(app) as test_client:
        yield test_client
