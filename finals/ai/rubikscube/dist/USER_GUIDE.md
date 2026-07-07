# Rubikscube User Guide

## Run the Visual CLI

Install dependencies, then run the local visual practice CLI from this directory:

```bash
python -m pip install -r requirements.txt
```

```bash
python -u -m rubikscube.cli
```

This opens the full-color cube renderer and an interactive move prompt.

To render in blind masked-color mode, pass `--no-color`:

```bash
python -u -m rubikscube.cli --no-color
```

The official remote challenge server is text-only and intentionally runs in
masked no-color mode. Local visual play does not need a team token or PoW.

To play the remote challenge, connect using the command shown in CTFd, usually:

```bash
nc <host> <port>
```

The server first prints a short banner, then asks for your CTFd team token:

```text
INFO rubikscube-server ready
INFO authenticate with your CTFd team token, then solve proof-of-work.
TOKEN required
```

Paste the token shown in the CTFd challenge description or connection info. It
may be shown next to the connection command through a `{TEAM_TOKEN}` placeholder.

After the token is accepted, the server may require proof-of-work:

```text
TOKEN ok
POW prefix=<prefix> difficulty=<difficulty>
```

Solve it with the included helper, then paste the nonce back into the service:

```bash
python pow.py <prefix> <difficulty>
```

After `POW ok`, the challenge prints its initial cube state and `READY`:

```text
POW ok
INFO challenge=masked-2x2x2 cubes=100
CUBE index=1 total=100
STATE code=<0..63> masked={...}
READY
```

There is no flag to copy. After you solve all cubes, the service prints your
final average and score, then submits that score for your CTFd team.

### Visual CLI Flags

| Flag | Value | Description |
| --- | --- | --- |
| `--no-color` | none | Renders the cube in blind masked-color mode, where unsolved face colors are hidden. |
| `--no-render` | none | Disables the renderer for terminal-only use. |
| `--no-repl` | none | Exits after processing the initial move sequence. |
| `--no-shuffle` | none | Starts from a solved cube instead of a random shuffle. |
| `--shuffle-seed` | integer | Uses a reproducible shuffle seed. |
| `--shuffle-length` | positive integer | Sets the startup shuffle length. Default: `22`. |
| `--move-duration` | seconds | Sets the target duration for each animated quarter-turn. Default: `0.05`. |
| `--record-mp4` | path | Records the initial move sequence to an MP4 file. |
| `--debug-render` | none | Prints every rendered tile color to stderr. |

### Remote Server Prompts

| Prompt | Response | Description |
| --- | --- | --- |
| `TOKEN required` | Your CTFd team token, or `token <team-token>` | Required only on official team-token-gated servers. This prompt appears before PoW. |
| `POW prefix=<prefix> difficulty=<difficulty>` | Nonce from `python pow.py <prefix> <difficulty>` | Required only when the official server enables proof-of-work. |

## Commands

Send one command per input line.

| Command | Aliases / Forms | Description | Limit |
| --- | --- | --- | --- |
| `move <moves>` | raw `<moves>` without the `move` prefix | Applies and animates a move sequence, then prints one compact trace line containing the observation code after each move. `R U F'` and `move R U F'` are equivalent. | `2048` moves per command; `25000` total moves per cube |
| `quit` | `exit`, `q` | Ends the interactive prompt. | none |

The CLI processes one command line at a time. It does not run commands concurrently.

## Move Notation

Move notation accepts quarter-turn Singmaster moves. The aliases are:

- `V = U'`
- `S = L'`
- `G = F'`

Valid base moves are:

```text
U D F B L R U' D' F' B' L' R'
```

Aliases cannot take a prime suffix. For example, use `U` instead of `V'`.

Move sequences are applied in order and animated one turn at a time.

## Examples

Examples:

```text
move F S R'
R U V
```
