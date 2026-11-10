"""What the settings page shows about the running server.

These values are fixed when Finchvox starts (command-line flags or compose.yaml),
so the settings page only displays them. They are deliberately not editable
from the browser: Finchvox has no login, so a write endpoint could be called by
any website the user visits.
"""

from dataclasses import asdict, dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from finchvox import telemetry
from finchvox.collector.config import BYTES_PER_MB

FALLBACK_VERSION = "0.0.1"

# Files container engines create: Docker writes /.dockerenv, Podman /run/.containerenv.
CONTAINER_MARKERS = (Path("/.dockerenv"), Path("/run/.containerenv"))


def running_in_container() -> bool:
    """True inside a container, where the ports seen here may be published as others."""
    return any(marker.exists() for marker in CONTAINER_MARKERS)


def package_version() -> str:
    """The installed Finchvox version, or a placeholder when running unpackaged."""
    try:
        return version("finchvox")
    except PackageNotFoundError:
        return FALLBACK_VERSION


@dataclass(frozen=True)
class ServerInfo:
    version: str
    data_dir: str
    host: str | None
    http_port: int | None
    grpc_port: int | None
    max_upload_mb: int
    telemetry_enabled: bool
    in_container: bool

    @classmethod
    def describe(
        cls,
        *,
        data_dir: Path,
        max_upload_bytes: int,
        host: str | None = None,
        http_port: int | None = None,
        grpc_port: int | None = None,
    ) -> "ServerInfo":
        """Snapshot the server's startup settings.

        ``host`` and the ports are unknown when the UI routes are mounted without
        the unified server, as in tests; they are then reported as ``None``.
        """
        return cls(
            version=package_version(),
            data_dir=str(data_dir),
            host=host,
            http_port=http_port,
            grpc_port=grpc_port,
            max_upload_mb=max_upload_bytes // BYTES_PER_MB,
            telemetry_enabled=telemetry.is_enabled(),
            in_container=running_in_container(),
        )

    def to_dict(self) -> dict:
        return asdict(self)
