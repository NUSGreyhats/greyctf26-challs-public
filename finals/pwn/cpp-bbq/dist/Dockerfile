# syntax=docker/dockerfile:1

FROM ubuntu:26.04

ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    coreutils \
    socat \
    libstdc++6 \
 && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --home-dir /home/ctf --shell /usr/sbin/nologin ctf

WORKDIR /home/ctf
COPY --chmod=0555 chall ./chall
COPY --chmod=0444 flag.txt ./flag.txt

COPY <<'EOF' /usr/local/bin/launch-cpp-bbq
#!/bin/sh
set -eu

cd /home/ctf
exec timeout --foreground --kill-after=5s "${SESSION_RUNTIME:-10800s}" ./chall
EOF

RUN chown -R root:root /home/ctf \
 && chmod 755 /home/ctf \
 && chmod 0755 /usr/local/bin/launch-cpp-bbq

USER ctf
EXPOSE 1337

CMD ["socat", "-T10800", "TCP-LISTEN:1337,reuseaddr,fork,max-children=32", "EXEC:/usr/local/bin/launch-cpp-bbq,stderr"]
