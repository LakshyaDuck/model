# Superseded — single VM, not Render

**Status:** Superseded on 2026-10-17 by
[ADR 0008](0008-local-only-pending-hosting.md).

The planned public VM deployment is no longer viable: Oracle Cloud requires credit
card verification and the project does not have a card to use. Do not use this record
to select Render, Oracle, a domain, or any other production host. The capture stack's
shared-volume and single-origin requirements remain documented in `compose.yaml` and
`docs/system-design.md` for a future hosting decision.
