#!/usr/bin/env python3
"""
fix_openapi_tags.py

Sanitizes OpenAPI tag names for Bruno compatibility.

Bruno's tag regex only allows alphanumeric characters, spaces, hyphens,
and underscores. Characters like '/' are replaced with '-'.

    e.g., "Access/ToR Associations" -> "Access-ToR Associations"

Also updates tag references in operation objects to match.

Idempotent: safe to run multiple times on the same file.

Usage:
    python scripts/fix_openapi_tags.py schemas/4.2.1.10/manage_download.json
    python scripts/fix_openapi_tags.py schemas/4.2.1.10/manage_download.json -o schemas/4.2.1.10/manage_tags_fixed.json
"""

import argparse
import json
import re
import sys
from pathlib import Path

BRUNO_TAG_RE = re.compile(r"^[\w-][\w\s-]*[\w-]$|^[\w-]+$")


def sanitize_tags(spec: dict) -> int:
    """Replace invalid characters in tag names for Bruno compatibility."""
    tag_renames = {}

    for tag in spec.get("tags", []):
        name = tag["name"]
        if not BRUNO_TAG_RE.match(name):
            sanitized = re.sub(r"[^\w\s-]", "-", name)
            tag_renames[name] = sanitized
            tag["name"] = sanitized

    if not tag_renames:
        return 0

    for _path, methods in spec.get("paths", {}).items():
        for _method, details in methods.items():
            if not isinstance(details, dict):
                continue
            op_tags = details.get("tags", [])
            for i, tag in enumerate(op_tags):
                if tag in tag_renames:
                    op_tags[i] = tag_renames[tag]

    for old, new in tag_renames.items():
        print(f'  "{old}" -> "{new}"')

    return len(tag_renames)


def main():
    parser = argparse.ArgumentParser(
        description="Sanitize OpenAPI tag names for Bruno compatibility."
    )
    parser.add_argument(
        "schema",
        help="Path to the OpenAPI JSON schema file",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Output file path (default: overwrite input file)",
    )
    args = parser.parse_args()

    schema_path = Path(args.schema)
    if not schema_path.is_file():
        print(f"Error: File not found: {schema_path}")
        sys.exit(1)

    with open(schema_path) as f:
        try:
            spec = json.load(f)
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON: {e}")
            sys.exit(1)

    fix_count = sanitize_tags(spec)

    if fix_count == 0:
        print("No invalid tag names found. File is already clean.")
        return

    output_path = Path(args.output) if args.output else schema_path
    with open(output_path, "w") as f:
        json.dump(spec, f, indent=2)
        f.write("\n")

    print(f"Sanitized {fix_count} tag name(s).")
    print(f"Output written to: {output_path}")


if __name__ == "__main__":
    main()
