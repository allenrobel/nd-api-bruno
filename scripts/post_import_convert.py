#!/usr/bin/env python3
"""
post_import_convert.py

Converts a freshly-imported Bruno collection from the native OpenAPI
{{baseUrl}} URL format to the project's standard format using
{{controllerProtocol}}{{controllerIp}}{{basePath}}.

Idempotent: safe to run multiple times on the same collection.

Usage:
    python scripts/post_import_convert.py "Nexus Dashboard OneManage v1"

What it does:
    1. Replaces {{baseUrl}} -> {{controllerProtocol}}{{controllerIp}}{{basePath}}
       in all .yml request files (skips files already converted)
    2. Rewrites the environment file: baseUrl -> basePath with the path
       extracted from the original baseUrl value (skips if already converted)
    3. Adds the collection-level auth token pre-request script to
       opencollection.yml (skips if already present)
"""

import argparse
import sys
from pathlib import Path
from urllib.parse import urlparse

OLD_VAR = "{{baseUrl}}"
NEW_VAR = "{{controllerProtocol}}{{controllerIp}}{{basePath}}"

BEFORE_REQUEST_SCRIPT = """\
// Skip token check for login request itself
if (req.getUrl().includes('/login')) {
  return;
}

// Check if token exists
const token = bru.getVar("nd_auth_token");
if (!token) {
  console.log("No auth token found. Please run the login request first.");
}"""

OPENCOLLECTION_TEMPLATE = """\
opencollection: 1.0.0

info:
  name: {collection_name}
config:
  proxy:
    inherit: true
    config:
      protocol: http
      hostname: ""
      port: ""
      auth:
        username: ""
        password: ""
      bypassProxy: ""

request:
  scripts:
    - type: before-request
      code: |-
        {script_indented}
bundled: false
extensions: {{}}
"""


def replace_urls(collection_dir: Path) -> tuple[int, int]:
    """Replace {{baseUrl}} with the standard variable format in all request .yml files."""
    converted = 0
    skipped = 0

    for yml_file in collection_dir.rglob("*.yml"):
        # Skip environment files and opencollection.yml
        if "environments" in yml_file.parts:
            continue
        if yml_file.name == "opencollection.yml":
            continue

        content = yml_file.read_text()

        if OLD_VAR in content:
            yml_file.write_text(content.replace(OLD_VAR, NEW_VAR))
            converted += 1
        else:
            skipped += 1

    return converted, skipped


def convert_environment(collection_dir: Path) -> None:
    """Rewrite environment files: replace baseUrl with basePath."""
    env_dir = collection_dir / "environments"
    if not env_dir.is_dir():
        print("Step 2: No environments/ directory found — skipping")
        return

    for env_file in env_dir.glob("*.yml"):
        content = env_file.read_text()

        if "name: baseUrl" not in content:
            print(f"Step 2: Environment file")
            print(f"  Skipped (already converted): {env_file.name}")
            return

        # Parse the baseUrl value and extract just the path
        env_name = None
        base_url_value = None
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("name:") and env_name is None:
                env_name = stripped.split("name:", 1)[1].strip()
            # Look for the value line that follows "name: baseUrl"
            if base_url_value is None and "name: baseUrl" in content:
                # Find the value on the line after "name: baseUrl"
                lines = content.splitlines()
                for i, l in enumerate(lines):
                    if "name: baseUrl" in l:
                        for j in range(i + 1, len(lines)):
                            if "value:" in lines[j]:
                                base_url_value = lines[j].split("value:", 1)[1].strip()
                                break
                        break

        if not base_url_value:
            print(f"  Warning: Could not extract baseUrl value from {env_file.name}")
            return

        # Extract path from URL (e.g., "https://example.com/api/v1/oneManage" -> "/api/v1/oneManage")
        parsed = urlparse(base_url_value)
        base_path = parsed.path

        if not base_path:
            print(f"  Warning: Could not extract path from baseUrl: {base_url_value}")
            return

        env_file.write_text(
            f"name: {env_name}\n"
            f"variables:\n"
            f"  - name: basePath\n"
            f"    value: {base_path}\n"
        )

        print(f"Step 2: Environment file")
        print(f"  Updated: {env_file.name}")
        print(f"  basePath: {base_path}")


def add_prerequest_script(collection_dir: Path) -> None:
    """Add the auth token pre-request script to opencollection.yml if not already present."""
    oc_file = collection_dir / "opencollection.yml"

    if not oc_file.is_file():
        print("Step 3: opencollection.yml not found — skipping")
        return

    content = oc_file.read_text()

    if "before-request" in content:
        print("Step 3: Pre-request script")
        print("  Skipped (already present in opencollection.yml)")
        return

    # Extract the collection name from the existing file
    collection_name = None
    for line in content.splitlines():
        if "name:" in line and collection_name is None:
            # Skip the opencollection: line; grab the first name: under info:
            stripped = line.strip()
            if stripped.startswith("name:"):
                collection_name = stripped.split("name:", 1)[1].strip()

    if not collection_name:
        collection_name = collection_dir.name

    # Indent the script block for the YAML |- block (8 spaces to align under code: |-)
    script_indented = BEFORE_REQUEST_SCRIPT.replace("\n", "\n        ")

    oc_file.write_text(
        OPENCOLLECTION_TEMPLATE.format(
            collection_name=collection_name,
            script_indented=script_indented,
        )
    )

    print("Step 3: Pre-request script")
    print("  Added auth token script to opencollection.yml")


def main():
    parser = argparse.ArgumentParser(
        description="Convert an imported Bruno collection to use standard URL variables."
    )
    parser.add_argument(
        "collection",
        help='Collection directory name (e.g., "Nexus Dashboard OneManage v1")',
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    collection_dir = repo_root / args.collection

    if not collection_dir.is_dir():
        print(f"Error: Collection directory not found: {collection_dir}")
        sys.exit(1)

    print(f"Converting collection: {args.collection}\n")

    # Step 1
    converted, skipped = replace_urls(collection_dir)
    print("Step 1: URL replacement")
    print(f"  Converted: {converted} files")
    print(f"  Skipped (already converted): {skipped} files")
    print()

    # Step 2
    convert_environment(collection_dir)
    print()

    # Step 3
    add_prerequest_script(collection_dir)

    print(f"\nDone. Collection '{args.collection}' has been converted.")


if __name__ == "__main__":
    main()
