import pytest

def test_health_endpoint_healthy(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("healthy", "degraded")
    assert data["database"] == "connected"
    assert "version" in data
    assert "ffmpeg" in data
    assert "ffprobe" in data

def test_health_reflects_missing_ffmpeg(client, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda cmd: None if cmd == "ffmpeg" else "/fake/path")
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "degraded"
    assert data["ffmpeg"] == "missing"
