#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from collections import deque
from pathlib import Path
from typing import Iterable

import numpy as np
from PIL import Image


ACTIONS = {
    0: "left",
    1: "right",
    2: "forward",
    3: "pickup",
    4: "drop",
    5: "toggle",
    6: "done",
}
ACTION_IDS = {name: action for action, name in ACTIONS.items()}
DIR_TO_VEC = {
    0: (1, 0),
    1: (0, 1),
    2: (-1, 0),
    3: (0, -1),
}


def parse_actions(text: str) -> list[int]:
    out: list[int] = []
    for raw in text.replace(",", " ").split():
        token = raw.strip().lower()
        if not token or token.startswith("#"):
            continue
        action = int(token) if token.isdigit() else ACTION_IDS[token]
        if action not in ACTIONS:
            raise ValueError(f"unknown action: {raw}")
        out.append(action)
    return out


def load_actions(path: str | Path | None) -> list[int]:
    if path is None:
        return []
    return parse_actions(Path(path).read_text(encoding="utf-8"))


def save_image(path: Path, obs: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(obs.astype(np.uint8), mode="RGB").save(path)


def make_env(seed: int = 2026):
    try:
        import gymnasium as gym
        from minigrid.wrappers import RGBImgPartialObsWrapper, ImgObsWrapper
    except Exception as exc:
        if os.environ.get("IMCD_ALLOW_ENV_STUB") == "1":
            raise RuntimeError("MiniGrid is required for faithful visuals; install dist requirements.") from exc
        raise RuntimeError(
            "MiniGrid-LockedRoom-v0 is required. Run with the dist requirements, "
            "for example: uv run --with-requirements dist/requirements.txt python ..."
        ) from exc

    env = gym.make("MiniGrid-LockedRoom-v0", render_mode="rgb_array")
    env = RGBImgPartialObsWrapper(env, tile_size=8)
    env = ImgObsWrapper(env)
    env.reset(seed=seed)
    return env


def front_cell(pos: tuple[int, int], direction: int) -> tuple[int, int]:
    dx, dy = DIR_TO_VEC[int(direction)]
    return int(pos[0]) + dx, int(pos[1]) + dy


def object_at(env, pos: tuple[int, int]):
    return env.unwrapped.grid.get(int(pos[0]), int(pos[1]))


def extracted_info(env) -> dict:
    u = env.unwrapped
    pos = tuple(int(v) for v in u.agent_pos)
    direction = int(u.agent_dir)
    carrying = u.carrying
    fwd = front_cell(pos, direction)
    fwd_obj = object_at(env, fwd)
    locked_doors = []
    doors = []
    keys = []
    for y in range(u.height):
        for x in range(u.width):
            obj = u.grid.get(x, y)
            if obj is None:
                continue
            if obj.type == "door":
                locked = bool(getattr(obj, "is_locked", False))
                open_ = bool(getattr(obj, "is_open", False))
                doors.append((x, y, obj.color, locked, open_))
                if locked:
                    locked_doors.append((x, y, obj.color, open_))
            elif obj.type == "key":
                keys.append((x, y, obj.color))
    near_locked = any(abs(pos[0] - x) + abs(pos[1] - y) <= 1 for x, y, _, _ in locked_doors)
    facing_locked = (
        fwd_obj is not None
        and fwd_obj.type == "door"
        and bool(getattr(fwd_obj, "is_locked", False))
    )
    return {
        "agent_pos": pos,
        "agent_dir": direction,
        "has_key": carrying is not None and carrying.type == "key",
        "carrying": None if carrying is None else {"type": carrying.type, "color": carrying.color},
        "doors": doors,
        "locked_doors": locked_doors,
        "keys": keys,
        "near_locked_door": near_locked,
        "facing_locked_door": facing_locked,
        "front_cell": fwd,
        "front_object": None
        if fwd_obj is None
        else {
            "type": fwd_obj.type,
            "color": getattr(fwd_obj, "color", None),
            "locked": bool(getattr(fwd_obj, "is_locked", False)),
            "open": bool(getattr(fwd_obj, "is_open", False)),
        },
    }


def merged_info(env, info: dict | None = None) -> dict:
    out = dict(info or {})
    out.update(extracted_info(env))
    return out


def run_actions(seed: int, actions: Iterable[int]) -> tuple[np.ndarray, dict, list[dict]]:
    env = make_env(seed)
    obs, info = env.reset(seed=seed)
    info = merged_info(env, info)
    trace = [{"action": -1, "reward": 0.0, "info": info}]
    for action in actions:
        step = env.step(int(action))
        obs, reward, terminated, truncated, raw_info = step
        info = merged_info(env, raw_info)
        trace.append({"action": int(action), "reward": float(reward), "info": info})
        if terminated or truncated:
            break
    return np.asarray(obs, dtype=np.uint8), info, trace


def passable_for_planning(env, pos: tuple[int, int], locked_key_color: str | None = None) -> bool:
    obj = object_at(env, pos)
    if obj is None:
        return True
    if obj.type in {"key", "goal"}:
        return True
    if obj.type == "door":
        if not getattr(obj, "is_locked", False):
            return True
        return locked_key_color is not None and obj.color == locked_key_color
    return False


def turn_actions(src_dir: int, dst_dir: int) -> list[int]:
    right = (dst_dir - src_dir) % 4
    left = (src_dir - dst_dir) % 4
    if right <= left:
        return [1] * right
    return [0] * left


def bfs_actions(env, start: tuple[int, int, int], goals: set[tuple[int, int]], locked_key_color: str | None = None) -> list[int]:
    q = deque([(start, [])])
    seen = {start}
    while q:
        (x, y, direction), path = q.popleft()
        if (x, y) in goals:
            return path
        for ndir, (dx, dy) in DIR_TO_VEC.items():
            nx, ny = x + dx, y + dy
            if not passable_for_planning(env, (nx, ny), locked_key_color):
                continue
            actions = turn_actions(direction, ndir)
            obj = object_at(env, (nx, ny))
            if obj is not None and obj.type == "door" and not getattr(obj, "is_open", False):
                actions = actions + [5]
            actions = actions + [2]
            state = (nx, ny, ndir)
            if state not in seen:
                seen.add(state)
                q.append((state, path + actions))
    raise RuntimeError("no path found in MiniGrid layout")


def adjacent_positions(pos: tuple[int, int]) -> set[tuple[int, int]]:
    x, y = pos
    return {(x + dx, y + dy) for dx, dy in DIR_TO_VEC.values()}


def actions_to_face(env, target: tuple[int, int]) -> list[int]:
    u = env.unwrapped
    pos = tuple(int(v) for v in u.agent_pos)
    direction = int(u.agent_dir)
    dx = int(target[0]) - pos[0]
    dy = int(target[1]) - pos[1]
    for ndir, vec in DIR_TO_VEC.items():
        if vec == (dx, dy):
            return turn_actions(direction, ndir)
    raise RuntimeError("target is not adjacent")


def find_key_locked_door_prefix(seed: int = 2026) -> list[int]:
    env = make_env(seed)
    _, _ = env.reset(seed=seed)
    info = extracted_info(env)
    locked = info["locked_doors"]
    if not locked:
        raise RuntimeError("MiniGrid layout has no locked door")
    door_x, door_y, door_color, _ = locked[0]
    key_positions = [(x, y) for x, y, color in info["keys"] if color == door_color]
    if not key_positions:
        raise RuntimeError(f"MiniGrid layout has no {door_color} key")
    key_pos = key_positions[0]

    start = (*info["agent_pos"], info["agent_dir"])
    key_goals = adjacent_positions(key_pos)
    actions = bfs_actions(env, start, key_goals)
    for action in actions:
        env.step(action)
    face_key = actions_to_face(env, key_pos)
    actions.extend(face_key)
    for action in face_key:
        env.step(action)
    actions.append(3)
    env.step(3)

    info = extracted_info(env)
    start = (*info["agent_pos"], info["agent_dir"])
    door_adjacent = adjacent_positions((door_x, door_y))
    to_door = bfs_actions(env, start, door_adjacent)
    actions.extend(to_door)
    for action in to_door:
        env.step(action)
    face = actions_to_face(env, (door_x, door_y))
    actions.extend(face)
    for action in face:
        env.step(action)
    actions.append(5)
    return actions


def all_door_positions(env) -> list[tuple[int, int, str, bool, bool]]:
    u = env.unwrapped
    doors = []
    for y in range(u.height):
        for x in range(u.width):
            obj = u.grid.get(x, y)
            if obj is not None and obj.type == "door":
                doors.append((x, y, obj.color, bool(getattr(obj, "is_locked", False)), bool(getattr(obj, "is_open", False))))
    return doors


def inspect_door(env, door_pos: tuple[int, int]) -> list[int]:
    actions: list[int] = []
    info = extracted_info(env)
    if info["agent_pos"] not in adjacent_positions(door_pos):
        route = bfs_actions(env, (*info["agent_pos"], info["agent_dir"]), adjacent_positions(door_pos))
        actions.extend(route)
        for action in route:
            env.step(action)
    face = actions_to_face(env, door_pos)
    actions.extend(face)
    for action in face:
        env.step(action)
    door = object_at(env, door_pos)
    if door is not None and door.type == "door" and not getattr(door, "is_open", False):
        actions.append(ACTION_IDS["toggle"])
        env.step(ACTION_IDS["toggle"])
    front = object_at(env, door_pos)
    if front is not None and front.type == "door" and getattr(front, "is_open", False):
        actions.append(ACTION_IDS["forward"])
        env.step(ACTION_IDS["forward"])
    return actions


def inspect_other_doors_prefix(seed: int = 2026) -> list[int]:
    env = make_env(seed)
    _, _ = env.reset(seed=seed)
    door, _ = target_locked_door_and_key(env)
    if door is None:
        raise RuntimeError("MiniGrid layout has no locked door")
    locked_pos = (door[0], door[1])
    remaining = [(x, y) for x, y, _, locked, _ in all_door_positions(env) if not locked and (x, y) != locked_pos]
    actions: list[int] = []
    while remaining:
        info = extracted_info(env)
        best_idx = min(
            range(len(remaining)),
            key=lambda idx: min(abs(info["agent_pos"][0] - x) + abs(info["agent_pos"][1] - y) for x, y in adjacent_positions(remaining[idx])),
        )
        target = remaining.pop(best_idx)
        inspected = inspect_door(env, target)
        actions.extend(inspected)
    return actions


def find_locked_door_failed_attempt_prefix(seed: int = 2026, attempts: int = 3) -> list[int]:
    env = make_env(seed)
    _, _ = env.reset(seed=seed)
    actions = inspect_other_doors_prefix(seed)
    for action in actions:
        env.step(action)
    info = extracted_info(env)
    locked = info["locked_doors"]
    if not locked:
        raise RuntimeError("MiniGrid layout has no locked door")
    door_x, door_y, _, _ = locked[0]
    to_locked = bfs_actions(env, (*info["agent_pos"], info["agent_dir"]), adjacent_positions((door_x, door_y)))
    actions.extend(to_locked)
    for action in to_locked:
        env.step(action)
    face = actions_to_face(env, (door_x, door_y))
    actions.extend(face)
    for action in face:
        env.step(action)
    for idx in range(attempts):
        action = ACTION_IDS["toggle"] if idx % 2 == 0 else ACTION_IDS["done"]
        actions.append(action)
        env.step(action)
    return actions


def find_reward_desire_prefix(seed: int = 2026) -> list[int]:
    env = make_env(seed)
    _, _ = env.reset(seed=seed)
    actions = find_locked_door_failed_attempt_prefix(seed)
    for action in actions:
        env.step(action)
    reward = 0.0
    terminated = truncated = False
    for _ in range(256 - len(actions)):
        action = expert_action_from_env(env)
        actions.append(action)
        _, reward, terminated, truncated, _ = env.step(action)
        if terminated or truncated:
            break
        if not target_locked_door_and_key(env)[0] and reward == 0.0:
            break
    if terminated or reward > 0:
        raise RuntimeError("desire prefix should stop before solving the real task")
    return actions


def target_locked_door_and_key(env) -> tuple[tuple[int, int, str] | None, tuple[int, int] | None]:
    info = extracted_info(env)
    locked = info["locked_doors"]
    if not locked:
        return None, None
    door_x, door_y, door_color, _ = locked[0]
    keys = [(x, y) for x, y, color in info["keys"] if color == door_color]
    return (door_x, door_y, door_color), (keys[0] if keys else None)


def find_goal_positions(env) -> set[tuple[int, int]]:
    u = env.unwrapped
    goals: set[tuple[int, int]] = set()
    for y in range(u.height):
        for x in range(u.width):
            obj = u.grid.get(x, y)
            if obj is not None and obj.type == "goal":
                goals.add((x, y))
    if not goals:
        raise RuntimeError("MiniGrid layout has no goal")
    return goals


def expert_action_from_env(env) -> int:
    info = extracted_info(env)
    pos = info["agent_pos"]
    direction = info["agent_dir"]
    carrying = info["carrying"]
    door, key_pos = target_locked_door_and_key(env)

    if carrying is None and door is not None:
        if key_pos is None:
            raise RuntimeError(f"MiniGrid layout has no {door[2]} key")
        if pos not in adjacent_positions(key_pos):
            return bfs_actions(env, (*pos, direction), adjacent_positions(key_pos))[0]
        face_key = actions_to_face(env, key_pos)
        return face_key[0] if face_key else ACTION_IDS["pickup"]

    if carrying is not None and door is not None:
        door_pos = (door[0], door[1])
        if pos not in adjacent_positions(door_pos):
            return bfs_actions(env, (*pos, direction), adjacent_positions(door_pos))[0]
        face_door = actions_to_face(env, door_pos)
        return face_door[0] if face_door else ACTION_IDS["toggle"]

    return bfs_actions(env, (*pos, direction), find_goal_positions(env), None)[0]


def find_expert_plan(seed: int = 2026) -> list[int]:
    env = make_env(seed)
    _, _ = env.reset(seed=seed)
    actions: list[int] = []
    reward = 0.0
    terminated = truncated = False
    for _ in range(256):
        action = expert_action_from_env(env)
        actions.append(action)
        _, reward, terminated, truncated, _ = env.step(action)
        if terminated or truncated:
            break
    if not terminated or reward <= 0:
        raise RuntimeError(f"expert did not solve seed {seed}: terminated={terminated} reward={reward}")
    return actions


def find_exploratory_expert_plan(seed: int = 2026) -> list[int]:
    env = make_env(seed)
    _, _ = env.reset(seed=seed)
    actions = inspect_other_doors_prefix(seed)
    for action in actions:
        _, reward, terminated, truncated, _ = env.step(action)
        if terminated or truncated:
            raise RuntimeError("exploratory prefix terminated before solving the task")
    reward = 0.0
    terminated = truncated = False
    for _ in range(256 - len(actions)):
        action = expert_action_from_env(env)
        actions.append(action)
        _, reward, terminated, truncated, _ = env.step(action)
        if terminated or truncated:
            break
    if not terminated or reward <= 0:
        raise RuntimeError(f"exploratory expert did not solve seed {seed}: terminated={terminated} reward={reward}")
    return actions


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the clean MiniGrid-LockedRoom-v0 RGB wrapper.")
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--actions")
    parser.add_argument("--out", type=Path, default=Path("clean_obs.png"))
    parser.add_argument("--print-prefix", action="store_true")
    args = parser.parse_args()
    if args.print_prefix:
        print(" ".join(map(str, find_key_locked_door_prefix(args.seed))))
        return 0
    obs, info, _ = run_actions(args.seed, load_actions(args.actions))
    save_image(args.out, obs)
    print(info)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
