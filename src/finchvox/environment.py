import asyncio
import platform
import sys
import threading
from datetime import UTC

import aiohttp
from loguru import logger
from opentelemetry.sdk.trace import ReadableSpan, SpanProcessor

_captured_environment: dict | None = None
_environment_sent_traces: set[str] = set()
_lock = threading.Lock()


def capture_environment() -> dict:
    global _captured_environment

    env = {
        "os": {"system": "unknown", "release": "unknown", "machine": "unknown"},
        "python": {"version": "unknown", "implementation": "unknown"},
        "packages": {},
        "captured_at": None,
    }

    # Environment capture runs inside the user's agent process during init(); the
    # platform/importlib probes can fail in many OS-specific ways (subprocess
    # errors, broken package metadata), and none may crash the agent.
    try:
        env["os"] = {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        }
    except Exception as e:  # noqa: BLE001 - best-effort probe must never crash the agent
        logger.debug(f"Could not capture OS info: {e}")

    try:
        env["python"] = {
            "version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "implementation": platform.python_implementation(),
        }
    except Exception as e:  # noqa: BLE001 - best-effort probe must never crash the agent
        logger.debug(f"Could not capture Python info: {e}")

    try:
        from importlib.metadata import distributions

        env["packages"] = {
            d.metadata["Name"]: d.version for d in distributions() if d.metadata["Name"]
        }
    except Exception as e:  # noqa: BLE001 - broken third-party package metadata must never crash the agent
        logger.debug(f"Could not capture installed packages: {e}")

    try:
        from datetime import datetime

        env["captured_at"] = datetime.now(UTC).isoformat()
    except Exception as e:  # noqa: BLE001 - best-effort probe must never crash the agent
        logger.debug(f"Could not capture timestamp: {e}")

    _captured_environment = env
    return env


def get_captured_environment() -> dict | None:
    return _captured_environment


class EnvironmentSpanProcessor(SpanProcessor):
    def __init__(self, endpoint: str):
        self._endpoint = endpoint

    def on_start(self, span, parent_context):
        pass

    def on_end(self, span: ReadableSpan):
        trace_id = format(span.get_span_context().trace_id, "032x")
        if trace_id == "0" * 32:
            return

        with _lock:
            if trace_id in _environment_sent_traces:
                return
            _environment_sent_traces.add(trace_id)

        env = get_captured_environment()
        if not env:
            return

        try:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                asyncio.run(self._send_environment(trace_id, env))
            else:
                loop.create_task(self._send_environment(trace_id, env))
        except Exception as e:  # noqa: BLE001 - runs inside span.end() in the user's agent, so nothing may escape
            logger.debug(f"Could not upload environment: {e}")

    async def _send_environment(self, trace_id: str, env: dict):
        try:
            url = f"{self._endpoint}/collector/environment/{trace_id}"
            async with aiohttp.ClientSession() as session, session.post(
                url, json=env, timeout=aiohttp.ClientTimeout(total=5)
            ):
                pass
        except (aiohttp.ClientError, TimeoutError, OSError, ValueError) as e:
            logger.debug(f"Could not upload environment: {e}")

    def shutdown(self):
        pass

    def force_flush(self, timeout_millis=30000):
        return True
