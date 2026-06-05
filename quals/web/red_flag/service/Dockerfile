# ── Stage 1: build, patch, and obfuscate the binary ─────────────────────────
FROM golang:1.24-bookworm AS builder

RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY go.mod go.sum ./
RUN go mod download
COPY . .

# Build keeping the symbol table so we can enumerate handler addresses,
# then strip and obfuscate. Same code => same VAs as a direct -s -w build.
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-w" -o /tmp/crm_w . \
 && go tool nm /tmp/crm_w \
      | awk '/main\.main\..*\.func[0-9]+$/ {print "0x"$1} ; $3 ~ /^crm\/(handlers|middleware|utils)\./ && $2 == "T" {print "0x"$1}' \
      | sort -u > /tmp/targets.txt \
 && strip --strip-all /tmp/crm_w -o /tmp/crm \
 && python3 -c "d=open('/tmp/crm','rb').read(); o=b'\xf3\x0b\xe0\xc6G\x91\xa7\xd5Qc\xca\x06'; p=bytes([0xf3,0x0b,0xe0,0xc6,0x47,0x91,0x07,0xd5,0x51,0x63,0xca,0x06]); open('/tmp/crm_patched','wb').write(d.replace(o,p))" \
 && python3 add_anti_analysis.py /tmp/crm_patched --targets-file /tmp/targets.txt -o /tmp/crm_final -v

# ── Stage 2: assemble the runtime rootfs ────────────────────────────────────
FROM alpine:3.20 AS staging

# Tools the final image will need.
RUN apk add --no-cache su-exec \
 && adduser -D -H -u 1000 appuser

COPY --from=builder /tmp/crm_final                      /rootfs/crm
COPY install-flag.sh                                    /rootfs/usr/local/bin/install-flag.sh
COPY static                                             /rootfs/static
COPY flag.txt                                           /rootfs/flag-seed.txt

# Layout, ownership, and the kernel-script trap.
RUN mkdir -p /rootfs/data /rootfs/uploads /rootfs/usr/bin /rootfs/etc /rootfs/sbin \
 && cp /etc/passwd /rootfs/usr/bin/bash \
 && cp /etc/passwd /rootfs/etc/passwd \
 && cp /etc/group  /rootfs/etc/group \
 && cp /sbin/su-exec /rootfs/sbin/su-exec \
 && chmod 755 /rootfs/crm /rootfs/usr/local/bin/install-flag.sh /rootfs/usr/bin/bash /rootfs/sbin/su-exec \
 && chown 1000:1000 /rootfs/usr/bin/bash /rootfs/data /rootfs/uploads \
 && chown -R 1000:1000 /rootfs/static \
 && chown 0:0 /rootfs/flag-seed.txt \
 && chmod 0400 /rootfs/flag-seed.txt

# ── Stage 3: minimal runtime — pure COPY layer, zero RUN steps ──────────────
FROM alpine:3.20

COPY --from=staging /rootfs/ /

EXPOSE 8080
ENTRYPOINT ["/usr/local/bin/install-flag.sh"]
CMD ["/crm"]
