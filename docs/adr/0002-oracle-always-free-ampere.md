# Oracle Always Free Ampere A1 as the deployment host

The capture stack needs an always-on VM with a disk and ports 80/443, at $0. Oracle's 30-day $300 offer is only the trial; Always Free compute has no end date if we stay at **2 OCPU / 12 GB** Ampere A1 from day one (the trial-sized 4 OCPU / 24 GB shape is reclaimed). We build linux/arm64 on the box. We do not use GCP's e2-micro: ~1 GB RAM is too small, and a public IPv4 is often not free.
