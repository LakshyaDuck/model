# Single always-free VM, not Render

The capture stack is two processes (API and tusd) that must share one disk so a finished upload is a rename, and one public origin so the phone can reach both the phone page and `/files/`. Render's free web service gives one public port, no persistent disk, and cannot share a disk across services — so it cannot host this. We deploy one always-free VM behind `https://shares.qzz.io` instead, and we do not ship the Vite frontend until it speaks sessions and tus.
