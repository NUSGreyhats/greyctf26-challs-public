#!/usr/bin/env python3
import asyncio
import json
import os
import signal
import sys
import urllib.error
import urllib.parse
import urllib.request


HOST = os.environ.get("PROXY_HOST", "0.0.0.0")
PORT = int(os.environ.get("PROXY_PORT", "1337"))
CHALLENGE_HOST = os.environ.get("CHALLENGE_HOST", "challenge")
CHALLENGE_PORT = int(os.environ.get("CHALLENGE_PORT", "1337"))
TOKEN_PROMPT_TIMEOUT = float(os.environ.get("TOKEN_PROMPT_TIMEOUT", "30"))
RESOLVE_TIMEOUT = float(os.environ.get("TOKEN_RESOLVE_TIMEOUT", "5"))
MAX_TOKEN_BYTES = int(os.environ.get("MAX_TOKEN_BYTES", "256"))
DISABLE_TOKEN_CHECK = os.environ.get("DISABLE_TOKEN_CHECK", "").lower() in {
    "1",
    "true",
    "yes",
    "on",
}


active_teams = {}
active_teams_lock = asyncio.Lock()


class RejectConnection(Exception):
    pass


def log(message):
    print(message, file=sys.stderr, flush=True)


def get_resolve_url():
    resolve_url = os.environ.get("CTFD_RESOLVE_URL", "").strip()
    if resolve_url:
        return resolve_url

    ctfd_url = os.environ.get("CTFD_URL", "").strip().rstrip("/")
    if not ctfd_url:
        return ""
    if "/plugins/team-token/api/v1/resolve" in ctfd_url:
        return ctfd_url
    return f"{ctfd_url}/plugins/team-token/api/v1/resolve"


def resolve_token_sync(token):
    resolve_url = get_resolve_url()
    plugin_secret = os.environ.get("TEAM_TOKEN_PLUGIN_SECRET", "")
    expected_challenge_id = os.environ.get("EXPECTED_CHALLENGE_ID", "")

    if not resolve_url:
        raise RejectConnection("resolve API is not configured")
    if not plugin_secret:
        raise RejectConnection("plugin secret is not configured")
    if not expected_challenge_id:
        raise RejectConnection("expected challenge id is not configured")

    params = urllib.parse.urlencode({"token": token})
    separator = "&" if "?" in resolve_url else "?"
    request = urllib.request.Request(
        f"{resolve_url}{separator}{params}",
        headers={"Authorization": f"Bearer {plugin_secret}"},
        method="GET",
    )

    try:
        with urllib.request.urlopen(request, timeout=RESOLVE_TIMEOUT) as response:
            body = response.read(4096)
            status = response.status
    except urllib.error.HTTPError as exc:
        raise RejectConnection(f"resolve API returned HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RejectConnection("could not reach resolve API") from exc
    except TimeoutError as exc:
        raise RejectConnection("resolve API timed out") from exc

    if status != 200:
        raise RejectConnection(f"resolve API returned HTTP {status}")

    try:
        data = json.loads(body.decode())
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RejectConnection("resolve API returned invalid JSON") from exc

    if data.get("valid") is not True:
        raise RejectConnection("invalid team token")

    try:
        challenge_id = int(data.get("challenge_id"))
        expected = int(expected_challenge_id)
        team_id = int(data.get("team_id"))
    except (TypeError, ValueError) as exc:
        raise RejectConnection("resolve API returned invalid team metadata") from exc

    if challenge_id != expected:
        raise RejectConnection("team token is for a different challenge")

    return {
        "team_id": team_id,
        "team_name": data.get("team_name") or "",
        "challenge_id": challenge_id,
        "solved": bool(data.get("solved")),
    }


async def resolve_token(token):
    return await asyncio.to_thread(resolve_token_sync, token)


async def write_text(writer, text):
    writer.write(text.encode())
    await writer.drain()


async def read_token(reader):
    try:
        raw = await asyncio.wait_for(
            reader.readline(), timeout=TOKEN_PROMPT_TIMEOUT
        )
    except asyncio.TimeoutError as exc:
        raise RejectConnection("timed out waiting for team token") from exc

    if not raw:
        raise RejectConnection("missing team token")
    if len(raw) > MAX_TOKEN_BYTES:
        raise RejectConnection("team token is too long")

    token = raw.strip().decode(errors="ignore")
    if not token:
        raise RejectConnection("missing team token")
    return token


async def reserve_team(team_id, peer):
    async with active_teams_lock:
        if team_id in active_teams:
            return False
        active_teams[team_id] = peer
        return True


async def release_team(team_id):
    async with active_teams_lock:
        active_teams.pop(team_id, None)


async def pipe(reader, writer):
    try:
        while True:
            chunk = await reader.read(4096)
            if not chunk:
                break
            writer.write(chunk)
            await writer.drain()
    except (BrokenPipeError, ConnectionResetError):
        pass
    finally:
        writer.close()


async def proxy_to_challenge(client_reader, client_writer):
    try:
        challenge_reader, challenge_writer = await asyncio.open_connection(
            CHALLENGE_HOST, CHALLENGE_PORT
        )
    except OSError as exc:
        raise RejectConnection("challenge service is unavailable") from exc

    tasks = [
        asyncio.create_task(pipe(client_reader, challenge_writer)),
        asyncio.create_task(pipe(challenge_reader, client_writer)),
    ]

    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        challenge_writer.close()
        try:
            await challenge_writer.wait_closed()
        except ConnectionError:
            pass


async def handle_client(reader, writer):
    peer = writer.get_extra_info("peername")
    team_id = None
    reserved = False

    try:
        if DISABLE_TOKEN_CHECK:
            log(f"accepted local debug session peer={peer}")
            await proxy_to_challenge(reader, writer)
            return

        await write_text(writer, "Team token: ")
        token = await read_token(reader)
        resolved = await resolve_token(token)
        team_id = resolved["team_id"]

        if not await reserve_team(team_id, peer):
            await write_text(writer, "Your team already has an active session.\n")
            return
        reserved = True

        log(
            "accepted session "
            f"team_id={team_id} team_name={resolved['team_name']!r} peer={peer}"
        )
        await write_text(writer, "Token accepted. Starting challenge...\n")
        await proxy_to_challenge(reader, writer)
    except RejectConnection as exc:
        await write_text(writer, f"Connection rejected: {exc}.\n")
        log(f"rejected session peer={peer}: {exc}")
    except Exception as exc:
        log(f"session error peer={peer}: {exc!r}")
    finally:
        if reserved:
            await release_team(team_id)
            log(f"released session team_id={team_id} peer={peer}")
        writer.close()
        try:
            await writer.wait_closed()
        except ConnectionError:
            pass


async def main():
    server = await asyncio.start_server(handle_client, HOST, PORT)
    sockets = ", ".join(str(sock.getsockname()) for sock in server.sockets or [])
    log(f"team token proxy listening on {sockets}")
    log(f"proxying accepted sessions to {CHALLENGE_HOST}:{CHALLENGE_PORT}")

    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)

    async with server:
        await stop.wait()
        server.close()
        await server.wait_closed()


if __name__ == "__main__":
    asyncio.run(main())
