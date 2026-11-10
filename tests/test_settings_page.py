"""The settings page, and the read-only server information it shows."""

import importlib.metadata

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import finchvox.server_info as server_info_module
from finchvox.collector.config import BYTES_PER_MB
from finchvox.server import UnifiedServer
from finchvox.server_info import ServerInfo
from finchvox.ui_routes import register_ui_routes


@pytest.fixture
def client(tmp_path):
    app = FastAPI()
    register_ui_routes(app, tmp_path, max_upload_bytes=256 * BYTES_PER_MB)
    return TestClient(app)


def test_settings_page_is_served_with_its_scripts(client):
    response = client.get("/settings")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    html = response.text
    # preferences.js must come before the stylesheet so the theme applies before drawing.
    assert html.index("/js/preferences.js") < html.index("/css/app.css")
    assert "/js/settings.js" in html


def test_every_page_loads_preferences_before_the_stylesheet(client):
    for path in ("/", "/sessions/some-session", "/settings"):
        html = client.get(path).text
        assert html.index("/js/preferences.js") < html.index("/css/app.css"), path


def test_server_information_without_the_unified_server(client, tmp_path):
    info = client.get("/api/settings/server").json()

    assert info == {
        "version": importlib.metadata.version("finchvox"),
        "data_dir": str(tmp_path),
        "host": None,
        "http_port": None,
        "grpc_port": None,
        "max_upload_mb": 256,
        "telemetry_enabled": False,
        "in_container": server_info_module.running_in_container(),
    }


def test_container_is_detected_from_the_engine_marker_file(tmp_path, monkeypatch):
    marker = tmp_path / ".dockerenv"
    monkeypatch.setattr(server_info_module, "CONTAINER_MARKERS", (marker, tmp_path / ".containerenv"))
    assert ServerInfo.describe(data_dir=tmp_path, max_upload_bytes=BYTES_PER_MB).in_container is False

    marker.touch()

    assert ServerInfo.describe(data_dir=tmp_path, max_upload_bytes=BYTES_PER_MB).in_container is True


def test_unified_server_reports_its_startup_settings(tmp_path):
    server = UnifiedServer(
        port=3333, grpc_port=4444, host="127.0.0.1", data_dir=tmp_path,
        max_upload_bytes=2048 * BYTES_PER_MB,
    )

    info = TestClient(server.app).get("/api/settings/server").json()

    assert info["http_port"] == 3333
    assert info["grpc_port"] == 4444
    assert info["host"] == "127.0.0.1"
    assert info["max_upload_mb"] == 2048
    assert info["data_dir"] == str(tmp_path)


def test_telemetry_setting_is_reported(tmp_path, monkeypatch):
    monkeypatch.setenv("FINCHVOX_TELEMETRY", "true")

    info = ServerInfo.describe(data_dir=tmp_path, max_upload_bytes=BYTES_PER_MB)

    assert info.telemetry_enabled is True


@pytest.mark.parametrize(
    "path", ["/", "/sessions/some-session", "/settings", "/css/app.css", "/js/preferences.js", "/images/icons.svg"]
)
def test_ui_files_are_revalidated_so_upgrades_show_at_once(client, path):
    response = client.get(path)

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"


def test_unchanged_ui_files_still_answer_not_modified(client):
    first = client.get("/css/app.css")

    again = client.get("/css/app.css", headers={"If-None-Match": first.headers["etag"]})

    assert again.status_code == 304


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_server_settings_cannot_be_changed_from_the_browser(client, method):
    response = client.request(method, "/api/settings/server", json={"http_port": 80})

    assert response.status_code == 405
