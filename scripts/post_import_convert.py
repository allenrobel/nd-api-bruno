#!/usr/bin/env python3
"""
post_import_convert.py

Converts a freshly-imported Bruno collection from the native OpenAPI
{{baseUrl}} URL format to the project's standard format using
{{controllerProtocol}}{{controllerIp}}{{<pathVar>}}.

Idempotent: safe to run multiple times on the same collection.

Usage:
    python scripts/post_import_convert.py "Nexus Dashboard OneManage v1"
    python scripts/post_import_convert.py "Nexus Dashboard Infrastructure v1" --path-var infraPath

What it does:
    1. Replaces {{baseUrl}} -> {{controllerProtocol}}{{controllerIp}}{{<pathVar>}}
       in all .yml request files (also converts {{basePath}} -> {{<pathVar>}}
       for previously converted collections)
    2. Removes basePath/baseUrl from the collection environment file
       (these are now defined in the Global environment)
    3. Adds the collection-level auth token pre-request script and bearer
       auth to opencollection.yml (skips if already present)
    4. Replaces per-request oauth2 auth blocks with auth: inherit so
       requests inherit bearer auth from the collection level
"""

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

# Mapping from basePath suffix to the global path variable name
PATH_SUFFIX_MAP = {
    "/infra": "infraPath",
    "/manage": "managePath",
    "/oneManage": "oneManagePath",
    "/analyze": "analyzePath",
}

OLD_BASE_URL = "{{baseUrl}}"
OLD_BASE_PATH = "{{basePath}}"

# Regex matching the oauth2 auth block that Bruno generates from OpenAPI imports
OAUTH2_AUTH_PATTERN = re.compile(
    r"  auth:\n"
    r"    type: oauth2\n"
    r"    flow: implicit\n"
    r"    authorizationUrl: https://example\.com/login\n"
    r'    callbackUrl: "\{\{oauth_callback_url\}\}"\n'
    r"    credentials:\n"
    r'      clientId: "\{\{oauth_client_id\}\}"\n'
    r"    scope: observer fabric-admin support-engineer super-admin approver designer\n"
    r'    state: "\{\{oauth_state\}\}"\n'
    r"    tokenConfig:\n"
    r"      placement:\n"
    r"        header: Bearer\n"
    r"    settings:\n"
    r"      autoFetchToken: false\n"
    r"      autoRefreshToken: true\n"
)

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
  auth:
    type: bearer
    token: "{{{{nd_auth_token}}}}"
  scripts:
    - type: before-request
      code: |-
        {script_indented}
