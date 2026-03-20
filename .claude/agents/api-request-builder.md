# API Request Builder

Build Bruno YAML request files from Nexus Dashboard OpenAPI endpoint definitions.

## Purpose

Generate properly formatted Bruno request `.yml` files by querying the nd-openapi MCP server for endpoint details and schemas.

## Workflow

1. Use `mcp__nd-openapi__search_endpoints` or `mcp__nd-openapi__list_endpoints` to find the target endpoint
2. Use `mcp__nd-openapi__get_endpoint` to get full endpoint details (method, path, parameters, request/response body)
3. Use `mcp__nd-openapi__get_schema` to resolve any referenced data models
4. Generate a Bruno YAML request file following this format:

```yaml
info:
  name: <Descriptive Request Name>
  type: http
  seq: <next sequence number in folder>

http:
  method: <GET|POST|PUT|DELETE|PATCH>
  url: "{{controllerProtocol}}{{controllerIp}}{{<pathVar>}}<endpoint_path>"
  body:
    type: json
    data: |-
      <example request body from schema>
  auth: inherit
```

## Rules

- URL must use `{{controllerProtocol}}{{controllerIp}}{{<pathVar>}}` prefix where pathVar matches the API:
  - Infrastructure endpoints: `infraPath`
  - Manage endpoints: `managePath`
  - OneManage endpoints: `oneManagePath`
  - Analyze endpoints: `analyzePath`
- Always set `auth: inherit`
- Include example request body populated from the schema when the endpoint accepts a body
- Place the file in the appropriate category subfolder within the collection
- Use a descriptive `info.name` based on the endpoint's summary or description
- For path parameters, use Bruno template syntax: `{{paramName}}`
