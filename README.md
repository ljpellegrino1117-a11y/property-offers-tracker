# Property Offer Tracker — public snapshot

Static public snapshot of the Illinois New Realty Holdings property offer
tracker board: pipeline counts, per-property cards (ask, our offer, unit mix,
three-way cash-on-cash panel, dates) and the under-contract deadlines board.

This page is a snapshot, regenerated from the live tracker by
`publish_snapshot.py` (kept in the Muse workspace, not in this repo). The
generator publishes display fields only — no internal notes, no MLS numbers,
no agent contact details, no file paths — and fails its audit if any of those
patterns survive into the HTML.

## Railway deployment

Railway automatically detects the root `Dockerfile`. The image serves only
`index.html` using official Caddy 2.11.7, pinned by digest. It listens on Railway's
`PORT` (8080 when unset), with TLS terminated by Railway. The Docker build validates
the Caddy configuration. This avoids fetching a Railpack build driver for each
snapshot update; `publish_snapshot.py` remains unchanged.

After deployment, verify Railway reports `SUCCESS` and the live root page matches
`index.html` from the deployed commit. `/publish_snapshot.py` and `/README.md`
should return 404 because only the public snapshot is copied into the image.
