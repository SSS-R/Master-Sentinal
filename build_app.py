"""Build Master Sentinal into a Windows executable with PyInstaller."""

from __future__ import annotations

import shutil
from pathlib import Path

import PyInstaller.__main__


ROOT = Path(__file__).resolve().parent
DIST_DIR = ROOT / "dist"
BUILD_DIR = ROOT / "build"
SPEC_PATH = ROOT / "Master Sentinal.spec"
OUTPUT_PATH = DIST_DIR / "Master Sentinal.exe"


def main() -> None:
    """Clean previous artifacts and run the PyInstaller spec."""
    for directory in (DIST_DIR, BUILD_DIR):
        if directory.exists():
            shutil.rmtree(directory)

    PyInstaller.__main__.run([
        str(SPEC_PATH),
        "--noconfirm",
        "--clean",
    ])

    if OUTPUT_PATH.exists():
        print(f"Build complete: {OUTPUT_PATH}")
    else:
        print("Build finished, but the executable was not found in dist.")


if __name__ == "__main__":
    main()
