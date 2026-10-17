# No automated backups during local development

**Status:** Accepted on 2026-10-17.

Session files and SQLite live in the local Compose data volume. There is no snapshot,
object-store copy, or export job. Clearing Docker volumes or losing the development
machine loses captures. Add a backup decision before any hosted or durable deployment.
