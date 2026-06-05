# dbench_jumbf Notes

Hi future agent. This challenge is a jailed pwn service for quals. The goal is to keep the deploy target, the public dist bundle, and the solver aligned for the target binary and the pinned Debian runtime.

## Layout

- `README.md`: CTFd metadata. The real flag is here by repo convention.
- `service/`: deployable Docker context with the real flag in `service/flag.txt`.
- `dist/`: public bundle. It contains the same compiled `server` binary, a benign C2PA/JUMBF sample JPEG, and the dummy `grey{fake_flag}` in `dist/flag.txt`.
- `solve/solve.py`: official exploit. It reads `../dist/server` for binary metadata, then targets either local process mode or a remote TCP service.

Only the compiled `server` binary should be present in `service/`. In `dist/`, the only binary files should be `server` and `sample_c2pa.jpg`. Do not check in copied libc, loader, libstdc++, core dumps, IDA databases, patched duplicate binaries, or other binary artifacts.

`dist/sample_c2pa.jpg` was downloaded from `contentauth/c2pa-attacks` at:

```text
https://raw.githubusercontent.com/contentauth/c2pa-attacks/main/sample/C.jpg
```

Their README describes `sample/C.jpg` as having attached Content Credentials. It was also locally checked for `0xffeb` APP11 data plus `jumb` and `c2pa` markers.

The parser source in `dbench_jumbf/` is derived from the JPEG Systems JUMBF Reference Implementation 2:

```text
https://gitlab.com/wg1/jpeg-systems/reference-software/jumbf-reference-implementation-2
```

The upstream project is BSD 3-Clause licensed. Keep `dbench_jumbf/LICENSE.txt` and `THIRD_PARTY_LICENSES.md` in both `service/` and `dist/`; the BSD terms require retaining the copyright/license notice in source redistributions and reproducing it in documentation/materials for binary redistribution.

Do not copy the real flag into `dist/`. A quick leak check is:

```sh
rg -n "jumb0_0v3rfl0w|grey\\{jumb0" quals/pwn/dbench_jumbf/dist || true
```

## Deployment

Deploy from `service/`:

```sh
cd quals/pwn/dbench_jumbf/service
docker compose up --build -d
```

The service listens on TCP port `32167` on the host (container port `1337`).

The Docker image uses `pwn.red/jail` over a Debian rootfs. The Dockerfile is pinned to specific image digests. Runtime C/C++ libraries are installed from Debian inside the image with `apt`; they are intentionally not stored in the repo. The jail needs privileged container mode for the namespace/cgroup setup:

```yaml
privileged: true
```

Runtime limits are set in the Dockerfile:

```text
JAIL_TIME=60
JAIL_PIDS=16
JAIL_MEM=128M
JAIL_CPU=500
JAIL_TMP_SIZE=0
```

The target process is executed by `/app/run`, which currently just runs `/app/server`. This is intentional. `pwn.red/jail` already runs the jailed child with UID/GID `1000`, as shown in the startup log:

```text
Uid map: inside_uid:1000 outside_uid:1000 count:1
Gid map: inside_gid:1000 outside_gid:1000 count:1
```

Do not add `USER root` or run the service as root. Also avoid using `setpriv --regid=65534` in `/app/run`: that failed during testing because the jail only mapped GID `1000`. `setpriv --clear-groups` also failed under the jail permissions. Let the jail run the child as `1000:1000`.

## Smoke Tests

If host port `32167` is free:

```sh
cd quals/pwn/dbench_jumbf/service
docker compose up --build -d
printf '0\n' | nc -w 3 localhost 32167
docker compose down
```

Expected response:

```text
=== C2PA JUMBF Validator ===

jpeg size> goodbye
```

If `32167` is already taken, test the built image on another host port:

```sh
cd quals/pwn/dbench_jumbf/service
docker compose build
docker run -d --rm --privileged -p 31337:1337 --name dbench_jumbf_service_test service-dbench_jumbf
printf '0\n' | nc -w 3 localhost 31337
docker stop dbench_jumbf_service_test
```

For `dist/`, use the same flow from `dist/`; the image name from compose is usually `dist-dbench_jumbf`.

The public helper should print parsed metadata without crashing:

```sh
cd quals/pwn/dbench_jumbf/dist
python3 submit_sample.py localhost 32167
```

## Exploit Test

The solver supports `REMOTE HOST=... PORT=...`.

Test against the real service image:

```sh
docker run -d --rm --privileged -p 31337:1337 --name dbench_jumbf_service_test service-dbench_jumbf
timeout 30 python3 quals/pwn/dbench_jumbf/solve/solve.py REMOTE HOST=localhost PORT=31337
docker stop dbench_jumbf_service_test
```

Expected final line includes:

```text
grey{jumb0_0v3rfl0w_1n_4_jumbf_b0x_6imryubogc09}
```

Test against the public dist image:

```sh
docker run -d --rm --privileged -p 31338:1337 --name dbench_jumbf_dist_test dist-dbench_jumbf
timeout 30 python3 quals/pwn/dbench_jumbf/solve/solve.py REMOTE HOST=localhost PORT=31338
docker stop dbench_jumbf_dist_test
```

Expected final line includes:

```text
grey{fake_flag}
```

Both images were tested successfully with this solver path when the challenge was added.

## Solve Path

At a high level, the exploit abuses memory corruption in the JUMBF parser through crafted JPEG APP11/JUMBF segments:

1. Send a malformed JPEG to shape heap state.
2. Trigger a heap over-read through an undersized JUMBF content box to leak libc.
3. Trigger another over-read to recover the heap safe-linking key.
4. Allocate and free adjacent JUMBF boxes to prepare tcache chunks.
5. Use a JUMBF reassembly overflow to poison a tcache forward pointer.
6. Allocate over `stdout` and write a fake `FILE`/wide-data structure.
7. Trigger FSOP so glibc calls `system("  sh")`.
8. Send `cat /flag.txt`.

The exploit is sensitive to the target binary and libc. Keep `service/server` and `dist/server` synchronized, and keep the Debian base image digest pinned. The libc offsets below match the current `debian:trixie-slim` runtime installed in the Docker image:

```text
server
```

The solver constants are:

```text
UNSORTED_BIN_OFFSET = 0x1e5b20
STDOUT_OFF          = 0x1e65c0
WFILE_JUMPS_OFF     = 0x1e4228
SYSTEM_OFF          = 0x53110
```

If the exploit starts failing after a Docker or library change, first confirm the remote image still uses the same `server` as `dist/`, then confirm the Debian base digest and `libc6` package version did not change.

## Debugging Checklist

- `docker compose build` passes in both `service/` and `dist/`.
- `printf '0\n' | nc -w 3 localhost <port>` prints the validator banner and `goodbye`.
- Jail logs show UID/GID maps for `1000`.
- `rg -n "jumb0_0v3rfl0w|grey\\{jumb0" dist || true` prints nothing.
- `find service dist -maxdepth 1 -type f -exec file {} +` shows no binary files except `service/server`, `dist/server`, and `dist/sample_c2pa.jpg`.
- `python3 -m py_compile solve/solve.py` passes.
- Solver against service returns the real flag.
- Solver against dist returns `grey{fake_flag}`.
- No leftover test containers are running:

```sh
docker ps --filter name=dbench_jumbf
```

If a container cannot bind `32167`, something else is using the port. Use a temporary host port for testing with `docker run -p 31337:1337`.
