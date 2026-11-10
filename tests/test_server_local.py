import sys
from importlib.metadata import PackageNotFoundError
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from starlette.middleware.body_limit import RequestBodyLimitMiddleware

import finchvox.__main__ as main_module
import finchvox.cli as cli_module
import finchvox.server as server_module
import finchvox.server_info as server_info_module
from finchvox.server import UnifiedServer

ENTRY_POINTS = [
    pytest.param(cli_module, ["finchvox", "start"], id="finchvox-start"),
    pytest.param(main_module, ["python -m finchvox"], id="python-m-finchvox"),
]


def test_get_version_falls_back_when_package_is_not_installed(monkeypatch):
    def missing_package(name):
        raise PackageNotFoundError(name)

    monkeypatch.setattr(server_info_module, "version", missing_package)

    assert cli_module.get_version() == "0.0.1"


def test_unified_server_defaults_to_loopback(tmp_path):
    server = UnifiedServer(data_dir=tmp_path)
    assert server.host == "127.0.0.1"


@pytest.mark.parametrize(("module", "argv"), ENTRY_POINTS)
def test_max_upload_flag_reaches_server(module, argv, monkeypatch):
    unified_server = Mock()
    monkeypatch.setattr(module, "UnifiedServer", unified_server)
    monkeypatch.setattr(sys, "argv", [*argv, "--max-upload-mb", "5"])

    module.main()

    assert unified_server.call_args.kwargs["max_upload_bytes"] == 5 * 1024 * 1024


@pytest.mark.parametrize(("module", "argv"), ENTRY_POINTS)
def test_max_upload_defaults_to_one_gigabyte(module, argv, monkeypatch):
    unified_server = Mock()
    monkeypatch.setattr(module, "UnifiedServer", unified_server)
    monkeypatch.setattr(sys, "argv", argv)

    module.main()

    assert unified_server.call_args.kwargs["max_upload_bytes"] == 1024 * 1024 * 1024


@pytest.mark.parametrize("value", ["0", "-1", "lots"])
def test_max_upload_flag_rejects_non_positive_values(value, monkeypatch):
    monkeypatch.setattr(cli_module, "UnifiedServer", Mock())
    monkeypatch.setattr(
        sys, "argv", ["finchvox", "start", "--max-upload-mb", value]
    )

    with pytest.raises(SystemExit):
        cli_module.main()


def test_server_passes_upload_limit_to_routes(tmp_path):
    server = UnifiedServer(data_dir=tmp_path, max_upload_bytes=4096)

    response = TestClient(server.app).get("/api/sessions")

    assert response.json()["max_upload_bytes"] == 4096


def test_every_route_accepting_a_body_has_a_size_limit(tmp_path):
    """A new upload route must choose a limit rather than accept unlimited data."""
    server = UnifiedServer(data_dir=tmp_path)
    body_routes = [
        route
        for route in server.app.routes
        if getattr(route, "methods", None) and route.methods & {"POST", "PUT", "PATCH"}
    ]

    assert body_routes
    unlimited = [
        route.path
        for route in body_routes
        if not isinstance(route.app, RequestBodyLimitMiddleware)
    ]
    assert unlimited == []


def test_upload_limit_does_not_affect_collector_routes(tmp_path):
    server = UnifiedServer(data_dir=tmp_path, max_upload_bytes=1)

    response = TestClient(server.app).post(
        f"/collector/livekit/{'a' * 32}/report", json={"note": "larger than one byte"}
    )

    assert response.status_code == 201


@pytest.mark.asyncio
async def test_grpc_binds_to_configured_host(tmp_path, monkeypatch):
    grpc_server = Mock()
    grpc_server.add_insecure_port.return_value = 4317

    monkeypatch.setattr(server_module.grpc, "server", lambda *args, **kwargs: grpc_server)
    monkeypatch.setattr(
        server_module, "add_TraceServiceServicer_to_server", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(
        server_module, "add_LogsServiceServicer_to_server", lambda *args, **kwargs: None
    )

    server = UnifiedServer(host="127.0.0.1", grpc_port=4317, data_dir=tmp_path)
    await server.start_grpc()

    grpc_server.add_insecure_port.assert_called_once_with("127.0.0.1:4317")
    grpc_server.start.assert_called_once_with()


@pytest.mark.asyncio
async def test_grpc_all_interfaces_is_explicit_opt_in(tmp_path, monkeypatch):
    grpc_server = Mock()
    grpc_server.add_insecure_port.return_value = 4317

    monkeypatch.setattr(server_module.grpc, "server", lambda *args, **kwargs: grpc_server)
    monkeypatch.setattr(
        server_module, "add_TraceServiceServicer_to_server", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(
        server_module, "add_LogsServiceServicer_to_server", lambda *args, **kwargs: None
    )

    server = UnifiedServer(host="0.0.0.0", grpc_port=4317, data_dir=tmp_path)
    await server.start_grpc()

    grpc_server.add_insecure_port.assert_called_once_with("0.0.0.0:4317")
