#!/usr/bin/env python3
"""Serve the wood-products mill animation locally and open it in a browser.

A local HTTP server is needed because browsers block fetch() of data/mills.csv
and the base-map JSON over file:// URLs. Standard library only.
"""
from __future__ import annotations

import argparse
import functools
import http.server
import socket
import sys
import threading
import webbrowser
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    """Static file handler that disables caching so CSV edits show up on reload."""

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt: str, *args: object) -> None:  # keep the console readable
        if args and str(args[1]).startswith(("4", "5")):
            super().log_message(fmt, *args)


def free_port(preferred: int) -> int:
    """Return `preferred` if it's free, otherwise an OS-assigned free port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", preferred))
            return preferred
        except OSError:
            s.bind(("127.0.0.1", 0))
            return int(s.getsockname()[1])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000, help="Port to serve on (default 8000).")
    parser.add_argument("--no-browser", action="store_true", help="Don't open a browser window.")
    args = parser.parse_args()

    if not (APP_DIR / "index.html").exists():
        print(f"index.html not found in {APP_DIR}", file=sys.stderr)
        return 1
    if not (APP_DIR / "data" / "mills.csv").exists():
        print("Warning: data/mills.csv is missing; the page will show an error.", file=sys.stderr)
    if not (APP_DIR / "vendor" / "d3.min.js").exists():
        print("Note: vendor/ is empty, so libraries load from jsDelivr (internet needed). "
              "Run `python fetch_assets.py` once to work offline.")

    port = free_port(args.port)
    handler = functools.partial(QuietHandler, directory=str(APP_DIR))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"Serving {APP_DIR} at {url}  (Ctrl+C to stop)")
    if not args.no_browser:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
