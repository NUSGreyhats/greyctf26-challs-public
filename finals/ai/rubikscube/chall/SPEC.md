# Masked 2x2x2 Organizer Specification

## Challenge Surface

The deployed challenge is a line-oriented terminal service that hosts a sequence
of masked 2x2x2 Rubik's cubes. Player-facing information is limited to the CLI
protocol exposed by `python -u -m server.cli.app --headless --pow --no-color --team-token`.

Player-visible protocol lines:

- `INFO rubikscube-server ready`
- `INFO authenticate with your CTFd team token, then solve proof-of-work.`
- `TOKEN required`
- `TOKEN ok`
- `TOKEN failed: <public reason>`
- `POW prefix=<hex> difficulty=<bits>`
- `POW ok`
- `INFO ...`
- `INFO max_moves_per_cube=25000`
- `CUBE index=<n> total=<m>`
- `STATE code=<0..63> masked={<color>: <bool>, ...}`
- `TRACE count=<n> codes=<comma-separated ints>`
- `MOVES current=<k> limit=25000`
- `PROGRESS solved=<n> total=<m> current_moves=<k> average=<x.xx>`
- `SOLVED cube=<n> total=<m> moves=<k>`
- `FAILED cube=<n> total=<m> moves=<k> limit=25000 reason=move_cap_exceeded`
- `FINAL average=<x.xx> score=<points> status=<submitted|score_pending>` on success
- `FINAL status=failed average=<x.xx> solved=<n> total=<m>` on move-cap failure
- `READY` framing for non-interactive clients after each response block

The visible `STATE code=... masked=...` payload is a 6-bit observation keyed by
the canonical color order:

- `white`
- `yellow`
- `green`
- `blue`
- `orange`
- `red`

Each bit is `True` iff the corresponding face is solved in the challenge's fixed
Singmaster frame.

The service accepts standard quarter-turn Singmaster notation and the following
cuBer Bruce aliases at the CTF layer only:

- `V = U'`
- `S = L'`
- `G = F'`

The cube core remains standard-only. Alias support is input/output sugar for the
challenge and solver layers.

## Deployment Contract

`chall/` is the only deployable service directory.

- `Dockerfile` runs `socat` on `${PORT:-1337}` and forks
  `python -u -m server.cli.app --headless --pow --no-color --team-token` for each TCP connection.
- `SOCAT_CLOSE_TIMEOUT` controls the `socat -t` close timeout. Default: `20`.
- `SOCAT_IDLE_TIMEOUT` controls the `socat -T` inactivity timeout. Default: `1800`.
- `--team-token` prompts before PoW and validates a raw `tt_...` token or
  `token tt_...` line against the CTFd Team Token plugin before any cube state
  is exposed.
- Team-token deployment requires `CTFD_TEAM_TOKEN_CHALLENGE_ID` and either
  `CTFD_RESOLVE_URL` or `CTFD_URL`; the bearer secret comes from
  `CTFD_TEAM_TOKEN_PLUGIN_SECRET` or `TEAM_TOKEN_PLUGIN_SECRET`.
- Successful completion does not reveal a flag. It submits a CTFd team award
  using `CTFD_API_TOKEN` and either `CTFD_SCORE_URL` or `CTFD_URL`.
- Default proof-of-work difficulty is 24 leading zero bits.
- Default cube count is 100.
- Default shuffle length is 22.
- `move` accepts at most 2048 move tokens per command and returns compact trace data.
- Each cube has a hard cap of 25000 applied move tokens.

`dist/` is the participant package and must not contain this specification,
organizer notes, or deployment-only material.

## Scoring Contract

The official challenge is score-based rather than flag-based. After all 100
cubes are solved, the service computes the team's average move count across all
cubes and submits a CTFd award for that team.

Scoring constants:

- average moves `<= 2000`: `1000` points
- average moves `>= 25000`: `100` points
- intermediate averages use logarithmic interpolation:

```text
score = round(100 + 900 * ln(25000 / average) / ln(25000 / 2000))
```

The CTFd scoring client uses a deterministic award marker containing the
challenge ID and team ID. If a team submits multiple completions, the client
preserves the best existing award and updates only when the new score is higher.

Required scoring environment:

- `CTFD_API_TOKEN`: CTFd API token with award create/update access
- `CTFD_URL`: CTFd base URL, used as `<CTFD_URL>/api/v1/awards`

Optional scoring environment:

- `CTFD_SCORE_URL`: explicit awards endpoint override
- `CTFD_AWARD_CATEGORY`: award category, default `Rubikscube`

## Allowed Solver Inputs

The reference solver must be challenger-only. It may use:

- the public challenge protocol over stdin/stdout
- the public move rules for quarter-turn Singmaster moves
- the public masked observation `STATE code=... masked=...`
- the public `move` response `TRACE count=<n> codes=...`
- the public move count and progress lines
- the public cube mechanics included in `dist/rubikscube`

The solver may precompute tables from the public mechanics. It must not depend
on service internals outside the public distribution.

## Forbidden Shortcuts

The reference solver must not use:

- launcher seed inference
- direct access to scrambles
- hidden full-state logs
- debug output
- any branch in solving logic that depends on non-player-visible data

Local-only helpers that do any of the above are noncompliant if they are used by
the main solve path.

## Move-Cap Contract

Every move token counts, including probes, undo moves, and the final solve
sequence. The counter resets only when a new cube starts.

If the current cube reaches 25000 moves and is still unsolved:

- the service emits `FAILED ... reason=move_cap_exceeded`
- the service emits `FINAL status=failed ...`
- the session terminates immediately

The final average on failure is computed over the cubes solved before the
failure.

## Reference Solve Contract

The maintained reference entrypoint is `../solve/solve.py` from this challenge
directory.

Supported reference-solve CLI flags:

- `--challenge-command`
- `--team-token`
- `--strategy {group,gofai}`
- `--cache-dir`
- `--moves-out`
- `--video-out`
- `--full-video-out`
- `--video-fps`
- `--move-duration`
- `--video-sample-every`
- `--verbose`

The default solve path must remain public-protocol-only. Optional output flags
may write local artifacts, but they must not be required to solve the challenge
and must not introduce a dependency on hidden service state.

## Organizer Checks

From the challenge root:

```bash
python3 -m unittest discover -s tests
```

Run the public CLI without PoW for fast local testing:

```bash
PYTHONPATH=dist:chall python3 -u -m server.cli.app --cube-count 1 --seed 1 --headless
```

Run the reference solver against that public CLI:

```bash
python3 solve/solve.py --challenge-command "python3 -u -m server.cli.app --cube-count 1 --seed 1 --headless"
```

Run the alternate finite-state GOFAI solver against the same public CLI:

```bash
python3 solve/solve.py --strategy gofai --challenge-command "python3 -u -m server.cli.app --cube-count 1 --seed 1 --headless"
```

Run the reference solver against a token-gated service by passing the team token
explicitly or setting `RUBIK_TEAM_TOKEN`:

```bash
python3 solve/solve.py --team-token 'tt_example' --challenge-command 'nc host 1337'
```
