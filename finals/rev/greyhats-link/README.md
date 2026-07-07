# Name

Greyhats Link

# Description

My Greyhats Link router is bricked and stuck on the firmware recovery page. The upload seems to reject everything I throw at it. Can you figure out what it wants?

# Author

jro

# Flag

`grey{i_love_luanear_algebra_UUID}`

# Whale

enabled: true
redirect_port: 80
memory_limit: 256m
cpu_limit: 0.5

# Deployment

For local standalone testing, deploy with:

```bash
docker compose up --build
```

Production CTFd Whale deployment builds `greyhats-link:latest` from `service/compose.yml`. Whale uses the static CTFd flag seed above, replaces `UUID` for each container, and injects the generated value as `FLAG`.

The service builds a custom Lua 5.4 interpreter with rotated opcodes (ADD/MUL/BXOR) and compiles the CGI router from `router_cgi.lua`. A pre-signed firmware containing the flag payload is generated at build time via `sign_firmware.lua`.

Required environment:

- `FLAG`: the flag value written to `/flag.txt` at container start by the entrypoint. Local root Compose defaults to the README flag seed if `FLAG` is unset; Whale injects the per-instance flag in production.

The `dist/` directory contains pre-built binaries for player distribution (the compiled CGI, custom Lua interpreter, and lighttpd config). The `solve/` directory contains decompiled/disassembled reference files and the solve script.
