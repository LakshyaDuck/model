# No backups in v1

Session files and SQLite live only on the VM's `/data` volume. There is no snapshot, object-store copy, or export job. A destroyed instance or wiped disk loses every capture. We accept that for a free-tier prototype; adding backups later is a new decision.
