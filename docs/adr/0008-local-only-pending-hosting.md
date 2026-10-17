# Local-only development pending viable hosting

**Status:** Accepted on 2026-10-17.

## Context

The previous deployment plan depended on Oracle Cloud Always Free. Oracle requires a
credit card during account signup, and the project does not have one available. The
assumption that an Oracle VM, public domain, and TLS configuration could be provisioned
is therefore invalid.

## Decision

Use the local Docker Compose stack as the only supported runtime for development and
demos. Do not provision an Oracle tenancy, VM, public DNS record, TLS certificate, or
public SSH access. For phone testing on the same network, set `PUBLIC_BASE_URL` to the
development laptop's LAN address.

The existing Compose boundaries remain intentional: Caddy is the gateway, FastAPI and
tusd share `DATA_DIR`, and `/internal/*` stays private. They make a future hosted
deployment possible without committing the project to a provider now.

## Consequences

- Remote users and phones outside the local network cannot use the capture flow.
- Public hosting is deferred, not designed around an unverified free-tier provider.
- A future host selection must explicitly cover account eligibility, persistent shared
  storage, one public origin for API and tus uploads, secret handling, and backups.
