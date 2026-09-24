#!/usr/bin/env python3
"""Serve the race player UI along with a race log file.

Usage:
    python serve_viewer.py [race.jsonl.br] [--port 5173] [--dev]

By default this starts the Vite dev server (hot reload). With --dev it copies
the given log into public/ so it's served at /race.jsonl.br.

Without --dev it builds the app and serves the static output plus the logs.
"""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "public"
DIST = ROOT / "dist"


class RaceHandler(SimpleHTTPRequestHandler):
    """Serves static files plus a /api/races listing of the copied .jsonl.br files."""

    def end_headers(self):
        # Load-bearing: a .br log is served compressed, so the browser must be
        # told to decode it or the player gets raw brotli and JSON.parse fails
        # on line 1.
        if self.path.split("?", 1)[0].endswith(".br"):
            self.send_header("Content-Encoding", "br")
        super().end_headers()

    def do_GET(self):
        if self.path.split("?", 1)[0] == "/api/races":
            files = [
                {
                    "name": p.name,
                    "mtime": datetime.fromtimestamp(
                        p.stat().st_mtime, tz=timezone.utc
                    ).isoformat(),
                }
                for p in sorted(DIST.glob("*.jsonl.br"))
            ]
            body = json.dumps({"files": files}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        return super().do_GET()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("race_file", nargs="?", default="race.jsonl.br",
                        help="Path to the race log (default: ./race.jsonl.br)")
    parser.add_argument("--port", type=int, default=5173, help="Port to serve on")
    parser.add_argument("--dev", action="store_true",
                        help="Run Vite dev server (default mode)")
    args = parser.parse_args()

    src = Path(args.race_file).resolve()
    if not src.exists():
        print(f"error: {src} not found", file=sys.stderr)
        return 1

    PUBLIC.mkdir(exist_ok=True)
    shutil.copy(src, PUBLIC / "race.jsonl.br")
    print(f"copied {src.name} -> {PUBLIC/'race.jsonl.br'}")

    if not args.dev:
        print("building app...")
        subprocess.run(["npm", "run", "build"], cwd=ROOT, check=True)
        DIST.mkdir(exist_ok=True)
        # Copy every log so each race is loadable from the static server.
        for f in PUBLIC.glob("*.jsonl.br"):
            shutil.copy(f, DIST / f.name)
            print(f"copied {f.name} -> {DIST / f.name}")
        print(f"serving static build on :{args.port}")
        handler = lambda *a, **kw: RaceHandler(*a, directory=DIST, **kw)  # noqa: E731
        httpd = ThreadingHTTPServer(("0.0.0.0", args.port), handler)
        print("Serving on http://localhost:{}".format(args.port))
        httpd.serve_forever()
        return 0

    print(f"starting Vite dev server on http://localhost:{args.port}")
    return subprocess.run(
        ["npm", "run", "dev", "--", "--port", str(args.port), "--host"],
        cwd=ROOT,
    ).returncode


if __name__ == "__main__":
    sys.exit(main())
