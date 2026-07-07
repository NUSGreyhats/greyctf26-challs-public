# Name

Blind Devil

# Description

Is this what people mean when they say they blindsolve Rubik's cubes? :0

Notes:
* Your goal is to solve 100 Rubik's cubes on the remote service in as few moves as possible.
* Your average move count will be used to compute your score. The lower, the better.
* The remote service authenticates with your team token: `{TEAM_TOKEN}`.
* N00bcak had to look up how people solved Rubik's cubes to do this challenge.

# Author

N00bcak

# Flag

`grey{score_based_no_static_flag}`

This challenge is score-based. After a team solves all 100 cubes, the service computes their score from average move count and submits the score to CTFd as a team award.

# Team Token

enabled: true
koth: true

# Whale

enabled: false
redirect_port: 1337
memory_limit: 512m
cpu_limit: 1.0

# Deployment

Deploy `chall/` as the service image. The container listens on `${PORT:-1337}` and serves one TCP session per connection.

Required environment:

- `CTFD_URL`: CTFd base URL.
- `CTFD_TEAM_TOKEN_CHALLENGE_ID`: CTFd challenge ID expected by the Team Token plugin.
- `CTFD_TEAM_TOKEN_PLUGIN_SECRET` or `TEAM_TOKEN_PLUGIN_SECRET`: bearer secret for the Team Token plugin resolver.
- `CTFD_API_TOKEN`: CTFd API token with award create/update access.

Optional environment:

- `PORT`: TCP listen port inside the container. Default: `1337`.
- `CTFD_RESOLVE_URL`: explicit Team Token plugin resolve endpoint override.
- `CTFD_SCORE_URL`: explicit CTFd awards endpoint override.
- `CTFD_AWARD_CATEGORY`: award category. Default: `Rubikscube`.
- `SOCAT_CLOSE_TIMEOUT`: SABLE-style close timeout passed to `socat -t`. Default: `20`.
- `SOCAT_IDLE_TIMEOUT`: idle timeout passed to `socat -T`. Default: `1800`.

Build:

```bash
docker build -t rubikscube-chall ./chall
```

Local server smoke without token/PoW:

```bash
PYTHONPATH=dist:chall python -u -m server.cli.app --headless --cube-count 1 --seed 1
```

Public practice CLI:

```bash
PYTHONPATH=dist python -u -m rubikscube.cli
```
