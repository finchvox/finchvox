from importlib.metadata import version

from packaging.version import Version

PIPECAT_NEW_TRACING_VERSION = Version("0.0.103")


def _get_pipecat_version() -> Version:
    try:
        return Version(version("pipecat-ai"))
    except Exception:
        return Version("0.0.0")


def has_new_tracing_api() -> bool:
    pipecat_version = _get_pipecat_version()
    if pipecat_version >= PIPECAT_NEW_TRACING_VERSION:
        return True
    try:
        from pipecat.utils.tracing.tracing_context import TracingContext  # noqa: F401

        return True
    except ImportError:
        return False


HAS_NEW_TRACING_API = has_new_tracing_api()
