#!/usr/bin/env python3
"""Entry point.

Usage:
  python3 main.py [--host 127.0.0.1] [--port 8080]

Environment:
  BABELFISH_FIXTURE=1        offline fixture mode (no RPC calls at all)
  BABELFISH_REFRESH_SECONDS  cache/refresh interval (default 60)
  BABELFISH_DB               SQLite snapshot path (default ./babelfish.db)
  BABELFISH_RPC_SLEEP        seconds between eth_calls in live mode (default 1.0)
  BABELFISH_HOST             bind address (default 127.0.0.1)
  PORT                       port (default 8080; PaaS hosts inject this)

Deploy (Railway / Render): Procfile runs
  python3 main.py --host 0.0.0.0 --port $PORT
so the server is reachable from outside the container.
"""

import argparse
import os

from babelfish.server import serve


def main():
    parser = argparse.ArgumentParser(description="Babel Fish Prices (Phase 0)")
    parser.add_argument("--host",
                        default=os.environ.get("BABELFISH_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int,
                        default=int(os.environ.get("PORT", "8080")))
    args = parser.parse_args()
    serve(args.host, args.port)


if __name__ == "__main__":
    main()
