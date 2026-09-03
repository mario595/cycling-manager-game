#!/usr/bin/env python3
"""Serve the race player UI along with a race.jsonl log file.

Usage:
    python serve_viewer.py [race.jsonl] [--port 5173] [--dev]

By default this starts the Vite dev server (hot reload). With --dev it copies
the given JSONL into public/ so it's served at /race.jsonl.

Without --dev it builds the app and serves the static output plus the JSONL.
"""
import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "public"
DIST = ROOT / "dist"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("race_file", nargs="?", default="race.jsonl",
                        help="Path to the race.jsonl (default: ./race.jsonl)")
    parser.add_argument("--port", type=int, default=5173, help="Port to serve on")
    parser.add_argument("--dev", action="store_true",
                        help="Run Vite dev server (default mode)")
    args = parser.parse_args()

    src = Path(args.race_file).resolve()
    if not src.exists():
        print(f"error: {src} not found", file=sys.stderr)
        return 1

    PUBLIC.mkdir(exist_ok=True)
    shutil.copy(src, PUBLIC / "race.jsonl")
    print(f"copied {src.name} -> {PUBLIC/'race.jsonl'}")

    if not args.dev:
        print("building app...")
        subprocess.run(["npm", "run", "build"], cwd=ROOT, check=True)
        shutil.copy(src, DIST / "race.jsonl")
        print(f"serving static build on :{args.port}")
        subprocess.run(
            [sys.executable, "-m", "http.server", str(args.port)],
            cwd=DIST,
            check=True,
        )
        return 0

    print(f"starting Vite dev server on http://localhost:{args.port}")
    return subprocess.run(
        ["npm", "run", "dev", "--", "--port", str(args.port), "--host"],
        cwd=ROOT,
    ).returncode


if __name__ == "__main__":
    sys.exit(main())
