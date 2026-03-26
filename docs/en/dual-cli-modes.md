# Dual CLI Modes (Local + Control Plane Client)

## 1. Why split the CLI

CertMan serves two primary user groups:

1. Local-first users: issue, renew, export, and check certificates on a single host
2. Platform operators: query and manage resources through control-plane APIs

To reduce cognitive load, CLI responsibilities are split:

- `certman`: local operator CLI
- `certmanctl`: remote control-plane client CLI

## 2. Components and entry points

1. `certman`

- Local-only operations (keeps existing behavior)

1. `certmanctl`

- Docker-client-like UX for calling `certman-server` REST endpoints

1. `certman-server`

- Control-plane API service

1. `certman-worker`

- Background job processor

1. `certman-agent`

- Node-side agent (register, poll, report)

## 3. Deployment shapes

### Native single-host

- Use `certman` only

### Containerized

- Run `server + worker` in compose
- Use `certmanctl` for remote operations

### Distributed

- Run `server + worker + agent`
- Use `certmanctl` for operational control and automation

## 4. Command boundaries

### certman (local)

- entries
- new
- renew
- export
- check
- config-validate
- logs-clean

### certmanctl (remote)

- health
- cert create
- cert list
- cert get
- cert renew
- job get
- job list
- job wait
- webhook create
- webhook list
- webhook get
- webhook update
- webhook delete

## 5. Compatibility policy

1. Keep `certman` backward-compatible with existing scripts
2. Put all remote control-plane interactions into `certmanctl`
3. Avoid semantic ambiguity by separating entry points

## 6. Current stage

The dual-CLI split is now implemented for the current remote control-plane MVP.

Current remote operator surfaces:

- `certmanctl`: stable entrypoint for control-plane REST calls
- `/docs`, `/redoc`, `/openapi.json`: live OpenAPI documentation from `certman-server`

Current AI integration options:

- MCP via `certman-mcp` (stdio transport)
- REST + OpenAPI for direct HTTP integrations

Program document:

- `docs/notes/plans/2026-03-26-dual-cli-program.md`
