# syntax=docker/dockerfile:1

FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends socat coreutils \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /usr/sbin/nologin ctf

WORKDIR /home/ctf

COPY --chown=ctf:ctf dist/chal.py dist/vm.bin ./
RUN chmod 0444 chal.py vm.bin

COPY <<'EOF' /usr/local/bin/run-chal
#!/bin/sh
set -eu

cd /home/ctf
exec timeout -k 5s "${SESSION_TIMEOUT:-180}s" python3 -u chal.py
EOF

COPY <<'EOF' /usr/local/bin/start-service
#!/bin/sh
set -eu

: "${PORT:=31167}"
: "${SESSION_TIMEOUT:=180}"
: "${MAX_CHILDREN:=16}"
export SESSION_TIMEOUT

exec socat -T"${SESSION_TIMEOUT}" \
  "TCP-LISTEN:${PORT},reuseaddr,fork,max-children=${MAX_CHILDREN}" \
  "EXEC:/usr/local/bin/run-chal,pty,stderr,setsid,sigint,sane"
EOF

RUN chmod 0755 /usr/local/bin/run-chal /usr/local/bin/start-service

ENV PORT=31167 \
    SESSION_TIMEOUT=180 \
    MAX_CHILDREN=16 \
    FLAG=grey{vm_1s_r34lly_n0+_th4t_h4rd} \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

EXPOSE 31167

USER ctf
CMD ["/usr/local/bin/start-service"]
