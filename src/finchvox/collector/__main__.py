import sys

from loguru import logger

from .config import LOG_LEVEL
from .server import run_server


def main():
    """Main entry point for the OTLP collector."""
    # Configure loguru
    logger.remove()  # Remove default handler
    logger.add(
        sink=sys.stderr,
        level=LOG_LEVEL,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
    )

    logger.info("Starting FinchVox OTLP Collector")
    run_server()


if __name__ == "__main__":
    main()
