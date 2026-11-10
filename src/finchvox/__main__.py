"""
FinchVox entry point - starts unified server with collector and UI.

Usage:
    python -m finchvox                    # Start with default port 3000
    python -m finchvox --port 8000        # Start with custom port
    python -m finchvox --help             # Show options
"""

import argparse
from pathlib import Path

from finchvox.cli import add_max_upload_argument, get_version
from finchvox.collector.config import BYTES_PER_MB, GRPC_PORT, get_default_data_dir
from finchvox.server import UnifiedServer


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="FinchVox unified server for voice AI observability",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m finchvox                           # Start with default ports
  python -m finchvox --port 8000               # Use custom HTTP port
  python -m finchvox --grpc-port 4318          # Use custom gRPC port
  python -m finchvox --data-dir ./my-data      # Use custom data directory
  python -m finchvox --max-upload-mb 4096      # Allow session uploads up to 4 GB
        """,
    )
    parser.add_argument(
        "--port", type=int, default=3000, help="HTTP server port (default: 3000)"
    )
    parser.add_argument(
        "--grpc-port",
        type=int,
        default=GRPC_PORT,
        help=f"gRPC server port (default: {GRPC_PORT})",
    )
    parser.add_argument(
        "--host", type=str, default="127.0.0.1", help="Host to bind to (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default=None,
        help="Data directory for traces/logs/audio/exceptions (default: ~/.finchvox)",
    )
    add_max_upload_argument(parser)

    args = parser.parse_args()

    # Resolve data directory
    if args.data_dir:
        data_dir = Path(args.data_dir).expanduser().resolve()
    else:
        data_dir = get_default_data_dir()

    print("=" * 50)
    print(f"Finchvox v{get_version()}")
    print(f"HTTP Server:  http://{args.host}:{args.port}")
    print(f"  - UI:       http://{args.host}:{args.port}")
    print(f"  - Collector: http://{args.host}:{args.port}/collector")
    print(f"gRPC Server:  {args.host}:{args.grpc_port}")
    print(f"Data Directory: {data_dir}")
    print(f"Max Upload: {args.max_upload_mb} MB")
    print("=" * 50)

    server = UnifiedServer(
        port=args.port,
        grpc_port=args.grpc_port,
        host=args.host,
        data_dir=data_dir,
        max_upload_bytes=args.max_upload_mb * BYTES_PER_MB,
    )
    server.run()


if __name__ == "__main__":
    main()
