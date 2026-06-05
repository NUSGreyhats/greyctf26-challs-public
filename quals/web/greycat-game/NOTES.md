# GreyCat Game Notes

## Layout

- `service/`: challenge source and runtime assets, including the real server-side flag path
- `solution/`: reference solver and solution notes
- `Dockerfile`: root-level image build for the challenge
- `compose.yml`: root-level local orchestration
- `.dockerignore`: root-level Docker build context filter
- `README.md`: player/operator-facing run instructions for the challenge root
- workspace root: authoring copy of the same challenge files plus local notes and scratch artifacts

The challenge is a lightweight Node.js runner game. The client bundle contains
fake flags and bait strings spread across visible sources, while the real flag
is only emitted by the server after a plausible run session progresses far
enough. The packaged service blocks direct HTTP access to server-only files such
as `serve-local.js`, `solve.js`, `SOLUTION.md`, `progress.md`, `Dockerfile`,
`.dockerignore`, and `cat.json`.

## Local Run

```bash
docker build -t greycat-game .
docker run --rm -p 34467:4173 greycat-game
```

The service listens on `http://localhost:34467` (container port `4173`).

## Deployment Notes
Verify that the top-level `service/` folder is the one you
intend to ship and that the runtime behavior matches the intended solve path.

- The root `Dockerfile` uses `node:24-alpine` and runs as the non-root `node` user.
- The root `.dockerignore` is the active ignore file because Docker reads
  ignore rules from the build context root.
- The root `Dockerfile` copies only `service/` into `/app`, so `solution/`
  and author notes are not present in the runtime image.
- The container starts the challenge with `node serve-local.js`.
- The service binds to port `4173` by default via `PORT=4173`.
- The real flag path is server-side in `serve-local.js`, not embedded in
  `game.js`, `index.html`, or `styles.css`.
- Fragment unlock requires a plausible `/api/run` progression over time before
  `/api/ghost` returns useful late-game reveal data.
- `/api/ghost` no longer returns plain flag text in the response body.
- The background renderer reconstructs visible fragment text from opaque stamp
  data after the session unlocks.
- `/api/replay?view=debug` exposes encoded trace material rather than plain
  fragments.
- Scripts in `solution/` are reference solvers and should never be
  reachable over HTTP from the running service.
- Fake flags are intentionally distributed across browser-visible sources:
  `index.html`, `styles.css`, runtime JS, and `localStorage`.

Useful deployment checks:

```bash
docker build -t greycat-game .
docker run -d --rm --name greycat-game-test -p 34467:4173 greycat-game
curl -i http://127.0.0.1:34467/
curl -i http://127.0.0.1:34467/serve-local.js
curl -i http://127.0.0.1:34467/cat.json
curl -i 'http://127.0.0.1:34467/api/bootstrap'
```

Expected highlights:

- `/` returns the game HTML.
- `/serve-local.js` returns `404`.
- `/cat.json` returns `404`.
- `/api/bootstrap` returns session/bootstrap JSON without the real flag.
- `/api/ghost` does not return a plain `text` field containing readable flag
  fragments.

Common failure modes:

- Another process is already using port `34467`: change the host port mapping or
  stop the existing process/container.
- Players open `index.html` directly instead of running the service: the real
  flag path will never unlock because the API calls are not available.
- Server-only files become web-visible again after static-file handler edits:
  re-test `/serve-local.js`, `/solution/solve.js`, and `/cat.json`.
- The solve becomes too scriptable again if `/api/ghost` trusts raw score input
  without `/api/run` progression checks or starts returning plain-text
  fragments again.

## Package Verification

The challenge should be validated from the repository root before
shipping:

```bash
docker build -t greycat-game .
docker run -d --rm --name greycat-game-test -p 34467:4173 greycat-game
node solution/solve.js http://127.0.0.1:34467
curl -i http://127.0.0.1:34467/serve-local.js
curl -i http://127.0.0.1:34467/solution/solve.js
docker rm -f greycat-game-test
```

Expected package checks:

- The solver prints `grey{th3_trex_rep1ac3d_by_a_gr3y_cat}`.
- Direct access to server-only or solution files returns `404`.
- The real flag is not present in served `game.js`, `index.html`, or
  `styles.css`.
- `/api/ghost` returns masked or opaque data rather than readable fragments.

## Solve

```bash
node solution/solve.js http://localhost:34467
```

The reference solver performs a valid bootstrap, sends plausible timed
`/api/run` progression samples, then decodes the opaque trace material exposed
through the late-game API flow to reconstruct the final flag. A legitimate human
solve should mirror that flow through real gameplay and late-game inspection.
