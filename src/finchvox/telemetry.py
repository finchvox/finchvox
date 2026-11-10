import asyncio
import os
import sys
from datetime import UTC, datetime

import aiohttp
from loguru import logger

TELEMETRY_URL = "https://telemetry.finchvox.com"

_sent_events: set[str] = set()


def get_version() -> str:
    try:
        from importlib.metadata import PackageNotFoundError, version

        return version("finchvox")
    except PackageNotFoundError:
        return "unknown"


def get_os() -> str:
    platform = sys.platform
    if platform.startswith("darwin"):
        return "darwin"
    elif platform.startswith("linux"):
        return "linux"
    elif platform.startswith("win"):
        return "windows"
    return platform


def is_enabled() -> bool:
    env_value = os.environ.get("FINCHVOX_TELEMETRY", "false").lower()
    return env_value not in ("false", "0", "no", "off")


async def _send_event_async(event_type: str) -> None:
    if not is_enabled():
        return

    payload = {
        "event": event_type,
        "version": get_version(),
        "os": get_os(),
        "timestamp": datetime.now(UTC).isoformat(),
    }

    try:
        async with aiohttp.ClientSession() as session, session.post(
            TELEMETRY_URL, json=payload, timeout=aiohttp.ClientTimeout(total=5)
        ) as response:
            logger.debug(
                f"Telemetry sent: {event_type} (status: {response.status})"
            )
    except (aiohttp.ClientError, TimeoutError, OSError) as e:
        logger.debug(f"Telemetry failed (non-fatal): {e}")


def send_event(event_type: str, dedupe: bool = False) -> None:
    if not is_enabled():
        return

    if dedupe:
        if event_type in _sent_events:
            return
        _sent_events.add(event_type)

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_send_event_async(event_type))
    except RuntimeError:
        asyncio.run(_send_event_async(event_type))
