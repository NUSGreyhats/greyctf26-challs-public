# Greyhats Gallery Notes

## Layout

- `service/`: challenge Docker context and source, including the real flag
- `service/src/`: Express application
- `service/views/`: EJS templates
- `service/post_build/`: build-time EJS patch used by the Docker image
- `build-image.py`: regenerates the player image tarball in `dist/`
- `solve/solve.py`: exploit entrypoint
- `solve/scan.py`: optional Node process scanner helper
- `dist/`: player bundle with a fake flag image

## Local Run

```bash
cd service
docker compose up --build
```

The service listens on `http://localhost:34267` (container port `3000`).

## Deployment Notes

Hi future agent. This challenge is sensitive to the exact Node binary, so start by
confirming the image you are testing is the image you think you built.

- `service/compose.yml` builds `greyhats_gallery:latest` from `service/Dockerfile`.
- The Dockerfile pins the base image to `linux/amd64`:
  `node:lts-trixie-slim@sha256:c70f2d9b9dcd1f95d51b1f2d9c000637f203dbe2cbeaf06680780584518ca5c3`.
- The pinned image is Node `v24.15.0` on Debian GNU/Linux 13 `trixie`.
- The image labels record the base name, digest, and Node Docker image source revision
  `58635ae7aaeab55a5c036b59e8ca93d864119cbe`.
- Runtime privilege drop uses Debian `gosu`; the Node process runs as the dedicated
  `appuser`, not the bundled `node` user.
- `/app/uploads` is writable by `appuser`; `/app/views` is group-writable/sticky for
  the exploit path while the rest of `/app` stays root-owned.
- The checked-in `dist/greyhats_gallery_image.tar.gz` must be regenerated with
  `./build-image.py` after Docker image changes if the player bundle is refreshed.
- `install-flag.sh` re-randomizes the `/flag-*.txt` path on every container start,
  including a plain `docker restart` of the same container.

Useful deployment checks:

```bash
cd service
docker compose up --build -d --force-recreate
docker compose ps
docker image inspect greyhats_gallery:latest --format '{{json .Config.Labels}}'
docker exec service-gallery-1 sh -lc 'id appuser; node --version; cat /etc/os-release; command -v gosu; ls -ld /app/uploads /app/views'
curl -fsS http://127.0.0.1:34267/ | head
```

Expected highlights:

- `docker compose ps` shows `service-gallery-1` up and publishing `34267:3000`.
- `node --version` is `v24.15.0`.
- `/etc/os-release` says Debian 13 `trixie`.
- `id appuser` exists and the Node process is started through `gosu appuser`.
- `/app/uploads` is owned by `appuser:appuser`.
- `/app/views` is owned by `root:appuser` and has sticky group-writable permissions.
- The image labels include the pinned base digest and revision above.

If the container is restarting, check logs first:

```bash
cd service
docker compose logs --tail=100 gallery
```

Common failure modes:

- Compose did not rebuild the Dockerfile: use `docker compose up --build -d --force-recreate`
  from `service/`, and confirm the labels on `greyhats_gallery:latest`.
- Port `34267` is already in use: stop the other container/process or temporarily edit the
  host port in `service/compose.yml`.
- The exploit crashes but does not write `/flag`: the Node binary likely changed. Recheck
  `node --version`, the base digest, and whether `/usr/local/bin/node` is still non-PIE.
- Host-side `--scan` can fail with `/proc` permission errors because the service runs as
  `appuser`. That is expected on many Docker hosts. Use a same-UID analysis setup or a
  privileged helper container for calibration instead of changing the challenge user.
- `dist/greyhats_gallery_image.tar.gz` may be stale after image changes. Rebuild and
  re-export it with `./build-image.py` before distributing a refreshed player bundle.

## Dist Generation

Generate the player bundle image from the challenge root:

```bash
./build-image.py
```

The script builds from a temporary copy of `service/`. No flag is baked into the
image — the full flag is supplied at runtime via the `FLAG` environment variable
(see the dist `docker-compose.yml`). It then exports/imports the built filesystem
into a squashed `greyhats_gallery:latest` image before saving it to
`dist/greyhats_gallery_image.tar.gz`. The squash step intentionally strips Docker
build history, so the player bundle does not reveal build commands or patch helper
filenames; the only patch artifact in the player image should be the patched runtime
dependency itself.

The script restores the previous local `greyhats_gallery:latest` tag after writing
the tarball. The dist compose file still loads and runs `greyhats_gallery:latest`
for players.

Useful checks for the player tarball:

```bash
docker load < dist/greyhats_gallery_image.tar.gz
docker history --no-trunc greyhats_gallery:latest
docker run -d --name greyhats_player_test -p 3002:3000 greyhats_gallery:latest
first=$(docker exec greyhats_player_test sh -lc 'ls /flag-*.txt')
docker restart greyhats_player_test
second=$(docker exec greyhats_player_test sh -lc 'ls /flag-*.txt')
test "$first" != "$second"
docker exec greyhats_player_test sh -lc 'cat /flag-*.txt'
python3 solve/solve.py --url http://127.0.0.1:3002
docker rm -f greyhats_player_test
```

Expected player checks:

- `docker history` has a single `Imported from -` layer and no Dockerfile command
  history.
- The two `/flag-*.txt` paths differ across `docker restart`.
- The local flag content and solve output are `grey{fake_flag}`.
- A quick string scan of the tarball should not find the real flag, `solve.py`,
  `NOTES.md`, or patch helper filenames:

```bash
gzip -dc dist/greyhats_gallery_image.tar.gz | rg -a 'n0_5571|solve\.py|Greyhats Gallery Notes|patch-ejs|post_build'
```

## Solve

```bash
python3 solve/solve.py --url http://localhost:34267
```

The default payload removes the procfd upload symlinks, base64-encodes
`/flag-*.txt` into `/app/views/flag.ejs`, restarts the Node server, fetches
`/flag`, and decodes the flag locally.

The default addresses in `solve/solve.py` are calibrated for the pinned Node 24
Trixie slim binary. The Debian Node binary is non-PIE, so the ROP addresses are
stable for the pinned `linux/amd64` image. If the base image changes again, rerun
`solve/scan.py` against a same-UID or privileged analysis instance and update the
handle, signum, controlled return offset, PLT addresses, pop gadgets, and stage
address before shipping.

Smoke-test sequence after a rebuild:

```bash
cd service
docker compose up --build -d --force-recreate
cd ..
python3 solve/solve.py --url http://127.0.0.1:34267
cd service
docker compose up -d --force-recreate
```

The solve should print a `[flag]` object with a decoded `grey{...}` value. The final
`--force-recreate` leaves the local service back in a clean pre-exploit state.
