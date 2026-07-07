# syntax=docker/dockerfile:1

FROM ubuntu:24.04

ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends coreutils socat \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --home-dir /home/ctf --shell /usr/sbin/nologin ctf

WORKDIR /home/ctf

COPY --chmod=0555 dist/artifact-11 ./artifact-11
COPY --chmod=0444 service/flag.txt ./flag.txt

COPY <<'EOF' /usr/local/bin/launch-artifact-11
#!/bin/sh
set -eu

cd /home/ctf
exec timeout --foreground --kill-after=5s "${SESSION_RUNTIME:-120s}" \
    stdbuf -i0 -o0 -e0 ./artifact-11
EOF

RUN chmod 0755 /usr/local/bin/launch-artifact-11 \
    && chown -R root:root /home/ctf \
    && chmod 0755 /home/ctf

USER ctf

EXPOSE 31267

CMD ["socat","-T120","TCP-LISTEN:31267,reuseaddr,fork,max-children=32","EXEC:/usr/local/bin/launch-artifact-11,stderr"]
