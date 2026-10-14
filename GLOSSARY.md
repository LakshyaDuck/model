# Capture

Phase 1 of the 3D room-reconstruction system: a laptop and a phone share one capture job through the server. They never talk to each other.

## Language

**Public origin**:
The HTTPS hostname everyone actually visits. Today that is `https://shares.qzz.io`.
_Avoid_: base URL, site URL, server URL, Render URL

**Capture stack**:
The live phase-1 system: API, resumable uploads, laptop page, and phone page. The Vite app is not part of it yet.
_Avoid_: the frontend, the full app, the site (when you mean only the React tree)

**Session**:
One capture job: one laptop, one phone, and the files uploaded for that job.
_Avoid_: room, project, upload

**Owner token**:
The secret returned once to the laptop. It can read the session.
_Avoid_: admin token, API key

**Pair token**:
The short-lived, upload-only secret in the QR URL. It cannot read the session.
_Avoid_: QR token, invite code

**Phone page**:
The page the phone opens after scanning the QR. It may only create uploads for that session.
_Avoid_: mobile app, camera page (the React `/camerapic` route is not this)

**Laptop page**:
The page the laptop uses to start a session, show the QR, and watch assets arrive. On the public origin this is `/`.
_Avoid_: dashboard, admin, home (the React `/` route is not this)

**Asset**:
One file in a session (video, photo, floor plan, or sensor file).
_Avoid_: upload, media, attachment

**Manifest**:
The derived listing of a session's assets for the next pipeline stage.
_Avoid_: inventory, catalog
