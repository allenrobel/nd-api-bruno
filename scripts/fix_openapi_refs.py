#!/usr/bin/env python3
"""
fix_openapi_refs.py

Fixes OpenAPI 3.0.x schemas for compatibility with strict validators and
Bruno 3.1+ imports. Applies two categories of fixes:

A. $ref-with-siblings violations (invalid per OpenAPI 3.0.x spec):

   1. Schema properties: wraps $ref in allOf, keeps valid JSON Schema siblings
      alongside. Non-schema siblings (like custom properties) are folded into
      the allOf as additional inline schema properties.

   2. Parameter objects: resolves the $ref inline and merges sibling overrides,
      since parameters don't support allOf composition.

   3. Response objects: resolves the $ref inline and merges example/examples
      into the response content.

   4. Media type schema objects: when a schema has $ref + examples, resolves
      the $ref and converts examples to a single example on the media type.

B. Tag name sanitization for Bruno compatibility:

   5. Replaces characters in tag names that are invalid per Bruno's tag regex
      (only alphanumeric, spaces, hyphens, and underscores allowed).
      e.g., "Access/ToR Associations" -> "Access-ToR Associations"

Idempotent: safe to run multiple times on the same file.

Usage:
    python scripts/fix_openapi_refs.py schemas/4.2.1.10/manage_download.json
    python scripts/fix_openapi_refs.py schemas/4.2.1.10/manage_download.json -o schemas/4.2.1.10/manage_fixed.json
"""

import argparse
import copy
import json
import re
import sys
from pathlib import Path

# Bruno's tag validation regex — only alphanumeric, spaces, hyphens, underscores
BRUNO_TAG_RE = re.compile(r"^[\w-][\w\s-]*[\w-]$|^[\w-]+$")

# Valid JSON Schema / OpenAPI 3.0 Schema Object keywords that can appear
# alongside allOf without causing validation errors.
SCHEMA_KEYWORDS = frozenset({
    "allOf", "oneOf", "anyOf", "not", "type", "properties", "items",
    "required", "enum", "description", "example", "default", "format",
    "minimum", "maximum", "minLength", "maxLength", "pattern", "title",
    "additionalProperties", "minItems", "maxItems", "uniqueItems",
    "readOnly", "writeOnly", "nullable", "deprecated", "multipleOf",
    "exclusiveMinimum", "exclusiveMaximum", "minProperties", "maxProperties",
    "xml", "externalDocs", "discriminator",
})


def resolve_ref(spec: dict, ref: str) -> dict | None:
    """Resolve a JSON $ref pointer within the spec."""
    if not ref.startswith("#/"):
        return None
    parts = ref[2:].split("/")
    node = spec
    for part in parts:
        part = part.replace("~1", "/").replace("~0", "~")
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return None
    return copy.deepcopy(node) if isinstance(node, dict) else None


def ref_target_type(ref: str) -> str:
    """Classify the $ref target: 'parameter', 'response', 'schema', or 'other'."""
    if "#/components/parameters/" in ref:
        return "parameter"
    if "#/components/responses/" in ref:
        return "response"
    if "#/components/schemas/" in ref:
        return "schema"
    return "other"


