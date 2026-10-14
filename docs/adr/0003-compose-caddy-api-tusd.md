# Three containers on the VM: Caddy, API, tusd

On the Oracle VM we run docker compose with three services and one persistent `/data` volume (~50 GB). Caddy terminates TLS for `shares.qzz.io`, sends `/files/*` to tusd, blocks `/internal/*`, and sends everything else to the API. We do not collapse this into one image: the processes stay separate; the proxy is what makes them one public origin.
