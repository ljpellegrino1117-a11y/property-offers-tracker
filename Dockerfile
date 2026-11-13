# Use the same Caddy version as the prior Railpack deployment, without
# depending on a runtime download of the Railpack build driver.
FROM caddy:2.11.7-alpine@sha256:e70b164da81ef698b3ad19af799ea6086ce6d9e48ed4079eb9fe26f6fbf14ee5
COPY Caddyfile /etc/caddy/Caddyfile
COPY index.html /srv/index.html
RUN caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
