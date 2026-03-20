---
name: import-collection
description: "Import an OpenAPI schema into a new Bruno collection and run post-import conversion"
disable-model-invocation: true
---

# Import Collection

Import a Nexus Dashboard OpenAPI schema into a Bruno collection and convert it to project conventions.

## Arguments

- `schema_file` (required): Path to the OpenAPI JSON schema file (e.g., `schemas/4.2.1.10/manage.json`)
- `collection_name` (required): Name for the Bruno collection directory (e.g., `"Nexus Dashboard Manage v1"`)
- `--path-var` (optional): Path variable override (e.g., `infraPath`, `managePath`). Auto-detected if omitted.

## Workflow

1. **Validate the schema** exists at the given path
2. **Instruct the user** to import the schema in Bruno's desktop app:
   - Click '+' in the Collections bar
   - Select "Import collection"
   - Choose the schema JSON file
   - Save into the repo root as the given collection name
3. **Wait for user confirmation** that the Bruno import is complete
4. **Run the post-import conversion script**:
   ```bash
   python scripts/post_import_convert.py "<collection_name>" [--path-var <var>]
   ```
5. **Verify** the conversion succeeded:
   - Check that `opencollection.yml` has bearer auth and before-request script
   - Check that request files use `{{controllerProtocol}}{{controllerIp}}{{<pathVar>}}` URLs
   - Check that request files use `auth: inherit`
   - Check that the environment file is clean (no basePath/baseUrl)
6. **Report results** to the user

## Path Variable Mapping

| Path Suffix | Variable |
|---|---|
| `/infra` | `infraPath` |
| `/manage` | `managePath` |
| `/oneManage` | `oneManagePath` |
| `/analyze` | `analyzePath` |

## Notes

- The conversion script is idempotent and safe to re-run
- Schema JSON files should be saved under `schemas/<version>/` (e.g., `schemas/4.2.1.10/manage.json`)
- After conversion, review the git diff to verify changes look correct before committing
