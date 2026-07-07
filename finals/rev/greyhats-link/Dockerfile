FROM ubuntu:24.04 AS builder

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    lua5.4 build-essential wget libreadline-dev python3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY build/build_custom.sh /build/
COPY build/router_cgi.lua /build/
COPY solve/sign_firmware.lua /build/
COPY solve/payload.lua /build/

RUN bash /build/build_custom.sh

RUN /opt/custom-lua/bin/luac-custom -s -o /build/index.cgi /build/router_cgi.lua && \
    strip /opt/custom-lua/bin/lua-custom

RUN lua5.4 /build/sign_firmware.lua /build/payload.lua /build/firmware.bin

FROM scratch
COPY --from=builder /opt/custom-lua/bin/lua-custom /lua
COPY --from=builder /build/index.cgi /index.cgi