def fix_ref_siblings(obj: object, spec: dict, parent_key: str = "") -> tuple[object, int]:
    """Recursively fix $ref objects that have sibling properties.

    Returns the (possibly modified) object and a count of fixes applied.
    """
    if isinstance(obj, list):
        fixes = 0
        result = []
        for item in obj:
            fixed, n = fix_ref_siblings(item, spec, parent_key)
            result.append(fixed)
            fixes += n
        return result, fixes

    if not isinstance(obj, dict):
        return obj, 0

    fixes = 0

    # First, recurse into all values
    result = {}
    for key, value in obj.items():
        fixed, n = fix_ref_siblings(value, spec, key)
        result[key] = fixed
        fixes += n

    # Post-recursion: pick up hoisted example from schema child.
    if "schema" in result and isinstance(result["schema"], dict):
        hoisted = result["schema"].pop("__hoisted_example", None)
        if hoisted is not None and "example" not in result and "examples" not in result:
            result["example"] = hoisted

    # Now check if this dict has $ref with siblings
    if "$ref" not in result or len(result) <= 1:
        return result, fixes

    # Already wrapped in allOf — skip (idempotent)
    if "allOf" in result:
        return result, fixes

    ref = result["$ref"]
    siblings = {k: v for k, v in result.items() if k != "$ref"}
    target_type = ref_target_type(ref)

    if target_type == "parameter":
        # Resolve inline and merge
        resolved = resolve_ref(spec, ref)
        if resolved is not None:
            resolved.update(siblings)
            return resolved, fixes + 1

    elif target_type == "response":
        # Resolve inline and merge example(s) into content
        resolved = resolve_ref(spec, ref)
        if resolved is not None:
            examples = siblings.pop("examples", None)
            example = siblings.pop("example", None)
            resolved.update(siblings)
            if examples or example:
                content = resolved.get("content", {})
                for _media_type, media_obj in content.items():
                    if examples and "examples" not in media_obj:
                        media_obj["examples"] = examples
                    if example and "example" not in media_obj:
                        media_obj["example"] = example
            return resolved, fixes + 1

    elif target_type == "schema" and parent_key == "schema":
        # Schema inside a media type object (content/application/json/schema).
        # examples/example don't belong on schema objects — stash for parent.
        examples_val = siblings.pop("examples", None)
        example_val = siblings.pop("example", None)

        if siblings:
            new_result = _wrap_schema_ref(ref, siblings)
        else:
            new_result = {"$ref": ref}

        # Stash as single example for parent media type to pick up
        if examples_val is not None:
            new_result["__hoisted_example"] = examples_val
        elif example_val is not None:
            new_result["__hoisted_example"] = example_val

        return new_result, fixes + 1

    elif target_type == "schema":
        return _wrap_schema_ref(ref, siblings), fixes + 1

    else:
        # Generic fallback: wrap in allOf
        ref_value = result.pop("$ref")
        result = {"allOf": [{"$ref": ref_value}], **result}
        return result, fixes + 1

    # If resolution failed, return as-is
    return result, fixes


def _wrap_schema_ref(ref: str, siblings: dict) -> dict:
    """Wrap a schema $ref in allOf, handling non-standard siblings.

    Standard JSON Schema keywords stay alongside allOf.
    Non-standard keywords (custom properties like 'severities') get folded
    into the allOf as properties of an additional inline schema object.
    """
    standard = {}
    non_standard = {}

    for key, value in siblings.items():
        if key in SCHEMA_KEYWORDS or key.startswith("x-"):
            standard[key] = value
        else:
            non_standard[key] = value

    allof_items = [{"$ref": ref}]

    if non_standard:
        # Fold non-standard siblings as properties of an inline schema
        allof_items.append({
            "type": "object",
            "properties": non_standard,
        })

    return {"allOf": allof_items, **standard}


def sanitize_tags(spec: dict) -> int:
    """Replace invalid characters in tag names for Bruno compatibility.

    Bruno tags must match: /^[\\w-][\\w\\s-]*[\\w-]$|^[\\w-]+$/
    Characters like '/' are replaced with '-'.

    Also updates tag references in operation objects to match.
    """
    tag_renames = {}

    for tag in spec.get("tags", []):
        name = tag["name"]
        if not BRUNO_TAG_RE.match(name):
            # Replace any character that isn't word char, space, or hyphen
            sanitized = re.sub(r"[^\w\s-]", "-", name)
            tag_renames[name] = sanitized
            tag["name"] = sanitized

    if not tag_renames:
        return 0

    # Update tag references in all operations
    for _path, methods in spec.get("paths", {}).items():
        for _method, details in methods.items():
            if not isinstance(details, dict):
                continue
            op_tags = details.get("tags", [])
            for i, tag in enumerate(op_tags):
                if tag in tag_renames:
                    op_tags[i] = tag_renames[tag]

    return len(tag_renames)


def main():
    parser = argparse.ArgumentParser(
        description="Fix $ref-with-siblings violations in OpenAPI 3.0.x schemas."
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

    fixed_spec, ref_fix_count = fix_ref_siblings(spec, spec)
    tag_fix_count = sanitize_tags(fixed_spec)
    fix_count = ref_fix_count + tag_fix_count

    if fix_count == 0:
        print("No issues found. File is already clean.")
        return

    output_path = Path(args.output) if args.output else schema_path
    with open(output_path, "w") as f:
        json.dump(fixed_spec, f, indent=2)
        f.write("\n")

    if ref_fix_count:
        print(f"Fixed {ref_fix_count} $ref-with-siblings violations.")
    if tag_fix_count:
        print(f"Sanitized {tag_fix_count} tag name(s) for Bruno compatibility.")
    print(f"Output written to: {output_path}")


if __name__ == "__main__":
    main()
