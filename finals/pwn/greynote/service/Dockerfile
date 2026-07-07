# syntax=docker/dockerfile:1
#
# greynote — kctf-based deploy, single Dockerfile.
#   * one PoW per TCP connection (kctf-pow, the standard kctf client)
#   * one fresh, throwaway QEMU VM per connection
#
# The kctf challenge base image already ships socat + kctf-pow + an
# unprivileged 'user'. We add QEMU, inline two small scripts, and override the
# CMD so socat forks a PoW->QEMU pipeline per connection.
#
# Run from the challenge root:
#   docker compose up --build
#
# Default deployment assumes no /dev/kvm. QEMU runs without a KVM device unless
# infra deliberately adds a host-specific override on a supported machine.
#
# IMPORTANT: rootfs.cpio.gz must contain the REAL flag and must NOT contain the
# solution exploit (/xpl). Rebuild it with build_rootfs.sh before deploying.

FROM gcr.io/kctf-docker/challenge@sha256:f99f55006fcded43812c551a8cc020f4201aad4d9bbd73aa7ca0ca115068065b

# QEMU. (apt works on the Ubuntu-based kctf image.)
RUN apt-get update \
    && apt-get install -y --no-install-recommends qemu-system-x86 \
    && rm -rf /var/lib/apt/lists/*

# Challenge artifacts.
COPY bzImage rootfs.cpio.gz /kctf/

# One ephemeral VM per player
COPY <<'EOF' /kctf/qemu.sh
#!/bin/bash
: "${QEMU_TIMEOUT:?set QEMU_TIMEOUT in compose.yml}"
: "${QEMU_MEMORY:?set QEMU_MEMORY in compose.yml}"
: "${QEMU_SMP:?set QEMU_SMP in compose.yml}"
exec timeout "$QEMU_TIMEOUT" qemu-system-x86_64 \
  -m "$QEMU_MEMORY" -nographic -no-reboot -monitor none \
  -cpu qemu64,+smep,+smap -smp "cores=$QEMU_SMP" \
  -kernel /kctf/bzImage -initrd /kctf/rootfs.cpio.gz \
  -append "console=ttyS0 oops=panic panic=-1 quiet loglevel=0 kaslr" \
  -runas nobody
EOF

# Per-connection gate: solve PoW first (kctf-pow), then boot the VM.
# POW_DIFFICULTY is the kctf-pow work parameter (~log2 of work). Set to 0 to
# disable. Tune for a few seconds of client-side solve time.
# 113373 => about 1-2 minutes
COPY <<'EOF' /kctf/launch.sh
#!/bin/bash
set -uo pipefail
DIFF="${POW_DIFFICULTY:-113373}" 

if [ "$DIFF" != "0" ]; then
  /kctf/pow.py ask "$DIFF" 2>/dev/null || { echo "incorrect pow"; exit 1; }
fi

exec /kctf/qemu.sh
EOF

RUN chmod 0755 /kctf/qemu.sh /kctf/launch.sh

EXPOSE 31367

# socat: one forked child per connection (capped), pty so the PoW prompt and
# the guest serial console are interactive. PoW runs before QEMU, so it gates
# the expensive part.
COPY <<'EOF' /kctf/listen.sh
#!/bin/bash
set -uo pipefail
: "${MAX_CHILDREN:?set MAX_CHILDREN in compose.yml}"
: "${SESSION_TIMEOUT:?set SESSION_TIMEOUT in compose.yml}"
exec socat "-T${SESSION_TIMEOUT}" "TCP-LISTEN:31367,reuseaddr,fork,max-children=${MAX_CHILDREN}" \
  "EXEC:/kctf/launch.sh,pty,stderr,setsid,sigint,sane"
EOF

RUN chmod 0755 /kctf/listen.sh

CMD ["/kctf/listen.sh"]
