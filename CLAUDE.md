# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Repo Is

Bruno API collections for the **Cisco Nexus Dashboard** REST APIs. Bruno (opencollection 1.0.0 format) is a Git-friendly, file-based alternative to Postman. Each `.yml` file is a single API request.

## Collections

- `Nexus Dashboard Infrastructure v1/` — base path `/api/v1/infra`, ~296 endpoints; system management: health, certs, auth, backups, integrations
- `Nexus Dashboard Manage v1/` — base path `/api/v1/manage`, ~519 endpoints; fabric/network management: ACI/DCNM fabrics, inventory, policies
- `Schema/` — shared OpenAPI schema (`infra.json`) and Login request

## File Format

Each request is a `.yml` file:

```yaml
info:
  name: <Request Name>
  type: http
  seq: <ordering number>

http:
  method: GET|POST|PUT|DELETE
  url: "{{controllerProtocol}}{{controllerIp}}{{basePath}}/some/path"
  body:
    type: json
    data: |-
      { ... }
  auth: inherit
```

`opencollection.yml` at the collection root defines collection-level before-request scripts (injects `Authorization: Bearer {{nd_auth_token}}` on all non-login requests).

## Environment Variables

Defined in `environments/*.yml` within each collection. Key variables:

- `controllerProtocol` — `https://` or `http://`
- `controllerIp` — Target Nexus Dashboard IP/hostname
- `basePath` — `/api/v1/infra` or `/api/v1/manage`
- `nd_username` / `nd_password` / `nd_domain` — Login credentials
- `nd_auth_token` — Bearer token (auto-set after Login request)
- `nd_token_expires` — Token expiration (auto-set after Login request)

## Authentication Flow

1. Run `Login.yml` in the target collection — POSTs to `/login` with credentials
2. The after-response script captures `data.token` → stores in `nd_auth_token`
3. All subsequent requests automatically include `Authorization: Bearer <token>` via the collection-level before-request script

## Adding or Modifying Requests

- Place new `.yml` files in the appropriate category subfolder
- Use `seq` to control ordering within a folder
- URL must use `{{controllerProtocol}}{{controllerIp}}{{basePath}}` prefix
- Set `auth: inherit` so the collection-level token injection applies
- Include example request/response bodies in `docs:` or as `body.data`

## Folder Structure Convention

Each collection folder corresponds to an API category (e.g., `Fabric Management/`, `Certificate Management/`). Requests are grouped by resource, not HTTP method.