bundled: false
extensions: {{}}
"""


def detect_path_var(collection_dir: Path, explicit_path_var: str | None) -> str:
    """Determine the correct path variable for this collection.

    Priority: --path-var CLI arg > environment file basePath/baseUrl > error.
    """
    if explicit_path_var:
        return explicit_path_var

    env_dir = collection_dir / "environments"
    if env_dir.is_dir():
        for env_file in env_dir.glob("*.yml"):
            content = env_file.read_text()
            # Try to find a basePath or baseUrl value
            base_path_value = _extract_env_var_value(content, "basePath")
            if base_path_value:
                return _suffix_to_path_var(base_path_value)

            base_url_value = _extract_env_var_value(content, "baseUrl")
            if base_url_value:
                parsed = urlparse(base_url_value)
                return _suffix_to_path_var(parsed.path)

    print("Error: Could not auto-detect path variable from environment file.")
    print("       Use --path-var to specify it explicitly.")
    sys.exit(1)


def _extract_env_var_value(content: str, var_name: str) -> str | None:
    """Extract the value of a named variable from a Bruno environment YAML."""
    lines = content.splitlines()
    for i, line in enumerate(lines):
        if f"name: {var_name}" in line:
            for j in range(i + 1, len(lines)):
                if "value:" in lines[j]:
                    return lines[j].split("value:", 1)[1].strip()
            break
    return None


def _suffix_to_path_var(path: str) -> str:
    """Map a full path like /api/v1/infra to its path variable name."""
    for suffix, var_name in PATH_SUFFIX_MAP.items():
        if path.endswith(suffix):
            return var_name
    print(f"Error: Unknown path suffix in '{path}'.")
    print(f"       Known suffixes: {list(PATH_SUFFIX_MAP.keys())}")
    print("       Use --path-var to specify the variable explicitly.")
    sys.exit(1)


def replace_urls(collection_dir: Path, path_var: str) -> tuple[int, int]:
    """Replace {{baseUrl}} and {{basePath}} with the collection-specific path variable."""
    new_var = "{{controllerProtocol}}{{controllerIp}}{{" + path_var + "}}"
    old_base_path_var = "{{basePath}}"
    new_path_var = "{{" + path_var + "}}"

    converted = 0
    skipped = 0

    for yml_file in collection_dir.rglob("*.yml"):
        if "environments" in yml_file.parts:
            continue
        if yml_file.name == "opencollection.yml":
            continue

        content = yml_file.read_text()
        new_content = content

        # Replace {{baseUrl}} (fresh import)
        if OLD_BASE_URL in new_content:
            new_content = new_content.replace(OLD_BASE_URL, new_var)

        # Replace {{basePath}} with collection-specific variable (re-conversion)
        if old_base_path_var in new_content:
            new_content = new_content.replace(old_base_path_var, new_path_var)

        if new_content != content:
            yml_file.write_text(new_content)
            converted += 1
        else:
            skipped += 1

    return converted, skipped


def convert_environment(collection_dir: Path) -> None:
    """Clean up environment file: remove basePath/baseUrl (now in Global env)."""
    env_dir = collection_dir / "environments"
    if not env_dir.is_dir():
        print("Step 2: No environments/ directory found — skipping")
        return

    for env_file in env_dir.glob("*.yml"):
        content = env_file.read_text()

        has_base_url = "name: baseUrl" in content
        has_base_path = "name: basePath" in content

        if not has_base_url and not has_base_path:
            print("Step 2: Environment file")
            print(f"  Skipped (already clean): {env_file.name}")
            return

        # Extract just the environment name
        env_name = None
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("name:") and env_name is None:
                env_name = stripped.split("name:", 1)[1].strip()

        if not env_name:
            env_name = env_file.stem

        # Write a clean env file with just the name (path vars are global now)
        env_file.write_text(f"name: {env_name}\n")

        print("Step 2: Environment file")
        print(f"  Updated: {env_file.name}")
        print("  Removed basePath/baseUrl (now in Global environment)")


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


def replace_oauth2_auth(collection_dir: Path) -> tuple[int, int]:
    """Replace per-request oauth2 auth blocks with auth: inherit."""
    converted = 0
    skipped = 0

    for yml_file in collection_dir.rglob("*.yml"):
        if "environments" in yml_file.parts:
            continue
        if yml_file.name == "opencollection.yml":
            continue

        content = yml_file.read_text()

        if "type: oauth2" in content:
            new_content = OAUTH2_AUTH_PATTERN.sub("  auth: inherit\n", content)
            if new_content != content:
                yml_file.write_text(new_content)
                converted += 1
            else:
                print(f"  Warning: oauth2 block did not match expected pattern in {yml_file.name}")
                skipped += 1
        else:
            skipped += 1

    return converted, skipped


def main():
    parser = argparse.ArgumentParser(
        description="Convert an imported Bruno collection to use standard URL variables."
    )
    parser.add_argument(
        "collection",
        help='Collection directory name (e.g., "Nexus Dashboard OneManage v1")',
    )
    parser.add_argument(
        "--path-var",
        help="Path variable name to use (e.g., infraPath, managePath, oneManagePath). "
             "Auto-detected from environment file if not specified.",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    collection_dir = repo_root / args.collection

    if not collection_dir.is_dir():
        print(f"Error: Collection directory not found: {collection_dir}")
        sys.exit(1)

    # Detect path variable before modifying the environment file
    path_var = detect_path_var(collection_dir, args.path_var)
    print(f"Converting collection: {args.collection}")
    print(f"Path variable: {{{{{path_var}}}}}\n")

    # Step 1
    converted, skipped = replace_urls(collection_dir, path_var)
    print("Step 1: URL replacement")
    print(f"  Converted: {converted} files")
    print(f"  Skipped (already converted): {skipped} files")
    print()

    # Step 2
    convert_environment(collection_dir)
    print()

    # Step 3
    add_prerequest_script(collection_dir)
    print()

    # Step 4
    converted, skipped = replace_oauth2_auth(collection_dir)
    print("Step 4: Auth replacement (oauth2 -> inherit)")
    print(f"  Converted: {converted} files")
    print(f"  Skipped (already converted): {skipped} files")

    print(f"\nDone. Collection '{args.collection}' has been converted.")


if __name__ == "__main__":
    main()
