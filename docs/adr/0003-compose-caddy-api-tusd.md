# Superseded — VM Compose topology

**Status:** Superseded on 2026-10-17 by
[ADR 0008](0008-local-only-pending-hosting.md).

The Oracle VM and public TLS deployment described here are dropped. The same
gateway/API/tusd separation and shared `/data` volume remain the local Compose
topology; see `compose.yaml`. A hosted topology will be chosen later, if needed.
