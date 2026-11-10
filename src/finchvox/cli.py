"""
FinchVox CLI - Command-line interface for the finchvox package.

Provides subcommands:
- finchvox start: Start the unified server
- finchvox version: Display version information
"""

import argparse
import os
import sys
from pathlib import Path

from finchvox import telemetry
from finchvox.collector.config import BYTES_PER_MB, DEFAULT_MAX_UPLOAD_MB, GRPC_PORT
from finchvox.server import UnifiedServer
from finchvox.server_info import package_version


def _positive_int(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError(f"must be greater than 0, got {value}")
    return number


def add_max_upload_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--max-upload-mb",
        type=_positive_int,
        default=DEFAULT_MAX_UPLOAD_MB,
        help=(
            "Largest session zip the UI upload accepts, in MB; unzipped size limits "
            f"scale with it (default: {DEFAULT_MAX_UPLOAD_MB})"
        ),
    )


def get_version() -> str:
    """Get the package version."""
    return package_version()


def cmd_version(args):
    """Handle the 'version' subcommand."""
    print(f"finchvox version {get_version()}")
    print(f"Python {sys.version}")


def cmd_start(args):
    """Handle the 'start' subcommand."""
    os.environ["FINCHVOX_TELEMETRY"] = args.telemetry.lower()

    if args.data_dir:
        data_dir = Path(args.data_dir).expanduser().resolve()
    else:
        data_dir = Path.home() / ".finchvox"

    print("=" * 50)
    print(f"Finchvox v{get_version()}")
    print(f"HTTP Server:  http://{args.host}:{args.port}")
    print(f"  - UI:       http://{args.host}:{args.port}")
    print(f"  - Collector: http://{args.host}:{args.port}/collector")
    print(f"gRPC Server:  {args.host}:{args.grpc_port}")
    print(f"Data Directory: {data_dir}")
    print(f"Max Upload: {args.max_upload_mb} MB")
    if not telemetry.is_enabled():
        print("Telemetry: Disabled")
    print("=" * 50)

    server = UnifiedServer(
        port=args.port,
        grpc_port=args.grpc_port,
        host=args.host,
        data_dir=data_dir,
        max_upload_bytes=args.max_upload_mb * BYTES_PER_MB,
    )
    server.run()


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="finchvox",
        description="Finchvox - local Voice AI session replay for LiveKit Agents and Pipecat",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(
        title="commands",
        description="Available commands",
        dest="command",
        required=True,
    )

    # 'start' subcommand
    start_parser = subparsers.add_parser(
        "start",
        help="Start the unified server",
        description="Start the FinchVox unified server (gRPC + HTTP)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  finchvox start                           # Start with defaults
  finchvox start --port 8000               # Custom HTTP port
  finchvox start --grpc-port 4318          # Custom gRPC port
  finchvox start --data-dir ./my-data      # Custom data directory
  finchvox start --max-upload-mb 4096      # Allow session uploads up to 4 GB
        """,
    )
    start_parser.add_argument(
        "--port", type=int, default=3000, help="HTTP server port (default: 3000)"
    )
    start_parser.add_argument(
        "--grpc-port",
        type=int,
        default=GRPC_PORT,
        help=f"gRPC server port (default: {GRPC_PORT})",
    )
    start_parser.add_argument(
        "--host", type=str, default="127.0.0.1", help="Host to bind to (default: 127.0.0.1)"
    )
    start_parser.add_argument(
        "--data-dir",
        type=str,
        default=None,
        help="Data directory for traces/logs/audio/exceptions (default: ~/.finchvox)",
    )
    add_max_upload_argument(start_parser)
    start_parser.add_argument(
        "--telemetry",
        type=str,
        choices=("true", "false"),
        default="false",
        help="Enable or disable anonymous usage telemetry (default: false)",
    )
    start_parser.set_defaults(func=cmd_start)

    # 'version' subcommand
    version_parser = subparsers.add_parser(
        "version",
        help="Display version information",
        description="Display FinchVox version and Python version",
    )
    version_parser.set_defaults(func=cmd_version)

    # Parse arguments and dispatch to handler
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
