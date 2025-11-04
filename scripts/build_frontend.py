#!/usr/bin/env python3
"""
Build the React frontend and copy the output into the FastAPI static directory.

Usage:
    python scripts/build_frontend.py
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = REPO_ROOT / "visual_controller" / "frontend"
STATIC_DIR = REPO_ROOT / "visual_controller" / "static"


def run(command: Sequence[str], *, cwd: Path) -> None:
    print(f"[build_frontend] Running {' '.join(command)} (cwd={cwd})")
    subprocess.run(command, check=True, cwd=cwd)


def main() -> None:
    if not FRONTEND_DIR.exists():
        raise SystemExit(f"Frontend directory not found: {FRONTEND_DIR}")

    run(["npm", "install"], cwd=FRONTEND_DIR)
    run(["npm", "run", "build"], cwd=FRONTEND_DIR)

    dist_dir = FRONTEND_DIR / "dist"
    if not dist_dir.exists():
        raise SystemExit("Build output not found (expected dist/ directory).")

    if STATIC_DIR.exists():
        print(f"[build_frontend] Removing existing static directory: {STATIC_DIR}")
        shutil.rmtree(STATIC_DIR)

    print(f"[build_frontend] Copying {dist_dir} -> {STATIC_DIR}")
    shutil.copytree(dist_dir, STATIC_DIR)
    print("[build_frontend] Done.")


if __name__ == "__main__":
    main()
