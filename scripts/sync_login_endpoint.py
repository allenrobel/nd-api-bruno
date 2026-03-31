#!/usr/bin/env python3
"""
sync_login_endpoint.py

Copies the 'User login.yml' endpoint from the Nexus Dashboard Infrastructure
collection into every other Nexus Dashboard collection so that users can
authenticate directly from any collection and have nd_auth_token set in that
collection's Runtime Vars.

The login endpoint lives under an Authentication/ subfolder in each target
collection.  The folder (and its folder.yml) are created automatically if
they don't already exist.

Idempotent: safe to run multiple times — only writes when the target is
missing or differs from the source.

Usage:
    python scripts/sync_login_endpoint.py
"""

import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

SOURCE_COLLECTION = "Nexus Dashboard Infrastructure v1"
SOURCE_FILE = REPO_ROOT / SOURCE_COLLECTION / "Authentication" / "User login.yml"

# Every other "Nexus Dashboard *" collection gets a copy
EXCLUDED = {SOURCE_COLLECTION}

FOLDER_YML_TEMPLATE = """\
info:
  name: Authentication
  type: folder
  seq: 1

request:
  auth: inherit
"""


def discover_collections() -> list[Path]:
    """Return paths of all Nexus Dashboard collections except the source."""
    return sorted(
        p
        for p in REPO_ROOT.iterdir()
        if p.is_dir()
        and p.name.startswith("Nexus Dashboard")
        and p.name not in EXCLUDED
    )


def ensure_folder_yml(auth_dir: Path) -> None:
    """Create or update Authentication/folder.yml to match the expected format."""
    folder_yml = auth_dir / "folder.yml"
    if not folder_yml.exists():
        folder_yml.write_text(FOLDER_YML_TEMPLATE)
        print(f"  Created {folder_yml.relative_to(REPO_ROOT)}")
    elif folder_yml.read_text() != FOLDER_YML_TEMPLATE:
        folder_yml.write_text(FOLDER_YML_TEMPLATE)
        print(f"  Updated {folder_yml.relative_to(REPO_ROOT)}")


def sync_login_endpoint() -> None:
    if not SOURCE_FILE.exists():
        print(f"Error: source file not found: {SOURCE_FILE}", file=sys.stderr)
        sys.exit(1)

    source_content = SOURCE_FILE.read_text()
    collections = discover_collections()

    if not collections:
        print("No target collections found.")
        return

    for collection in collections:
        name = collection.name
        auth_dir = collection / "Authentication"
        target = auth_dir / "User login.yml"

        auth_dir.mkdir(exist_ok=True)
        ensure_folder_yml(auth_dir)

        if not target.exists():
            shutil.copy2(SOURCE_FILE, target)
            print(f"[{name}] Copied User login.yml")
        elif target.read_text() != source_content:
            shutil.copy2(SOURCE_FILE, target)
            print(f"[{name}] Updated User login.yml (was out of date)")
        else:
            print(f"[{name}] User login.yml is up to date")


if __name__ == "__main__":
    sync_login_endpoint()
